"""POST /api/jobs, GET /api/jobs/{id}, GET /api/jobs/{id}/report, GET /api/jobs/{id}/source"""

import json
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import PlainTextResponse

from auditor.report.generator import enrich_finding, load_explanations
from auditor.web import db, ratelimit, uploads
from auditor.web import jobs as job_runner
from auditor.web.schemas import AnnotatedSourceResponse, JobCreatedResponse, JobStatusResponse
from auditor.web.session import get_session_id

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

ADDRESS_PATTERN = re.compile(r"^0x[a-fA-F0-9]{40}$")

# 공유 Etherscan 키/제한된 slither 동시 실행 슬롯을 여러 익명 사용자가 나눠 쓰므로
# 세션+IP 둘 다 체크한다 — 정확한 수치는 운영하면서 조정할 placeholder.
SESSION_RATE_LIMIT = 10
SESSION_RATE_WINDOW = 3600.0
IP_RATE_LIMIT = 30
IP_RATE_WINDOW = 3600.0


@router.post("", status_code=201, response_model=JobCreatedResponse)
async def create_job(
    request: Request,
    response: Response,
    address: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    session_id: str = Depends(get_session_id),
) -> JobCreatedResponse:
    if bool(address) == bool(file):
        raise HTTPException(400, "address 또는 file 중 정확히 하나를 제공해야 합니다.")

    client_ip = request.client.host if request.client else "unknown"
    if not ratelimit.check(f"session:{session_id}", SESSION_RATE_LIMIT, SESSION_RATE_WINDOW):
        raise HTTPException(429, "요청이 너무 많습니다. 잠시 후 다시 시도하세요.")
    if not ratelimit.check(f"ip:{client_ip}", IP_RATE_LIMIT, IP_RATE_WINDOW):
        raise HTTPException(429, "요청이 너무 많습니다. 잠시 후 다시 시도하세요.")

    job_id = uuid.uuid4().hex
    job_dir = job_runner.REPORTS_ROOT / job_id

    if address:
        if not ADDRESS_PATTERN.match(address):
            raise HTTPException(400, f"올바른 컨트랙트 주소 형식이 아닙니다: {address}")
        db.create_job(job_id, session_id, "address", address)
        target = address
    else:
        assert file is not None
        try:
            content = await uploads.read_and_validate_upload(file)
        except uploads.UploadTooLarge as e:
            raise HTTPException(413, str(e)) from e
        except uploads.InvalidUpload as e:
            raise HTTPException(400, str(e)) from e

        filename = uploads.safe_filename(file)
        job_dir.mkdir(parents=True, exist_ok=True)
        saved_path = job_dir / filename
        saved_path.write_bytes(content)

        db.create_job(job_id, session_id, "file", filename)
        target = str(saved_path)

    job_runner.submit_job(request.app.state.executor, job_id, target)
    return JobCreatedResponse(job_id=job_id, status="queued")


@router.get("", response_model=list[JobStatusResponse])
def list_jobs(session_id: str = Depends(get_session_id)) -> list[JobStatusResponse]:
    """현재 세션이 지금까지 제출한 job을 최신순으로 반환한다 (히스토리 화면용)."""
    rows = db.list_jobs_by_session(session_id)
    return [
        JobStatusResponse(
            job_id=row["id"],
            status=row["status"],
            target_display=row["target_display"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            error_message=row["error_message"],
        )
        for row in rows
    ]


@router.get("/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str, session_id: str = Depends(get_session_id)) -> JobStatusResponse:
    row = db.get_job(job_id, session_id)
    if row is None:
        raise HTTPException(404, "job을 찾을 수 없습니다.")
    return JobStatusResponse(
        job_id=row["id"],
        status=row["status"],
        target_display=row["target_display"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        error_message=row["error_message"],
    )


@router.get("/{job_id}/report")
def get_job_report(job_id: str, session_id: str = Depends(get_session_id)) -> PlainTextResponse:
    row = db.get_job(job_id, session_id)
    if row is None:
        raise HTTPException(404, "job을 찾을 수 없습니다.")
    if row["status"] != "succeeded":
        raise HTTPException(409, f"아직 완료되지 않았습니다 (status={row['status']}).")

    report_path = Path(row["report_path"])
    if not report_path.exists():
        raise HTTPException(404, "리포트 파일을 찾을 수 없습니다.")

    return PlainTextResponse(report_path.read_text(encoding="utf-8"), media_type="text/markdown")


@router.get("/{job_id}/source", response_model=AnnotatedSourceResponse)
def get_job_source(job_id: str, session_id: str = Depends(get_session_id)) -> AnnotatedSourceResponse:
    row = db.get_job(job_id, session_id)
    if row is None:
        raise HTTPException(404, "job을 찾을 수 없습니다.")
    if row["status"] != "succeeded":
        raise HTTPException(409, f"아직 완료되지 않았습니다 (status={row['status']}).")

    findings_path_str = row["findings_path"]
    if not findings_path_str:
        # 이 기능(코드 뷰어) 도입 이전에 완료된 job — findings.json이 없어
        # 리포트 탭만 제공 가능하다. 백필하지 않는다.
        raise HTTPException(404, "이 분석 결과는 코드 뷰어를 지원하지 않습니다. 리포트를 확인하세요.")

    findings_path = Path(findings_path_str)
    if not findings_path.exists():
        raise HTTPException(404, "분석 결과 파일을 찾을 수 없습니다.")

    data = json.loads(findings_path.read_text(encoding="utf-8"))
    explanations = load_explanations()
    enriched_findings = [enrich_finding(f, explanations) for f in data["findings"]]

    return AnnotatedSourceResponse(
        contract_file=data["contract_file"],
        total_findings=data["total_findings"],
        findings=enriched_findings,
        source_files=data.get("source_files", []),
    )
