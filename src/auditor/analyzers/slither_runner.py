"""
Slither를 서브프로세스로 실행하고 결과 JSON 경로를 반환한다.
이 모듈은 어떤 외부 API도 호출하지 않는다 — 순수 로컬 정적분석 실행 레이어.

온체인 컨트랙트는 pragma solidity 버전이 제각각이라(예: 오래된 프록시 컨트랙트는
^0.4.24, 최신 컨트랙트는 ^0.8.x), 컴파일 전에 solc-select로 해당 버전을 자동
설치한다. solc-select가 없으면 건너뛰고 현재 solc를 그대로 사용한다.

주의: `solc-select use <version>`으로 전역 solc 버전을 전환하지 않는다 — 이 함수는
서로 다른 pragma 버전의 컨트랙트가 동시에(멀티스레드로) 분석될 수 있는 웹 백엔드에서도
쓰이는데, 전역 전환은 동시 실행 시 레이스 컨디션이 된다. 대신 solc-select가 설치한
바이너리 경로를 직접 찾아서 slither에 `--solc <경로>`로 넘긴다 — 프로세스별로 독립적이라
동시 실행이 안전하다.
"""

import logging
import os
import re
import shlex
import subprocess
import sys
import threading
from pathlib import Path

try:
    from solc_select.solc_select import artifact_path
except ImportError:
    artifact_path = None

logger = logging.getLogger(__name__)

PRAGMA_RE = re.compile(r"pragma\s+solidity\s+([^;]+);")

# 분석 대상 컨트랙트(특히 웹 UI의 업로드 파일)는 신뢰할 수 없는 입력이라, solc/slither
# subprocess가 무제한으로 CPU/메모리를 먹는 걸 막아야 한다. preexec_fn으로 resource.setrlimit을
# 거는 방식은 멀티스레드 프로세스(웹 백엔드)에서 fork 이후 데드락 위험이 있어(CPython 문서 경고)
# 쓰지 않는다 — 대신 POSIX 셸의 ulimit 빌트인으로 실제 명령을 감싸서, 제한 설정 자체가 파이썬
# 스레드 상태와 무관한 별도 셸 프로세스 안에서 이뤄지도록 한다.
_MAX_CPU_SECONDS = int(os.environ.get("SLITHER_MAX_CPU_SECONDS", "150"))
_MAX_VIRTUAL_MEMORY_KB = int(os.environ.get("SLITHER_MAX_MEMORY_KB", "3000000"))  # 약 3GB

_install_locks_guard = threading.Lock()
_install_locks: dict[str, threading.Lock] = {}


def _get_install_lock(version: str) -> threading.Lock:
    """버전별 설치 락. solc-select install 자체가 원자적이지 않아서, 같은 버전을
    동시에 처음 설치하려는 두 스레드가 파일을 동시에 쓰는 것만 직렬화한다."""
    with _install_locks_guard:
        if version not in _install_locks:
            _install_locks[version] = threading.Lock()
        return _install_locks[version]


def _extract_pragma_version(sol_path: Path) -> str | None:
    """소스에서 pragma solidity 줄을 찾아 x.y.z 형태의 버전 숫자를 뽑는다."""
    text = sol_path.read_text(errors="ignore")
    m = PRAGMA_RE.search(text)
    if not m:
        return None
    v = re.search(r"\d+\.\d+\.\d+", m.group(1))
    return v.group(0) if v else None


def ensure_solc_version(sol_path: Path) -> str | None:
    """
    컨트랙트의 pragma에 맞는 solc 버전을 solc-select로 설치하고, 그 바이너리의
    경로를 반환한다 (전역 상태는 건드리지 않음 — 모듈 docstring 참고).
    solc-select가 없거나 설치에 실패하면 None을 반환하고 경고만 출력한다
    (호출자는 시스템 solc로 폴백해서 계속 진행한다).
    """
    version = _extract_pragma_version(sol_path)
    if not version:
        return None
    if artifact_path is None:
        logger.warning(
            "solc-select 파이썬 패키지를 찾을 수 없어 버전 자동 지정을 건너뜁니다."
        )
        return None
    try:
        with _get_install_lock(version):
            subprocess.run(
                ["solc-select", "install", version],
                capture_output=True, text=True, timeout=60,
            )
        solc_bin = artifact_path(version)
        if solc_bin.exists():
            logger.info("pragma 기준 solc %s 확인 (--solc로 직접 지정)", version)
            return str(solc_bin)
        logger.warning(
            "solc %s 설치 후에도 바이너리를 찾을 수 없어 시스템 solc로 진행합니다.", version
        )
        return None
    except FileNotFoundError:
        logger.warning(
            "solc-select CLI가 설치되어 있지 않아 버전 자동 지정을 건너뜁니다. "
            "'pip install solc-select'로 설치하면 온체인 컨트랙트의 다양한 pragma 버전을 "
            "자동으로 맞출 수 있습니다."
        )
        return None
    except subprocess.TimeoutExpired:
        logger.warning("solc %s 설치가 시간 초과되었습니다.", version)
        return None


def _wrap_with_resource_limits(cmd: list[str]) -> list[str]:
    """
    실제 명령을 POSIX 셸의 ulimit으로 감싸서 CPU 시간/가상메모리 상한을 건다.
    macOS는 커널 제약으로 `ulimit -v`(가상메모리) 설정 자체를 거부하는 경우가 있는데
    (`cannot modify limit: Invalid argument`), 그 경우 에러를 무시하고 CPU 제한만 적용한다
    (best-effort — Linux 배포 환경에서는 두 제한 모두 걸린다). Windows에는 셸 ulimit이
    없으므로 원래 명령을 그대로 반환한다.
    """
    if os.name != "posix":
        return cmd
    quoted = " ".join(shlex.quote(c) for c in cmd)
    shell_cmd = (
        f"ulimit -t {_MAX_CPU_SECONDS} 2>/dev/null; "
        f"ulimit -v {_MAX_VIRTUAL_MEMORY_KB} 2>/dev/null; "
        f"exec {quoted}"
    )
    return ["/bin/sh", "-c", shell_cmd]


def run_slither(sol_path: str, output_json_path: str, timeout: int = 120) -> Path:
    """
    sol_path에 Slither를 실행하고 output_json_path에 결과를 저장한다.
    타임아웃을 반드시 지정한다 — 분석 대상 컨트랙트가 컴파일러를
    무한루프에 빠뜨릴 가능성을 고려한 안전장치.
    """
    out = Path(output_json_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    solc_bin = ensure_solc_version(Path(sol_path))

    cmd = ["slither", str(sol_path), "--json", str(out)]
    if solc_bin:
        cmd += ["--solc", solc_bin]

    result = subprocess.run(
        _wrap_with_resource_limits(cmd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    # Slither는 finding이 있으면 non-zero exit code를 반환하는 경우가 있어
    # returncode만으로 실패 여부를 판단하지 않고 output 파일 존재로 확인한다.
    if not out.exists():
        logger.error("Slither stderr:\n%s", result.stderr)
        raise RuntimeError(f"Slither 실행 실패: {sol_path}")

    return out


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("사용법: python -m auditor.analyzers.slither_runner <sol_path> <output_json_path>")
        sys.exit(1)
    path = run_slither(sys.argv[1], sys.argv[2])
    print(f"저장됨: {path}")