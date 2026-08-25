"""auditor.cli 단위 테스트."""

import importlib
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from auditor import cache
from auditor.cli import ADDRESS_PATTERN, resolve_input, run_pipeline


class TestAddressPattern:
    @pytest.mark.parametrize(
        "value",
        [
            "0x" + "a" * 40,
            "0x1234567890abcdefABCDEF1234567890abcdef12",
        ],
    )
    def test_matches_valid_addresses(self, value):
        assert ADDRESS_PATTERN.match(value)

    @pytest.mark.parametrize(
        "value",
        [
            "0x123",
            "not-an-address",
            "tests/fixtures/contracts/vulnerable_vault.sol",
        ],
    )
    def test_rejects_non_addresses(self, value):
        assert not ADDRESS_PATTERN.match(value)


class TestResolveInput:
    def test_local_path_is_returned_as_is(self, tmp_path):
        sol = tmp_path / "C.sol"
        sol.write_text("contract C {}")
        result = resolve_input(str(sol), tmp_path, is_address=False)
        assert result == sol

    def test_address_triggers_fetch(self, monkeypatch, tmp_path):
        fake_fetch = MagicMock(return_value=tmp_path / "Fetched.sol")
        monkeypatch.setattr("auditor.cli.fetch_verified_source", fake_fetch)
        address = "0x" + "a" * 40
        result = resolve_input(address, tmp_path, is_address=True)
        fake_fetch.assert_called_once_with(address, output_dir=str(tmp_path))
        assert result == tmp_path / "Fetched.sol"


def _write_sol(path: Path, body: str = "contract C {}") -> Path:
    path.write_text(f'// SPDX-License-Identifier: MIT\npragma solidity ^0.8.19;\n{body}\n')
    return path


def _mock_pipeline_internals(monkeypatch):
    """resolve_input 이후 단계(slither/preprocess/report 생성)를 전부 모킹해
    캐싱 로직만 격리해서 검증한다."""
    run_slither_mock = MagicMock()
    monkeypatch.setattr("auditor.cli.run_slither", run_slither_mock)
    monkeypatch.setattr(
        "auditor.cli.preprocess",
        lambda *a, **k: {"total_findings": 0, "findings": [], "contract_file": "C.sol"},
    )
    monkeypatch.setattr("auditor.cli.build_source_manifest", lambda *a, **k: [])
    monkeypatch.setattr(
        "auditor.cli.generate_markdown_report", lambda findings: "# 리포트 본문"
    )
    return run_slither_mock


class TestRunPipelineCache:
    """
    캐싱 회귀 테스트(2026-08): 같은 대상(같은 내용의 로컬 파일 / 같은 주소)을
    재분석하면 Etherscan 재조회 + Slither 재실행 없이 캐시된 리포트를 그대로
    돌려줘야 한다.
    """

    @pytest.fixture(autouse=True)
    def _isolate_cache(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cache, "CACHE_ROOT", tmp_path / ".cache")
        monkeypatch.setattr(cache, "TTL_SECONDS", 3600)

    def test_second_run_same_file_skips_slither(self, tmp_path, monkeypatch):
        run_slither_mock = _mock_pipeline_internals(monkeypatch)
        sol = _write_sol(tmp_path / "C.sol")

        work1 = tmp_path / "work1"
        result1 = run_pipeline(str(sol), work_dir=str(work1))
        assert run_slither_mock.call_count == 1

        work2 = tmp_path / "work2"
        result2 = run_pipeline(str(sol), work_dir=str(work2))
        assert run_slither_mock.call_count == 1  # 재호출되지 않음 (캐시 히트)
        assert result2.report_path.read_text() == result1.report_path.read_text()
        assert result2.findings_path.exists()
        assert result2.findings_path.read_text() == result1.findings_path.read_text()

    def test_force_refresh_bypasses_cache(self, tmp_path, monkeypatch):
        run_slither_mock = _mock_pipeline_internals(monkeypatch)
        sol = _write_sol(tmp_path / "C.sol")

        run_pipeline(str(sol), work_dir=str(tmp_path / "work1"))
        run_pipeline(str(sol), work_dir=str(tmp_path / "work2"), force_refresh=True)
        assert run_slither_mock.call_count == 2

    def test_different_content_is_cache_miss(self, tmp_path, monkeypatch):
        run_slither_mock = _mock_pipeline_internals(monkeypatch)
        sol_a = _write_sol(tmp_path / "A.sol", body="contract A {}")
        sol_b = _write_sol(tmp_path / "B.sol", body="contract B {}")

        run_pipeline(str(sol_a), work_dir=str(tmp_path / "work1"))
        run_pipeline(str(sol_b), work_dir=str(tmp_path / "work2"))
        assert run_slither_mock.call_count == 2

    def test_expired_cache_is_miss(self, tmp_path, monkeypatch):
        run_slither_mock = _mock_pipeline_internals(monkeypatch)
        sol = _write_sol(tmp_path / "C.sol")

        run_pipeline(str(sol), work_dir=str(tmp_path / "work1"))
        monkeypatch.setattr(cache, "TTL_SECONDS", 0)  # 즉시 만료
        run_pipeline(str(sol), work_dir=str(tmp_path / "work2"))
        assert run_slither_mock.call_count == 2


def test_cli_loads_dotenv_on_import(monkeypatch):
    """
    회귀 테스트(2026-08): python-dotenv 의존성만 추가되고 실제 load_dotenv()
    호출이 빠져 있던 버그가 있었다 — .env를 채워도 ETHERSCAN_API_KEY를 셸에
    직접 export해야만 동작했음. cli 모듈을 로드하면 load_dotenv()가 반드시
    호출되어야 한다.
    """
    import dotenv

    import auditor.cli as cli_module

    mock_load = MagicMock()
    monkeypatch.setattr(dotenv, "load_dotenv", mock_load)
    try:
        importlib.reload(cli_module)
        mock_load.assert_called_once()
    finally:
        monkeypatch.undo()
        importlib.reload(cli_module)
