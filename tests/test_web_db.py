"""auditor.web.db 단위 테스트 — sqlite CRUD와 소유권 조회, 재시작 후 정리 로직."""

import sqlite3
from pathlib import Path

import pytest

from auditor.web import db


@pytest.fixture
def db_path(tmp_path) -> Path:
    path = tmp_path / "jobs.sqlite3"
    db.init_db(path)
    return path


def test_create_and_get_job(db_path):
    db.create_job("job1", "session-a", "address", "0xabc", db_path=db_path)
    row = db.get_job("job1", "session-a", db_path=db_path)
    assert row is not None
    assert row["status"] == "queued"
    assert row["kind"] == "address"
    assert row["target_display"] == "0xabc"


def test_get_job_wrong_session_returns_none(db_path):
    """소유권 확인: 다른 세션이 조회하면 존재 여부와 무관하게 None이어야 한다."""
    db.create_job("job1", "session-a", "address", "0xabc", db_path=db_path)
    assert db.get_job("job1", "session-b", db_path=db_path) is None


def test_get_nonexistent_job_returns_none(db_path):
    assert db.get_job("nope", "session-a", db_path=db_path) is None


def test_update_job_status_succeeded(db_path):
    db.create_job("job1", "session-a", "file", "C.sol", db_path=db_path)
    db.update_job_status(
        "job1", "succeeded", report_path="/tmp/x.md", findings_path="/tmp/x.findings.json", db_path=db_path
    )
    row = db.get_job("job1", "session-a", db_path=db_path)
    assert row["status"] == "succeeded"
    assert row["report_path"] == "/tmp/x.md"
    assert row["findings_path"] == "/tmp/x.findings.json"
    assert row["error_message"] is None


def test_init_db_migrates_legacy_schema_without_findings_path(tmp_path):
    """
    회귀 테스트(2026-08): 코드 뷰어 기능 이전에 만들어진 jobs.sqlite3엔
    findings_path 컬럼이 없다. CREATE TABLE IF NOT EXISTS는 기존 테이블에
    컬럼을 추가해주지 않으므로, init_db()가 명시적으로 ALTER TABLE 마이그레이션을
    해야 한다 — 기존 데이터를 잃지 않고.
    """
    path = tmp_path / "legacy.sqlite3"
    conn = sqlite3.connect(str(path))
    conn.executescript("""
        CREATE TABLE jobs (
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
    """)
    conn.execute(
        "INSERT INTO jobs (id, session_id, kind, target_display, status, created_at, updated_at) "
        "VALUES ('old-job', 'session-a', 'address', '0xabc', 'succeeded', 't0', 't0')"
    )
    conn.commit()
    conn.close()

    db.init_db(path)

    row = db.get_job("old-job", "session-a", db_path=path)
    assert row is not None
    assert row["target_display"] == "0xabc"  # 기존 데이터 보존
    assert row["findings_path"] is None  # 새 컬럼은 NULL로 추가됨

    # 마이그레이션 이후엔 findings_path를 정상적으로 갱신할 수 있어야 한다.
    db.update_job_status(
        "old-job", "succeeded", report_path="/tmp/x.md", findings_path="/tmp/x.findings.json", db_path=path
    )
    row = db.get_job("old-job", "session-a", db_path=path)
    assert row["findings_path"] == "/tmp/x.findings.json"


def test_init_db_is_idempotent(db_path):
    """이미 마이그레이션된 DB에 init_db()를 다시 불러도 에러가 나면 안 된다."""
    db.init_db(db_path)
    db.init_db(db_path)


def test_update_job_status_failed_with_error(db_path):
    db.create_job("job1", "session-a", "address", "0xabc", db_path=db_path)
    db.update_job_status("job1", "failed", error_message="컨트랙트를 찾을 수 없습니다", db_path=db_path)
    row = db.get_job("job1", "session-a", db_path=db_path)
    assert row["status"] == "failed"
    assert row["error_message"] == "컨트랙트를 찾을 수 없습니다"


def test_sweep_stale_jobs_marks_queued_and_running_as_failed(db_path):
    db.create_job("job-queued", "session-a", "address", "0xabc", db_path=db_path)
    db.create_job("job-running", "session-a", "address", "0xdef", db_path=db_path)
    db.update_job_status("job-running", "running", db_path=db_path)
    db.create_job("job-done", "session-a", "address", "0x123", db_path=db_path)
    db.update_job_status("job-done", "succeeded", report_path="/tmp/x.md", db_path=db_path)

    swept = db.sweep_stale_jobs(db_path=db_path)

    assert swept == 2
    assert db.get_job("job-queued", "session-a", db_path=db_path)["status"] == "failed"
    assert db.get_job("job-running", "session-a", db_path=db_path)["status"] == "failed"
    assert db.get_job("job-done", "session-a", db_path=db_path)["status"] == "succeeded"


def test_list_jobs_by_session_returns_newest_first(db_path, monkeypatch):
    timestamps = iter(
        ["2026-01-01T00:00:01+00:00", "2026-01-01T00:00:02+00:00", "2026-01-01T00:00:03+00:00"]
    )
    monkeypatch.setattr(db, "_now", lambda: next(timestamps))

    db.create_job("job1", "session-a", "address", "0xabc", db_path=db_path)
    db.create_job("job2", "session-a", "address", "0xdef", db_path=db_path)
    db.create_job("job3", "session-b", "address", "0x999", db_path=db_path)

    rows = db.list_jobs_by_session("session-a", db_path=db_path)

    assert [r["id"] for r in rows] == ["job2", "job1"]  # 최신순
    assert {r["id"] for r in rows} == {"job1", "job2"}  # 다른 세션(job3)은 안 보임


def test_list_jobs_by_session_respects_limit(db_path):
    for i in range(5):
        db.create_job(f"job{i}", "session-a", "address", f"0x{i}", db_path=db_path)

    rows = db.list_jobs_by_session("session-a", limit=2, db_path=db_path)
    assert len(rows) == 2


def test_sweep_stale_jobs_noop_when_nothing_stale(db_path):
    db.create_job("job-done", "session-a", "address", "0x123", db_path=db_path)
    db.update_job_status("job-done", "succeeded", report_path="/tmp/x.md", db_path=db_path)
    assert db.sweep_stale_jobs(db_path=db_path) == 0
