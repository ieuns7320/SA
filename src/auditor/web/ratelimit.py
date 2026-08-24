"""세션+IP 기준 슬라이딩 윈도우 레이트리밋.

공유 ETHERSCAN_API_KEY와 제한된 slither 동시 실행 슬롯을 여러 익명 사용자가
나눠 쓰므로, 세션 하나가 이를 독점하지 못하게 막는다. 세션만 체크하면
쿠키를 지워서 우회할 수 있고 IP만 체크하면 같은 네트워크의 다른 사용자를
불공평하게 막으므로 둘 다 확인한다.

db.py의 rate_limit_hits 테이블(이미 있는 web_jobs.sqlite3)에 저장한다 — 예전엔
프로세스 인메모리 dict였는데, 서버 재시작하면 카운터가 리셋되고 여러 워커
프로세스 사이에 공유도 안 되는 문제가 있었다. sqlite는 이미 job 메타데이터로
쓰고 있던 인프라라 새 의존성(Redis 등) 없이 두 문제를 한 번에 해결한다.
"""

from auditor.web import db


def check(key: str, limit: int, window_seconds: float) -> bool:
    return db.check_rate_limit(key, limit, window_seconds)
