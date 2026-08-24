"""
동일 대상(같은 온체인 주소, 또는 동일 내용의 로컬 파일)을 반복 분석할 때
Etherscan 재조회 + Slither 재실행을 건너뛰기 위한 파일 기반 캐시.

캐시 키는 분석 대상 자체로 결정된다:
  - 온체인 주소: (chain_id, 주소를 소문자로 정규화)
  - 로컬 파일: 파일 "경로"가 아니라 "내용"의 sha256 해시 — 같은 내용이면 파일명이
    달라도 같은 캐시를 쓴다.

캐시는 완성된 산출물 두 개(report.md + findings.json — 코드 뷰어가 쓰는 구조화된
finding/소스 목록)만 저장한다. slither.json이나 원본 소스 트리는 캐시 히트 시점에
다시 만들어지지 않고 그대로 필요 없어지므로, 저장 범위를 이 두 파일로 최소화해서
work_dir 전체를 복사하는 방식의 위험(공유 디렉토리 오염, 재귀 복사)을 피한다.

findings.json이 캐시에 없는 경우(이 기능 도입 이전에 저장된 옛날 캐시 엔트리)는
부분 히트로 취급하지 않고 완전 미스로 처리한다 — TTL이 6시간으로 짧아서 한 번
다시 분석하는 비용이 감수할 만하고, "report만 있고 findings는 없는" 애매한 상태를
피할 수 있다.

TTL이 지나면 무효화된다. 기본값을 짧게(6시간) 잡은 이유: 프록시 컨트랙트는
구현(Implementation) 주소가 재배포로 바뀔 수 있어서, 캐시를 너무 오래 신뢰하면
업그레이드된 로직이 아니라 예전 구현체를 분석한 stale 리포트를 계속 내줄 위험이
있다. `PIPELINE_CACHE_TTL_SECONDS` 환경변수로 조정 가능.
"""

import hashlib
import json
import logging
import os
import shutil
import time
from pathlib import Path

from auditor.pipeline_types import PipelineResult

logger = logging.getLogger(__name__)

CACHE_ROOT = Path(os.environ.get("PIPELINE_CACHE_DIR", "reports/.cache"))
TTL_SECONDS = int(os.environ.get("PIPELINE_CACHE_TTL_SECONDS", str(6 * 3600)))


def key_for_address(address: str, chain_id: int) -> str:
    raw = f"addr:{chain_id}:{address.lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def key_for_file(path: Path) -> str:
    content_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashlib.sha256(f"file:{content_digest}".encode()).hexdigest()


def _meta_path(key: str) -> Path:
    return CACHE_ROOT / f"{key}.meta.json"


def _report_cache_path(key: str) -> Path:
    return CACHE_ROOT / f"{key}.report.md"


def _findings_cache_path(key: str) -> Path:
    return CACHE_ROOT / f"{key}.findings.json"


def _delete_entry(key: str) -> None:
    for path in (_meta_path(key), _report_cache_path(key), _findings_cache_path(key)):
        path.unlink(missing_ok=True)


def load(key: str, dest_dir: Path) -> PipelineResult | None:
    """
    캐시가 존재하고 TTL 이내면 report.md/findings.json 둘 다 dest_dir로 복사하고
    PipelineResult를 반환한다. 캐시가 없거나(둘 중 하나라도 없으면 미스로 취급)
    만료됐으면 None — 호출자는 평소대로 새로 분석하면 된다.

    만료되었거나 손상된(meta.json 파싱 실패) 엔트리는 이 시점에 디스크에서
    지운다 — 안 지우면 같은 키가 다시는 조회되지 않는 한 report.md/findings.json이
    영원히 CACHE_ROOT에 남아 디스크를 계속 잡아먹는다. 한 번도 재조회되지 않는
    엔트리까지 정리하는 건 sweep_expired()가 담당한다(웹 서버 시작 시 호출).
    """
    meta_path = _meta_path(key)
    report_cache_path = _report_cache_path(key)
    findings_cache_path = _findings_cache_path(key)
    if not meta_path.exists() or not report_cache_path.exists() or not findings_cache_path.exists():
        return None

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _delete_entry(key)
        return None

    age = time.time() - meta.get("cached_at", 0)
    if age > TTL_SECONDS:
        _delete_entry(key)
        return None

    dest_dir.mkdir(parents=True, exist_ok=True)
    report_dest = dest_dir / meta["report_filename"]
    findings_dest = dest_dir / meta["findings_filename"]
    shutil.copy2(report_cache_path, report_dest)
    shutil.copy2(findings_cache_path, findings_dest)
    logger.info("캐시 히트 (%.0f초 전 결과, target=%s)", age, meta.get("target_display"))
    return PipelineResult(report_path=report_dest, findings_path=findings_dest)


def sweep_expired() -> int:
    """CACHE_ROOT를 훑어서 TTL이 지난(또는 손상된) 엔트리를 전부 지운다.
    load()의 정리는 그 키가 다시 조회될 때만 일어나므로, 한 번도 재조회되지
    않는 엔트리는 이걸로만 정리된다. 반환값은 지운 엔트리 수 — 웹 서버 시작
    시(lifespan) 호출한다."""
    if not CACHE_ROOT.exists():
        return 0

    now = time.time()
    removed = 0
    for meta_path in CACHE_ROOT.glob("*.meta.json"):
        key = meta_path.name.removesuffix(".meta.json")
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            expired = (now - meta.get("cached_at", 0)) > TTL_SECONDS
        except (OSError, json.JSONDecodeError):
            expired = True
        if expired:
            _delete_entry(key)
            removed += 1
    return removed


def store(key: str, report_path: Path, findings_path: Path, target_display: str) -> None:
    """분석이 끝난 리포트+findings를 캐시에 저장한다."""
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    shutil.copy2(report_path, _report_cache_path(key))
    shutil.copy2(findings_path, _findings_cache_path(key))
    meta = {
        "cached_at": time.time(),
        "report_filename": report_path.name,
        "findings_filename": findings_path.name,
        "target_display": target_display,
    }
    _meta_path(key).write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
