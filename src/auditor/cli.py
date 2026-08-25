"""
[컨트랙트 주소 또는 .sol 파일 입력] -> [Slither 취약점 분석] -> [Markdown 결과보고서]

LLM을 전혀 호출하지 않는다. 3단계 모두 로컬 실행 또는 무료 블록체인 조회 API만 쓴다.
"""

import json
import logging
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

from auditor import cache
from auditor.analyzers.preprocess import build_source_manifest, preprocess
from auditor.analyzers.slither_runner import run_slither
from auditor.input.address_fetcher import ETHEREUM_MAINNET_CHAIN_ID, fetch_verified_source
from auditor.pipeline_types import PipelineResult
from auditor.report.generator import generate_markdown_report

load_dotenv()

logger = logging.getLogger(__name__)

ADDRESS_PATTERN = re.compile(r"^0x[a-fA-F0-9]{40}$")


def resolve_input(target: str, work_dir: Path, is_address: bool) -> Path:
    """target이 주소면 소스를 받아오고, 파일 경로면 그대로 반환한다."""
    if is_address:
        logger.info("[1/3] 컨트랙트 주소 감지 — Etherscan에서 소스코드 조회 중: %s", target)
        return fetch_verified_source(target, output_dir=str(work_dir))
    logger.info("[1/3] 로컬 파일 사용: %s", target)
    return Path(target)


def _cache_key_for_target(target: str, is_address: bool) -> str | None:
    """
    캐시 키를 계산한다. 주소는 (chain_id, 주소) 조합, 로컬 파일은 내용 해시.
    아직 존재하지 않는 파일(잘못된 경로)이면 None을 반환해 캐시를 건너뛰고,
    이후 resolve_input에서 통상적인 FileNotFoundError로 이어지게 둔다.
    """
    if is_address:
        return cache.key_for_address(target, chain_id=ETHEREUM_MAINNET_CHAIN_ID)
    path = Path(target)
    if path.is_file():
        return cache.key_for_file(path)
    return None


def _source_root_for(sol_path: Path, work: Path, is_address: bool) -> Path:
    """finding['file']/코드 뷰어 파일 목록의 기준 디렉토리.

    주소 조회 결과는 fetch_verified_source가 work/<contract_name>/... 아래 저장하므로
    그 컨트랙트 디렉토리 전체가 기준이어야 import된 다른 파일도 상대경로로 잡힌다.
    로컬 파일은 entry 파일이 있는 디렉토리 자체가 기준(이웃 파일을 끌어오지 않도록).
    """
    if is_address:
        try:
            return work / sol_path.relative_to(work).parts[0]
        except ValueError:
            return sol_path.parent
    return sol_path.parent


def run_pipeline(target: str, work_dir: str = "reports", force_refresh: bool = False) -> PipelineResult:
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)

    is_address = bool(ADDRESS_PATTERN.match(target))

    cache_key = _cache_key_for_target(target, is_address)
    if cache_key and not force_refresh:
        cached = cache.load(cache_key, work)
        if cached is not None:
            return cached

    sol_path = resolve_input(target, work, is_address)
    if not sol_path.exists():
        raise FileNotFoundError(f"컨트랙트 파일을 찾을 수 없습니다: {sol_path}")

    logger.info("[2/3] Slither 정적분석 실행 중...")
    slither_json = work / f"{sol_path.stem}.slither.json"
    run_slither(str(sol_path), str(slither_json))

    source_root = _source_root_for(sol_path, work, is_address)
    findings = preprocess(str(slither_json), str(sol_path), source_root=source_root)
    findings["source_files"] = build_source_manifest(sol_path, source_root, multi_file=is_address)
    logger.info("       %d개의 finding 발견", findings["total_findings"])

    logger.info("[3/3] 리포트 생성 중...")
    report_md = generate_markdown_report(findings)
    report_path = work / f"{sol_path.stem}.report.md"
    report_path.write_text(report_md, encoding="utf-8")

    findings_path = work / f"{sol_path.stem}.findings.json"
    findings_path.write_text(json.dumps(findings, ensure_ascii=False, indent=2), encoding="utf-8")

    if cache_key:
        cache.store(cache_key, report_path, findings_path, target_display=target)

    return PipelineResult(report_path=report_path, findings_path=findings_path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    args = [a for a in sys.argv[1:] if a != "--refresh"]
    refresh = len(args) != len(sys.argv[1:])

    if len(args) != 1:
        print(
            "사용법: python -m auditor.cli <컨트랙트 주소 또는 .sol 파일 경로> [--refresh]\n"
            "  --refresh: 캐시된 결과가 있어도 무시하고 새로 분석"
        )
        sys.exit(1)

    result = run_pipeline(args[0], force_refresh=refresh)
    print(f"\n완료: {result.report_path}")
