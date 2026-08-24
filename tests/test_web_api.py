"""auditor.web 백엔드 API 통합 테스트 (FastAPI TestClient).

run_pipeline은 대부분의 테스트에서 모킹해서 실제 slither를 태우지 않는다
(빠르고 결정적). 실제 slither까지 태우는 end-to-end 테스트는 맨 아래
TestRealPipeline 하나뿐이며, slither 미설치 환경에선 자동 skip된다.
"""

import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from auditor.pipeline_types import PipelineResult
from auditor.web import db as web_db
from auditor.web import jobs as job_runner
from auditor.web import ratelimit
from auditor.web.app import create_app

FIXTURE = Path(__file__).parent / "fixtures" / "contracts" / "vulnerable_vault.sol"
SLITHER_AVAILABLE = shutil.which("slither") is not None

VALID_SOL = b'// SPDX-License-Identifier: MIT\npragma solidity ^0.8.19;\ncontract C { function f() public {} }\n'


@pytest.fixture
def web_env(tmp_path, monkeypatch):
    monkeypatch.setattr(web_db, "DB_PATH", tmp_path / "jobs.sqlite3")
    monkeypatch.setattr(job_runner, "REPORTS_ROOT", tmp_path / "reports")
    monkeypatch.setattr(ratelimit, "_hits", {})
    return tmp_path


