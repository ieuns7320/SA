"""run_pipeline()의 반환 타입.

report.md 하나만 반환하던 걸 findings.json(코드 뷰어용 구조화 데이터) 경로까지
함께 반환하도록 확장한다. cli.py/cache.py 양쪽에서 참조하므로 순환 임포트를
피하려고 별도 모듈로 둔다.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class PipelineResult:
    report_path: Path
    findings_path: Path
