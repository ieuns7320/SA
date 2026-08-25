"""전체 파이프라인(입력 -> Slither -> Markdown 리포트) end-to-end 테스트.

실제 slither/solc-select를 서브프로세스로 실행하므로 이 환경에 slither가
설치되어 있지 않으면 건너뛴다. 다른 모듈의 로직 단위 테스트는 각각
test_preprocess.py / test_generator.py / test_slither_runner.py 참고.
"""

import json
import shutil
from pathlib import Path

import pytest

from auditor.cli import run_pipeline

FIXTURE = Path(__file__).parent / "fixtures" / "contracts" / "vulnerable_vault.sol"
SLITHER_AVAILABLE = shutil.which("slither") is not None


@pytest.mark.skipif(not SLITHER_AVAILABLE, reason="slither가 설치되어 있지 않음")
def test_full_pipeline_on_vulnerable_vault(tmp_path):
    result = run_pipeline(str(FIXTURE), work_dir=str(tmp_path))

    assert result.report_path.exists()
    content = result.report_path.read_text(encoding="utf-8")
    assert "보안 분석 리포트" in content
    assert "판단은 하지 않습니다" in content
    assert "재진입" in content or "reentrancy" in content.lower()

    assert result.findings_path.exists()
    findings = json.loads(result.findings_path.read_text(encoding="utf-8"))
    assert findings["total_findings"] > 0
    assert findings["source_files"]
    assert findings["source_files"][0]["path"] == "vulnerable_vault.sol"
    assert findings["source_files"][0]["content"]
    first_finding = findings["findings"][0]
    assert isinstance(first_finding["start_line"], int)
    assert isinstance(first_finding["end_line"], int)
