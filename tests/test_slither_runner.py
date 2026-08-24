"""auditor.analyzers.slither_runner 단위 테스트.

실제 slither/solc 실행 없이 subprocess 호출을 모킹해서 로직만 검증한다.
실제 slither 실행까지 포함하는 end-to-end 검증은 tests/test_pipeline_integration.py.
"""

import subprocess
from pathlib import Path

import pytest

from auditor.analyzers.slither_runner import (
    _extract_pragma_version,
    _wrap_with_resource_limits,
    ensure_solc_version,
    run_slither,
)


def _write(tmp_path: Path, pragma_line: str) -> Path:
    p = tmp_path / "C.sol"
    p.write_text(f"// SPDX-License-Identifier: MIT\n{pragma_line}\ncontract C {{}}\n")
    return p


class TestExtractPragmaVersion:
    def test_caret_version(self, tmp_path):
        path = _write(tmp_path, "pragma solidity ^0.8.19;")
        assert _extract_pragma_version(path) == "0.8.19"

    def test_exact_version(self, tmp_path):
        path = _write(tmp_path, "pragma solidity 0.8.4;")
        assert _extract_pragma_version(path) == "0.8.4"

    def test_range_version_picks_first_bound(self, tmp_path):
        path = _write(tmp_path, "pragma solidity >=0.7.0 <0.9.0;")
        assert _extract_pragma_version(path) == "0.7.0"

    def test_no_pragma_returns_none(self, tmp_path):
        path = tmp_path / "NoPragma.sol"
        path.write_text("contract C {}\n")
        assert _extract_pragma_version(path) is None


class TestEnsureSolcVersion:
    def test_missing_solc_select_warns_and_does_not_raise(self, tmp_path, monkeypatch, caplog):
        path = _write(tmp_path, "pragma solidity ^0.8.19;")

        def fake_run(*args, **kwargs):
            raise FileNotFoundError()

        monkeypatch.setattr(subprocess, "run", fake_run)
        with caplog.at_level("WARNING"):
            ensure_solc_version(path)  # 예외를 던지면 안 됨
        assert "solc-select" in caplog.text

    def test_no_pragma_skips_solc_select(self, tmp_path, monkeypatch):
        path = tmp_path / "NoPragma.sol"
        path.write_text("contract C {}\n")

        called = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: called.append(1))
        ensure_solc_version(path)
        assert called == []

    def test_installed_version_returns_binary_path(self, tmp_path, monkeypatch):
        path = _write(tmp_path, "pragma solidity ^0.8.19;")
        fake_bin = tmp_path / "solc-0.8.19"
        fake_bin.write_text("fake binary")

        monkeypatch.setattr(subprocess, "run", lambda *a, **k: None)
        monkeypatch.setattr(
            "auditor.analyzers.slither_runner.artifact_path", lambda v: fake_bin
        )
        assert ensure_solc_version(path) == str(fake_bin)

    def test_never_calls_solc_select_use(self, tmp_path, monkeypatch):
        """
        회귀 테스트(2026-08): 예전엔 `solc-select use <version>`으로 전역 solc
        버전을 전환했는데, 동시 실행(웹 백엔드에서 서로 다른 pragma 버전을 동시에
        분석) 시 레이스 컨디션이 되어 --solc 플래그로 바꿨다. 'use' subprocess
        호출이 다시 생기면 안 된다.
        """
        path = _write(tmp_path, "pragma solidity ^0.8.19;")
        fake_bin = tmp_path / "solc-0.8.19"
        fake_bin.write_text("fake binary")

        calls = []
        monkeypatch.setattr(subprocess, "run", lambda cmd, **k: calls.append(cmd))
        monkeypatch.setattr(
            "auditor.analyzers.slither_runner.artifact_path", lambda v: fake_bin
        )
        ensure_solc_version(path)
        assert all("use" not in cmd for cmd in calls)

    def test_missing_binary_after_install_returns_none(self, tmp_path, monkeypatch, caplog):
        path = _write(tmp_path, "pragma solidity ^0.8.19;")
        missing_bin = tmp_path / "does-not-exist"

        monkeypatch.setattr(subprocess, "run", lambda *a, **k: None)
        monkeypatch.setattr(
            "auditor.analyzers.slither_runner.artifact_path", lambda v: missing_bin
        )
        with caplog.at_level("WARNING"):
            assert ensure_solc_version(path) is None
        assert "찾을 수 없어" in caplog.text

    def test_solc_select_package_unavailable_returns_none(self, tmp_path, monkeypatch, caplog):
        path = _write(tmp_path, "pragma solidity ^0.8.19;")
        monkeypatch.setattr("auditor.analyzers.slither_runner.artifact_path", None)

        called = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: called.append(1))
        with caplog.at_level("WARNING"):
            assert ensure_solc_version(path) is None
        assert called == []  # solc-select install조차 호출하면 안 됨
        assert "solc-select" in caplog.text