def _write_fake_findings(d: Path, target: str) -> Path:
    import json

    findings_path = d / "fake.findings.json"
    findings_path.write_text(
        json.dumps({
            "contract_file": "fake.sol",
            "total_findings": 1,
            "findings": [{
                "id": "reentrancy-eth-10",
                "check": "reentrancy-eth",
                "impact": "High",
                "confidence": "Medium",
                "file": "fake.sol",
                "lines": "10-12",
                "start_line": 10,
                "end_line": 12,
                "summary": "재진입 가능성",
                "code_snippet": "10: function withdraw() public {}",
            }],
            "source_files": [{"path": "fake.sol", "content": "contract C {}"}],
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    return findings_path


@pytest.fixture
def mock_pipeline(monkeypatch):
    """run_pipeline을 빠른 가짜 구현으로 대체 — 실제 slither를 태우지 않는다."""

    def fake_run_pipeline(target: str, work_dir: str = "reports") -> PipelineResult:
        d = Path(work_dir)
        d.mkdir(parents=True, exist_ok=True)
        report = d / "fake.report.md"
        report.write_text(
            f"# 보안 분석 리포트 — {target}\n\n**LLM 판단 없이 자동 생성**되었습니다.\n"
        )
        findings_path = _write_fake_findings(d, target)
        return PipelineResult(report_path=report, findings_path=findings_path)

    monkeypatch.setattr(job_runner, "run_pipeline", fake_run_pipeline)
    return fake_run_pipeline


@pytest.fixture
def client(web_env):
    app = create_app()
    with TestClient(app) as c:
        yield c


def _wait_for_terminal_status(client: TestClient, job_id: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(f"/api/jobs/{job_id}")
        body = resp.json()
        if body["status"] in ("succeeded", "failed"):
            return body
        time.sleep(0.02)
    raise AssertionError(f"job {job_id}이 {timeout}초 안에 끝나지 않음")


class TestCreateJobValidation:
    def test_requires_exactly_one_of_address_or_file(self, client, mock_pipeline):
        resp = client.post("/api/jobs")
        assert resp.status_code == 400

    def test_rejects_both_address_and_file(self, client, mock_pipeline):
        resp = client.post(
            "/api/jobs",
            data={"address": "0x" + "a" * 40},
            files={"file": ("C.sol", VALID_SOL, "text/plain")},
        )
        assert resp.status_code == 400

    def test_rejects_invalid_address_format(self, client, mock_pipeline):
        resp = client.post("/api/jobs", data={"address": "not-an-address"})
        assert resp.status_code == 400


class TestJobLifecycleByAddress:
    def test_submit_and_poll_to_success(self, client, mock_pipeline):
        address = "0x" + "a" * 40
        create_resp = client.post("/api/jobs", data={"address": address})
        assert create_resp.status_code == 201
        job_id = create_resp.json()["job_id"]
        assert create_resp.json()["status"] == "queued"

        status = _wait_for_terminal_status(client, job_id)
        assert status["status"] == "succeeded"
        assert status["target_display"] == address

        report_resp = client.get(f"/api/jobs/{job_id}/report")
        assert report_resp.status_code == 200
        assert "LLM 판단 없이 자동 생성" in report_resp.text

    def test_sets_session_cookie_on_first_submit(self, client, mock_pipeline):
        address = "0x" + "b" * 40
        resp = client.post("/api/jobs", data={"address": address})
        assert "sid" in resp.cookies

    def test_report_not_ready_returns_409(self, client, monkeypatch):
        """job이 아직 안 끝났을 때 리포트를 요청하면 409."""
        import threading

        gate = threading.Event()

        def slow_pipeline(target: str, work_dir: str = "reports") -> PipelineResult:
            gate.wait(timeout=5)
            d = Path(work_dir)
            d.mkdir(parents=True, exist_ok=True)
            report = d / "fake.report.md"
            report.write_text("# 리포트\n")
            findings_path = _write_fake_findings(d, target)
            return PipelineResult(report_path=report, findings_path=findings_path)

        monkeypatch.setattr(job_runner, "run_pipeline", slow_pipeline)
        try:
            resp = client.post("/api/jobs", data={"address": "0x" + "c" * 40})
            job_id = resp.json()["job_id"]
            report_resp = client.get(f"/api/jobs/{job_id}/report")
            assert report_resp.status_code == 409
        finally:
            gate.set()


class TestJobFailure:
    def test_pipeline_exception_surfaces_as_failed_with_message(self, client, monkeypatch):
        def failing_pipeline(target: str, work_dir: str = "reports") -> Path:
            raise RuntimeError(f"컨트랙트 {target}는 검증되지 않았습니다 (소스 비공개).")

        monkeypatch.setattr(job_runner, "run_pipeline", failing_pipeline)

        resp = client.post("/api/jobs", data={"address": "0x" + "d" * 40})
        job_id = resp.json()["job_id"]

        status = _wait_for_terminal_status(client, job_id)
        assert status["status"] == "failed"
        assert "검증되지 않았습니다" in status["error_message"]

        report_resp = client.get(f"/api/jobs/{job_id}/report")
        assert report_resp.status_code == 409


class TestJobSource:
    """GET /api/jobs/{id}/source — 코드 뷰어용 구조화된 findings+소스 엔드포인트."""

    def test_returns_enriched_findings_and_source_files(self, client, mock_pipeline):
        address = "0x" + "f" * 40
        create_resp = client.post("/api/jobs", data={"address": address})
        job_id = create_resp.json()["job_id"]
        _wait_for_terminal_status(client, job_id)

        resp = client.get(f"/api/jobs/{job_id}/source")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_findings"] == 1
        assert body["source_files"] == [{"path": "fake.sol", "content": "contract C {}"}]
        finding = body["findings"][0]
        assert finding["check"] == "reentrancy-eth"
        assert finding["start_line"] == 10
        assert finding["end_line"] == 12
        # enrich_finding()이 detector_explanations.json에서 붙이는 필드들.
        assert finding["title"]
        assert finding["explanation"]
        assert finding["remediation"]
        assert finding["severity"]

    def test_not_yet_succeeded_returns_409(self, client, monkeypatch):
        import threading

        gate = threading.Event()

        def slow_pipeline(target: str, work_dir: str = "reports") -> PipelineResult:
            gate.wait(timeout=5)
            d = Path(work_dir)
            d.mkdir(parents=True, exist_ok=True)
            report = d / "fake.report.md"
            report.write_text("# 리포트\n")
            findings_path = _write_fake_findings(d, target)
            return PipelineResult(report_path=report, findings_path=findings_path)

        monkeypatch.setattr(job_runner, "run_pipeline", slow_pipeline)
        try:
            resp = client.post("/api/jobs", data={"address": "0x" + "1" * 40})
            job_id = resp.json()["job_id"]
            source_resp = client.get(f"/api/jobs/{job_id}/source")
            assert source_resp.status_code == 409
        finally:
            gate.set()

    def test_other_session_cannot_see_source(self, client, mock_pipeline):
        address = "0x" + "2" * 40
        create_resp = client.post("/api/jobs", data={"address": address})
        job_id = create_resp.json()["job_id"]
        _wait_for_terminal_status(client, job_id)

        other_client = TestClient(client.app)
        resp = other_client.get(f"/api/jobs/{job_id}/source")
        assert resp.status_code == 404

    def test_unknown_job_id_returns_404(self, client, mock_pipeline):
        resp = client.get("/api/jobs/does-not-exist/source")
        assert resp.status_code == 404


class TestSessionIsolation:
    def test_other_session_cannot_see_job(self, client, mock_pipeline):
        address = "0x" + "e" * 40
        create_resp = client.post("/api/jobs", data={"address": address})
        job_id = create_resp.json()["job_id"]

        other_client = TestClient(client.app)  # 쿠키를 공유하지 않는 새 클라이언트
        resp = other_client.get(f"/api/jobs/{job_id}")
        assert resp.status_code == 404

    def test_unknown_job_id_returns_404(self, client, mock_pipeline):
        resp = client.get("/api/jobs/does-not-exist")
        assert resp.status_code == 404


class TestJobHistory:
    def test_lists_own_jobs_newest_first(self, client, mock_pipeline):
        addr1 = "0x" + "1" * 40
        addr2 = "0x" + "2" * 40
        job1 = client.post("/api/jobs", data={"address": addr1}).json()["job_id"]
        job2 = client.post("/api/jobs", data={"address": addr2}).json()["job_id"]
        _wait_for_terminal_status(client, job1)
        _wait_for_terminal_status(client, job2)

        resp = client.get("/api/jobs")
        assert resp.status_code == 200
        job_ids = [j["job_id"] for j in resp.json()]
        assert job_ids[:2] == [job2, job1]

    def test_does_not_leak_other_sessions_jobs(self, client, mock_pipeline):
        client.post("/api/jobs", data={"address": "0x" + "3" * 40})

        other_client = TestClient(client.app)
        resp = other_client.get("/api/jobs")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_empty_history_for_fresh_session(self, client):
        resp = client.get("/api/jobs")
        assert resp.status_code == 200
        assert resp.json() == []


class TestFileUpload:
    def test_valid_sol_upload_succeeds(self, client, mock_pipeline):
        resp = client.post(
            "/api/jobs", files={"file": ("Vault.sol", VALID_SOL, "text/plain")}
        )
        assert resp.status_code == 201
        job_id = resp.json()["job_id"]
        status = _wait_for_terminal_status(client, job_id)
        assert status["status"] == "succeeded"
        assert status["target_display"] == "Vault.sol"

    def test_rejects_non_sol_extension(self, client, mock_pipeline):
        resp = client.post(
            "/api/jobs", files={"file": ("Vault.txt", VALID_SOL, "text/plain")}
        )
        assert resp.status_code == 400

    def test_rejects_non_solidity_content(self, client, mock_pipeline):
        resp = client.post(
            "/api/jobs",
            files={"file": ("Vault.sol", b"just some random text", "text/plain")},
        )
        assert resp.status_code == 400

    def test_rejects_oversized_file(self, client, mock_pipeline, monkeypatch):
        from auditor.web import uploads

        monkeypatch.setattr(uploads, "MAX_UPLOAD_BYTES", 10)
        resp = client.post(
            "/api/jobs", files={"file": ("Vault.sol", VALID_SOL, "text/plain")}
        )
        assert resp.status_code == 413

    def test_path_traversal_filename_is_sanitized(self, client, mock_pipeline, web_env):
        resp = client.post(
            "/api/jobs",
            files={"file": ("../../evil.sol", VALID_SOL, "text/plain")},
        )
        assert resp.status_code == 201
        job_id = resp.json()["job_id"]
        _wait_for_terminal_status(client, job_id)
        # job 디렉토리 밖으로 파일이 새어나가지 않았어야 한다
        job_dir = job_runner.REPORTS_ROOT / job_id
        assert (job_dir / "evil.sol").exists()
        assert not (web_env / "evil.sol").exists()


class TestRateLimit:
    def test_session_rate_limit_returns_429(self, client, mock_pipeline, monkeypatch):
        import auditor.web.routers.jobs as jobs_router

        monkeypatch.setattr(jobs_router, "SESSION_RATE_LIMIT", 2)

        for i in range(2):
            resp = client.post("/api/jobs", data={"address": "0x" + str(i) * 40})
            assert resp.status_code == 201

        resp = client.post("/api/jobs", data={"address": "0x" + "f" * 40})
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers or resp.status_code == 429


@pytest.mark.skipif(not SLITHER_AVAILABLE, reason="slither가 설치되어 있지 않음")
class TestRealPipeline:
    def test_upload_vulnerable_vault_end_to_end(self, client):
        """모킹 없이 실제 slither를 태워서 웹 API 전체 경로를 검증한다."""
        content = FIXTURE.read_bytes()
        resp = client.post(
            "/api/jobs", files={"file": ("vulnerable_vault.sol", content, "text/plain")}
        )
        assert resp.status_code == 201
        job_id = resp.json()["job_id"]

        status = _wait_for_terminal_status(client, job_id, timeout=60)
        assert status["status"] == "succeeded", status.get("error_message")

        report_resp = client.get(f"/api/jobs/{job_id}/report")
        assert report_resp.status_code == 200
        assert "보안 분석 리포트" in report_resp.text

        source_resp = client.get(f"/api/jobs/{job_id}/source")
        assert source_resp.status_code == 200
        body = source_resp.json()
        assert body["total_findings"] > 0
        assert body["source_files"][0]["path"] == "vulnerable_vault.sol"
        first = body["findings"][0]
        assert isinstance(first["start_line"], int)
        assert isinstance(first["end_line"], int)
        assert first["title"]
        assert first["explanation"]
