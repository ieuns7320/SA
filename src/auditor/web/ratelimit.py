"""세션+IP 기준 인메모리 슬라이딩 윈도우 레이트리밋. 신규 의존성 없음.

공유 ETHERSCAN_API_KEY와 제한된 slither 동시 실행 슬롯을 여러 익명 사용자가
나눠 쓰므로, 세션 하나가 이를 독점하지 못하게 막는다. 세션만 체크하면
쿠키를 지워서 우회할 수 있고 IP만 체크하면 같은 네트워크의 다른 사용자를
불공평하게 막으므로 둘 다 확인한다.

인메모리라 프로세스가 재시작되면 카운터가 리셋된다 — 단일 프로세스 v1에서
허용하는 트레이드오프로 남겨둔다 (CLAUDE.md 참고).
"""

import threading
import time
from collections import deque

_lock = threading.Lock()
_hits: dict[str, deque[float]] = {}


def check(key: str, limit: int, window_seconds: float) -> bool:
    """key가 최근 window_seconds 안에 limit번 이상 호출됐으면 False(제한 초과)."""
    now = time.monotonic()
    with _lock:
        window = _hits.setdefault(key, deque())
        while window and now - window[0] > window_seconds:
            window.popleft()
        if len(window) >= limit:
            return False
        window.append(now)
        return True