class TestRunSlither:
    def test_missing_output_file_raises_runtime_error(self, tmp_path, monkeypatch):
        sol = _write(tmp_path, "pragma solidity ^0.8.19;")
        out = tmp_path / "out.json"

        monkeypatch.setattr(
            "auditor.analyzers.slither_runner.ensure_solc_version", lambda p: None
        )

        class FakeResult:
            stderr = "boom"
            returncode = 1

        monkeypatch.setattr(subprocess, "run", lambda *a, **k: FakeResult())

        with pytest.raises(RuntimeError):
            run_slither(str(sol), str(out))

    def test_passes_timeout_through_to_subprocess(self, tmp_path, monkeypatch):
        sol = _write(tmp_path, "pragma solidity ^0.8.19;")
        out = tmp_path / "out.json"

        monkeypatch.setattr(
            "auditor.analyzers.slither_runner.ensure_solc_version", lambda p: None
        )

        captured = {}

        def fake_run(cmd, **kwargs):
            captured["timeout"] = kwargs.get("timeout")
            out.write_text("{}")
            return object()

        monkeypatch.setattr(subprocess, "run", fake_run)
        run_slither(str(sol), str(out), timeout=42)
        assert captured["timeout"] == 42

    def test_appends_solc_flag_when_version_resolved(self, tmp_path, monkeypatch):
        sol = _write(tmp_path, "pragma solidity ^0.8.19;")
        out = tmp_path / "out.json"

        monkeypatch.setattr(
            "auditor.analyzers.slither_runner.ensure_solc_version",
            lambda p: "/fake/solc-0.8.19",
        )

        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            out.write_text("{}")
            return object()

        monkeypatch.setattr(subprocess, "run", fake_run)
        run_slither(str(sol), str(out))
        wrapped = captured["cmd"]
        assert wrapped[0] == "/bin/sh"
        assert "--solc /fake/solc-0.8.19" in wrapped[2]

    def test_omits_solc_flag_when_version_unresolved(self, tmp_path, monkeypatch):
        sol = _write(tmp_path, "pragma solidity ^0.8.19;")
        out = tmp_path / "out.json"

        monkeypatch.setattr(
            "auditor.analyzers.slither_runner.ensure_solc_version", lambda p: None
        )

        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            out.write_text("{}")
            return object()

        monkeypatch.setattr(subprocess, "run", fake_run)
        run_slither(str(sol), str(out))
        assert "--solc" not in captured["cmd"][2]


class TestWrapWithResourceLimits:
    """
    회귀 테스트(2026-08): 업로드된(신뢰할 수 없는) 컨트랙트를 분석하는 subprocess가
    무제한 CPU/메모리를 먹는 걸 막기 위해 셸 ulimit으로 감싼다. preexec_fn 방식은
    멀티스레드 프로세스(웹 백엔드)에서 fork 데드락 위험이 있어 쓰지 않기로 했다.
    """

    def test_wraps_in_posix_shell_with_ulimits(self, monkeypatch):
        monkeypatch.setattr("os.name", "posix")
        wrapped = _wrap_with_resource_limits(["slither", "a.sol", "--json", "out.json"])
        assert wrapped[0] == "/bin/sh"
        assert wrapped[1] == "-c"
        assert "ulimit -t" in wrapped[2]
        assert "ulimit -v" in wrapped[2]
        assert "exec slither a.sol --json out.json" in wrapped[2]

    def test_quotes_arguments_with_special_characters(self, monkeypatch):
        monkeypatch.setattr("os.name", "posix")
        wrapped = _wrap_with_resource_limits(["slither", "path with space.sol"])
        assert "'path with space.sol'" in wrapped[2]

    def test_non_posix_returns_command_unchanged(self, monkeypatch):
        monkeypatch.setattr("os.name", "nt")
        cmd = ["slither", "a.sol"]
        assert _wrap_with_resource_limits(cmd) == cmd
