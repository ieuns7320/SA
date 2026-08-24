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

# 배포 시점(HTTPS 여부)에 맞춰 조정하는 env 플래그. 로컬 http://localhost 개발
# 환경에서는 False여야 브라우저가 쿠키를 보낸다.
SECURE_COOKIES = os.environ.get("WEB_SECURE_COOKIES", "false").lower() == "true"


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
        secure=SECURE_COOKIES,
        max_age=SESSION_MAX_AGE_SECONDS,
    )
    return sid
