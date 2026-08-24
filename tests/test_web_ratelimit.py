"""auditor.web.ratelimit 단위 테스트 — 세션/IP 슬라이딩 윈도우 (sqlite 기반)."""

import pytest

from auditor.web import db, ratelimit


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "jobs.sqlite3"
    db.init_db(path)
    return path


@pytest.fixture(autouse=True)
def _use_isolated_db(db_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", db_path)


def test_allows_up_to_limit():
    key = "session:a"
    for _ in range(3):
        assert ratelimit.check(key, limit=3, window_seconds=60) is True


def test_blocks_after_limit_exceeded():
    key = "session:a"
    for _ in range(3):
        ratelimit.check(key, limit=3, window_seconds=60)
    assert ratelimit.check(key, limit=3, window_seconds=60) is False


def test_different_keys_have_independent_limits():
    for _ in range(3):
        ratelimit.check("session:a", limit=3, window_seconds=60)
    # session:a는 한도 초과지만 session:b는 별개 카운터라 영향 없어야 함
    assert ratelimit.check("session:a", limit=3, window_seconds=60) is False
    assert ratelimit.check("session:b", limit=3, window_seconds=60) is True


def test_old_hits_outside_window_are_dropped(monkeypatch):
    fake_now = [1000.0]
    monkeypatch.setattr(db.time, "time", lambda: fake_now[0])

    key = "session:a"
    for _ in range(3):
        ratelimit.check(key, limit=3, window_seconds=60)
    assert ratelimit.check(key, limit=3, window_seconds=60) is False

    fake_now[0] += 61  # 윈도우 밖으로 이동
    assert ratelimit.check(key, limit=3, window_seconds=60) is True


def test_survives_across_calls_like_a_process_restart_would(db_path):
    """
    회귀 테스트(2026-08): 예전 인메모리 dict 구현은 프로세스가 재시작되면
    카운터가 리셋됐다. sqlite로 옮긴 뒤엔 같은 DB 파일을 다시 열어도(=새
    프로세스가 다시 연결하는 것과 동등) 히트 기록이 그대로 남아있어야 한다.
    """
    key = "session:a"
    for _ in range(3):
        ratelimit.check(key, limit=3, window_seconds=60)

    with db.get_connection(db_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM rate_limit_hits WHERE key = ?", (key,)
        ).fetchone()[0]
    assert count == 3


def test_sweep_old_rate_limit_hits_removes_stale_rows(db_path, monkeypatch):
    fake_now = [1000.0]
    monkeypatch.setattr(db.time, "time", lambda: fake_now[0])

    ratelimit.check("session:a", limit=10, window_seconds=3600)

    fake_now[0] += 90000  # 25시간 뒤 — 기본 max_age(24시간)를 넘김
    removed = db.sweep_old_rate_limit_hits(max_age_seconds=86400, db_path=db_path)
    assert removed == 1
