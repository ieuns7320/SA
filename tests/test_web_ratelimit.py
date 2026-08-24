"""auditor.web.ratelimit 단위 테스트 — 세션/IP 슬라이딩 윈도우."""

from auditor.web import ratelimit


def test_allows_up_to_limit(monkeypatch):
    monkeypatch.setattr(ratelimit, "_hits", {})
    key = "session:a"
    for _ in range(3):
        assert ratelimit.check(key, limit=3, window_seconds=60) is True


def test_blocks_after_limit_exceeded(monkeypatch):
    monkeypatch.setattr(ratelimit, "_hits", {})
    key = "session:a"
    for _ in range(3):
        ratelimit.check(key, limit=3, window_seconds=60)
    assert ratelimit.check(key, limit=3, window_seconds=60) is False


def test_different_keys_have_independent_limits(monkeypatch):
    monkeypatch.setattr(ratelimit, "_hits", {})
    for _ in range(3):
        ratelimit.check("session:a", limit=3, window_seconds=60)
    # session:a는 한도 초과지만 session:b는 별개 카운터라 영향 없어야 함
    assert ratelimit.check("session:a", limit=3, window_seconds=60) is False
    assert ratelimit.check("session:b", limit=3, window_seconds=60) is True


def test_old_hits_outside_window_are_dropped(monkeypatch):
    monkeypatch.setattr(ratelimit, "_hits", {})
    fake_now = [1000.0]
    monkeypatch.setattr(ratelimit.time, "monotonic", lambda: fake_now[0])

    key = "session:a"
    for _ in range(3):
        ratelimit.check(key, limit=3, window_seconds=60)
    assert ratelimit.check(key, limit=3, window_seconds=60) is False

    fake_now[0] += 61  # 윈도우 밖으로 이동
    assert ratelimit.check(key, limit=3, window_seconds=60) is True
