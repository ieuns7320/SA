"""auditor.web.session 단위 테스트 — Secure 쿠키 플래그 자동 판단."""

from starlette.requests import Request

from auditor.web import session


def _make_request(scheme: str = "http", headers: list[tuple[str, str]] | None = None) -> Request:
    headers = headers or []
    scope = {
        "type": "http",
        "scheme": scheme,
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers],
        "server": ("testserver", 80),
        "path": "/",
        "query_string": b"",
    }
    return Request(scope)


class TestResolveSecureCookieFlag:
    """
    회귀 테스트(2026-08): 예전엔 WEB_SECURE_COOKIES env를 명시적으로 켜지 않으면
    항상 Secure=False였다 — 배포 시 이 설정을 깜빡하면 HTTPS로 서빙되는데도
    세션 쿠키가 평문으로 나갈 위험이 있었다. 이제 env가 명시적으로 설정 안
    됐으면 요청 자체(스킴 또는 X-Forwarded-Proto)를 보고 자동으로 켠다.
    """

    def test_http_request_without_env_override_is_not_secure(self, monkeypatch):
        monkeypatch.setattr(session, "_SECURE_COOKIES_ENV", None)
        assert session._resolve_secure_cookie_flag(_make_request(scheme="http")) is False

    def test_https_request_without_env_override_is_secure(self, monkeypatch):
        monkeypatch.setattr(session, "_SECURE_COOKIES_ENV", None)
        assert session._resolve_secure_cookie_flag(_make_request(scheme="https")) is True

    def test_forwarded_proto_https_behind_reverse_proxy_is_secure(self, monkeypatch):
        """리버스 프록시가 TLS를 종료하면 앱 입장에선 scheme이 http로 보이므로
        X-Forwarded-Proto 헤더도 확인해야 한다."""
        monkeypatch.setattr(session, "_SECURE_COOKIES_ENV", None)
        req = _make_request(scheme="http", headers=[("x-forwarded-proto", "https")])
        assert session._resolve_secure_cookie_flag(req) is True

    def test_explicit_env_true_overrides_http_scheme(self, monkeypatch):
        monkeypatch.setattr(session, "_SECURE_COOKIES_ENV", "true")
        assert session._resolve_secure_cookie_flag(_make_request(scheme="http")) is True

    def test_explicit_env_false_overrides_https_scheme(self, monkeypatch):
        monkeypatch.setattr(session, "_SECURE_COOKIES_ENV", "false")
        assert session._resolve_secure_cookie_flag(_make_request(scheme="https")) is False
