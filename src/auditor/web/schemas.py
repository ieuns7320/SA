"""API 요청/응답 Pydantic 모델."""

from pydantic import BaseModel


class JobCreatedResponse(BaseModel):
    job_id: str
    status: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    target_display: str
    created_at: str
    updated_at: str
    error_message: str | None = None


class FindingOut(BaseModel):
    id: str
    check: str
    impact: str
    confidence: str
    file: str
    start_line: int
    end_line: int
    lines: str
    summary: str
    title: str
    explanation: str
    remediation: str
    severity: str
    code_snippet: str


class SourceFileOut(BaseModel):
    path: str
    content: str
    truncated: bool = False


class AnnotatedSourceResponse(BaseModel):
    contract_file: str
    total_findings: int
    findings: list[FindingOut]
    source_files: list[SourceFileOut]
