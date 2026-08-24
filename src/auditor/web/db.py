"""job 메타데이터 SQLite 스키마 + CRUD.

리포트 본문/소스/slither JSON은 여기 안 들어간다 — 기존 컨벤션 그대로
reports/<job_id>/ 파일로 관리하고, 이 DB는 상태 추적(폴링, 소유권 확인)용
메타데이터만 가진다.
"""

import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path("reports") / "web_jobs.sqlite3"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    target_display TEXT NOT NULL,
    status TEXT NOT NULL,
    report_path TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_session ON jobs(session_id);

-- 세션/IP 슬라이딩 윈도우 레이트리밋 히트 기록. 예전엔 프로세스 인메모리
-- dict였는데, 서버 재시작하면 리셋되고 여러 워커 프로세스 사이에 공유도
-- 안 됐다 — 이미 있는 sqlite 파일을 그대로 써서(신규 의존성 없이) 두
-- 문제를 한 번에 해결한다.
CREATE TABLE IF NOT EXISTS rate_limit_hits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL,
    ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rate_limit_key_ts ON rate_limit_hits(key, ts);
"""

# CREATE TABLE IF NOT EXISTS는 이미 존재하는 jobs 테이블(예전 스키마로 만들어진
# reports/web_jobs.sqlite3)엔 새 컬럼을 추가해주지 않는다 — 코드 뷰어용
# findings_path 컬럼은 명시적으로 마이그레이션해야 한다.
_MIGRATIONS: list[tuple[str, str]] = [
    ("findings_path", "ALTER TABLE jobs ADD COLUMN findings_path TEXT"),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_connection(db_path: Path | None = None):
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path | None = None) -> None:
    with get_connection(db_path) as conn:
        conn.executescript(_SCHEMA)
        existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
        for column_name, alter_sql in _MIGRATIONS:
            if column_name not in existing_columns:
                conn.execute(alter_sql)


def create_job(
    job_id: str,
    session_id: str,
    kind: str,
    target_display: str,
    db_path: Path | None = None,
) -> None:
    now = _now()
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO jobs (id, session_id, kind, target_display, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'queued', ?, ?)",
            (job_id, session_id, kind, target_display, now, now),
        )


def update_job_status(
    job_id: str,
    status: str,
    report_path: str | None = None,
    findings_path: str | None = None,
    error_message: str | None = None,
    db_path: Path | None = None,
) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE jobs SET status = ?, report_path = ?, findings_path = ?, "
            "error_message = ?, updated_at = ? WHERE id = ?",
            (status, report_path, findings_path, error_message, _now(), job_id),
        )


def get_job(job_id: str, session_id: str, db_path: Path | None = None) -> sqlite3.Row | None:
    with get_connection(db_path) as conn:
        cur = conn.execute(
            "SELECT * FROM jobs WHERE id = ? AND session_id = ?", (job_id, session_id)
        )
        return cur.fetchone()


def list_jobs_by_session(
    session_id: str, limit: int = 50, db_path: Path | None = None
) -> list[sqlite3.Row]:
    """세션 소유의 job을 최신순으로 반환한다 (히스토리 화면용)."""
    with get_connection(db_path) as conn:
        cur = conn.execute(
            "SELECT * FROM jobs WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
            (session_id, limit),
        )
        return cur.fetchall()


def check_rate_limit(
    key: str, limit: int, window_seconds: float, db_path: Path | None = None
) -> bool:
    """key가 최근 window_seconds 안에 limit번 이상 호출됐으면 False(제한 초과).
    같은 커넥션 안에서 DELETE(윈도우 밖 기록 정리) -> COUNT -> INSERT를 한
    트랜잭션으로 처리해 동시 요청 사이의 레이스를 SQLite의 쓰기 락으로 막는다."""
    now = time.time()
    cutoff = now - window_seconds
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM rate_limit_hits WHERE key = ? AND ts < ?", (key, cutoff))
        count = conn.execute(
            "SELECT COUNT(*) FROM rate_limit_hits WHERE key = ?", (key,)
        ).fetchone()[0]
        if count >= limit:
            return False
        conn.execute("INSERT INTO rate_limit_hits (key, ts) VALUES (?, ?)", (key, now))
        return True


def sweep_old_rate_limit_hits(max_age_seconds: float = 86400, db_path: Path | None = None) -> int:
    """`check_rate_limit`은 자기가 조회한 key의 오래된 기록만 지운다 — 한동안
    다시 안 보이는 세션/IP의 기록은 테이블에 계속 쌓인다. 현재 레이트리밋
    윈도우가 전부 1시간 이내라 24시간이면 넉넉히 안전한 기준으로 서버 시작
    시 한 번씩 정리한다."""
    cutoff = time.time() - max_age_seconds
    with get_connection(db_path) as conn:
        cur = conn.execute("DELETE FROM rate_limit_hits WHERE ts < ?", (cutoff,))
        return cur.rowcount


def sweep_stale_jobs(db_path: Path | None = None) -> int:
    """이전 프로세스에서 멈춘 queued/running job을 failed로 정리한다.
    (프로세스가 재시작되면 실행 중이던 Future는 사라지므로, 폴링 클라이언트가
    무한 대기하지 않도록 서버 시작 시 한 번 정리한다.) 정리된 row 수를 반환."""
    with get_connection(db_path) as conn:
        cur = conn.execute(
            "UPDATE jobs SET status = 'failed', error_message = ?, updated_at = ? "
            "WHERE status IN ('queued', 'running')",
            ("서버 재시작으로 중단됨", _now()),
        )
        return cur.rowcount
