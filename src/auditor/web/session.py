"""로그인 없는 익명 세션.

쿠키는 서명된 데이터를 담지 않고 순수 조회 키로만 쓴다 — 서버가 어차피 매
job 조회 요청마다 DB에서 소유권(session_id 일치)을 확인하므로, 쿠키에
itsdangerous 같은 서명 레이어를 추가로 둘 이유가 없다.
"""

import os
import secrets

from fastapi import Request, Response

SESSION_COOKIE_NAME = "sid"
SESSION_MAX_AGE_SECONDS = 30 * 24 * 3600  # 30일

# 명시적으로 설정된 경우에만 이 값을 강제한다(리버스 프록시가 X-Forwarded-Proto를
# 안 붙여주는 배포 환경 등 자동 판단이 안 맞을 때의 탈출구). 안 정하면
# _resolve_secure_cookie_flag()가 요청 자체를 보고 자동으로 판단한다 — 배포 시
# env 설정을 깜빡해도 HTTPS 요청이면 안전하게 Secure가 켜지도록 하기 위함
# (기존엔 env 미설정 시 항상 False로 폴백해서, 이 플래그를 깜빡히면 프로덕션
# 배포에서도 세션 쿠키가 평문으로 나갈 위험이 있었다).
_SECURE_COOKIES_ENV = os.environ.get("WEB_SECURE_COOKIES")


def _resolve_secure_cookie_flag(request: Request) -> bool:
    if _SECURE_COOKIES_ENV is not None:
        return _SECURE_COOKIES_ENV.lower() == "true"
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return forwarded_proto == "https" or request.url.scheme == "https"


def get_session_id(request: Request, response: Response) -> str:
    """요청의 세션 쿠키를 반환한다. 없으면 새로 발급해서 응답에 심는다."""
    sid = request.cookies.get(SESSION_COOKIE_NAME)
    if sid:
        return sid

    sid = secrets.token_urlsafe(32)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        sid,
        httponly=True,
        samesite="lax",
        secure=_resolve_secure_cookie_flag(request),
        max_age=SESSION_MAX_AGE_SECONDS,
    )
    return sid
