"""
컨트랙트 주소를 입력받아 Etherscan API V2로 검증된 Solidity 소스를 받아온다.
LLM과 무관한 블록체인 데이터 조회이며, Etherscan API 키는 무료로 발급 가능하다
(https://etherscan.io/apis). 이 모듈이 API 요금을 발생시키는 일은 없다.

주의: Etherscan API V1(api.etherscan.io/api)은 2025년 8월 15일부로 완전히 폐기되었다.
반드시 V2 엔드포인트(api.etherscan.io/v2/api)와 chainid 파라미터를 사용해야 한다.
자세한 내용: https://docs.etherscan.io/v2-migration
"""

import json
import logging
import os
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

ETHERSCAN_API_URL = "https://api.etherscan.io/v2/api"
ETHEREUM_MAINNET_CHAIN_ID = 1

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2.0


def _is_rate_limited(data: dict) -> bool:
    """Etherscan은 레이트리밋을 HTTP 429가 아니라 200 OK + status=0으로 알려준다."""
    if data.get("status") == "1":
        return False
    return "rate limit" in str(data.get("result", "")).lower()


def _request_with_retries(params: dict) -> dict:
    """
    Etherscan API를 호출한다. 타임아웃/연결 끊김 같은 네트워크 에러와 무료 티어
    레이트리밋(초당 5회) 응답에 대해 지수 백오프로 재시도하고, 그래도 실패하면
    원인을 알 수 있는 한국어 에러로 감싸서 던진다 — 원본 트레이스백을 그대로
    노출하지 않는다.
    """
    last_error: str = "알 수 없는 오류"
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(ETHERSCAN_API_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.RequestException as e:
            last_error = f"네트워크 오류: {e}"
        else:
            if not _is_rate_limited(data):
                return data
            last_error = f"레이트리밋: {data.get('result')}"

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    raise RuntimeError(
        f"Etherscan API 호출이 {MAX_RETRIES}회 재시도 후에도 실패했습니다 — {last_error}"
    )


def fetch_verified_source(
    address: str,
    output_dir: str = "reports",
    api_key: str | None = None,
    chain_id: int = ETHEREUM_MAINNET_CHAIN_ID,
    _proxy_of: str | None = None,
) -> Path:
    """
    주소의 검증된 소스코드를 받아와 .sol 파일로 저장하고 경로를 반환한다.
    미검증 컨트랙트거나 API 키가 없으면 명확한 에러를 던진다 — 조용히 빈 파일을 만들지 않는다.
    chain_id 기본값은 이더리움 메인넷(1)이다. 다른 체인 목록은
    https://api.etherscan.io/v2/chainlist 참고.

    프록시 컨트랙트(EIP-1967/1167/UUPS 등)라면 Etherscan이 알려주는 구현
    컨트랙트(Implementation) 주소를 대신 가져온다 — 프록시 자체는 delegatecall
    껍데기뿐이라 실제 로직/취약점은 구현 컨트랙트에 있기 때문. 1단계만 따라가며
    (구현 컨트랙트가 다시 프록시를 가리키는 경우는 대응하지 않음), _proxy_of는
    내부 재귀 호출용 파라미터라 직접 넘기지 않는다.
    """
    api_key = api_key or os.environ.get("ETHERSCAN_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ETHERSCAN_API_KEY가 설정되지 않았습니다. "
            "https://etherscan.io/apis 에서 무료로 발급받아 .env에 추가하세요."
        )

    data = _request_with_retries({
        "chainid": chain_id,
        "module": "contract",
        "action": "getsourcecode",
        "address": address,
        "apikey": api_key,
    })

    if data.get("status") != "1" or not data.get("result"):
        raise RuntimeError(f"소스코드를 가져올 수 없습니다: {data.get('result') or data.get('message', 'unknown error')}")

    entry = data["result"][0]

    implementation = (entry.get("Implementation") or "").strip()
    if entry.get("Proxy") == "1" and implementation and _proxy_of is None:
        logger.info(
            "%s는 프록시 컨트랙트입니다. 실제 로직은 구현 컨트랙트 %s에 있으므로 "
            "그쪽을 대신 분석합니다.",
            address, implementation,
        )
        return fetch_verified_source(
            implementation,
            output_dir=output_dir,
            api_key=api_key,
            chain_id=chain_id,
            _proxy_of=address,
        )

    source_code = entry.get("SourceCode", "")
    if not source_code:
        raise RuntimeError(f"컨트랙트 {address}는 검증되지 않았습니다 (소스 비공개).")

    contract_name = entry.get("ContractName") or address
    out_dir = Path(output_dir) / contract_name
    out_dir.mkdir(parents=True, exist_ok=True)

    if source_code.strip().startswith("{"):
        # 이중 중괄호로 감싸진 표준 JSON 입력(standard-json-input) 포맷.
        # import로 연결된 모든 파일이 들어있으므로 전부 원래 상대 경로 그대로
        # 저장해야 import 문이 실제로 풀린다. 첫 파일만 저장하면 안 된다.
        raw = source_code.strip()
        if raw.startswith("{{") and raw.endswith("}}"):
            raw = raw[1:-1]
        parsed = json.loads(raw)
        sources = parsed.get("sources", parsed)

        written_paths = {}
        for rel_path, content in sources.items():
            file_path = out_dir / rel_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content.get("content", ""), encoding="utf-8")
            written_paths[rel_path] = file_path

        entry_path = _find_entry_file(written_paths, contract_name)
        if len(sources) > 1:
            logger.warning(
                "이 컨트랙트는 %d개 파일(import 포함)로 구성되어 있습니다. 전체를 '%s'에 "
                "저장했고, 진입점은 '%s'로 판단했습니다. 만약 원격 패키지(@openzeppelin/... "
                "같은) import가 있다면 remapping 설정이 없어 컴파일이 실패할 수 있습니다.",
                len(sources), out_dir, entry_path.name,
            )
        return entry_path
    else:
        # 단일 파일
        out_path = out_dir / f"{contract_name}.sol"
        out_path.write_text(source_code, encoding="utf-8")
        return out_path


def _find_entry_file(written_paths: dict, contract_name: str) -> Path:
    """저장된 파일들 중 실제 진입점(메인 컨트랙트가 정의된 파일)을 추정한다."""
    import re

    pattern = re.compile(rf"\bcontract\s+{re.escape(contract_name)}\b")
    for rel_path, file_path in written_paths.items():
        try:
            if pattern.search(file_path.read_text(errors="ignore")):
                return file_path
        except OSError:
            continue
    # 못 찾으면 첫 번째 파일로 폴백
    return next(iter(written_paths.values()))


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("사용법: python -m auditor.input.address_fetcher <contract_address>")
        sys.exit(1)

    path = fetch_verified_source(sys.argv[1])
    print(f"저장됨: {path}")