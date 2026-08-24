"""job 실행: ThreadPoolExecutor로 기존 run_pipeline()을 감싸서 백그라운드로 돌린다.

run_pipeline() 자체는 무수정 — job별 work_dir(reports/<job_id>/)만 다르게 넘겨서,
동시에 여러 사용자가 같은 이름의 컨트랙트를 분석해도 파일이 섞이지 않게 한다.
동시성 캡은 ThreadPoolExecutor의 max_workers 하나로 해결한다 (Redis/Celery 불필요
— submit()은 풀이 꽉 차도 논블로킹이고 초과분은 executor 내부 큐에서 대기한다).
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from auditor.cli import run_pipeline
from auditor.web import db

logger = logging.getLogger(__name__)

REPORTS_ROOT = Path("reports")


def create_executor(max_workers: int) -> ThreadPoolExecutor:
    return ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="job-worker")


def submit_job(executor: ThreadPoolExecutor, job_id: str, target: str) -> None:
    """job을 백그라운드 실행 큐에 넣고 즉시 반환한다."""
    executor.submit(_execute_job, job_id, target)


def _execute_job(job_id: str, target: str) -> None:
    job_dir = REPORTS_ROOT / job_id
    db.update_job_status(job_id, "running")
    try:
        result = run_pipeline(target, work_dir=str(job_dir))
        db.update_job_status(
            job_id,
            "succeeded",
            report_path=str(result.report_path),
            findings_path=str(result.findings_path),
        )
    except Exception as e:
        logger.exception("job %s 실패", job_id)
        db.update_job_status(job_id, "failed", error_message=str(e))
