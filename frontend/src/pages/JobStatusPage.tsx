import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { getJobStatus } from "../api/client";
import type { JobStatusResponse } from "../api/types";

const POLL_INTERVAL_MS = 2000;

const STATUS_LABEL: Record<string, string> = {
  queued: "대기중",
  running: "분석중",
  succeeded: "완료",
  failed: "실패",
};

export function JobStatusPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const [status, setStatus] = useState<JobStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    async function poll() {
      try {
        const data = await getJobStatus(jobId!);
        if (cancelled) return;
        setStatus(data);

        if (data.status === "succeeded") {
          navigate(`/jobs/${jobId}/view`, { replace: true });
          return;
        }
        if (data.status !== "failed") {
          timer = setTimeout(poll, POLL_INTERVAL_MS);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "상태 조회에 실패했습니다.");
        }
      }
    }

    poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [jobId, navigate]);

  if (error) {
    return (
      <div className="page">
        <div className="card">
          <p className="error">{error}</p>
          <Link to="/">← 다시 시작</Link>
        </div>
      </div>
    );
  }

  if (!status) {
    return (
      <div className="page">
        <div className="card">
          <p className="muted">불러오는 중...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <h1>분석 진행 상황</h1>
      <div className="card status-card">
        {(status.status === "queued" || status.status === "running") && (
          <div className="spinner" aria-hidden="true" />
        )}
        <p className={`status-badge status-${status.status}`}>
          {STATUS_LABEL[status.status] ?? status.status}
        </p>
        <p className="target">{status.target_display}</p>

        {(status.status === "queued" || status.status === "running") && (
          <p className="hint">Slither 정적분석 중입니다. 최대 2분 정도 걸릴 수 있어요.</p>
        )}

        {status.status === "failed" && (
          <div>
            <p className="error">{status.error_message}</p>
            <Link to="/">← 다시 시작</Link>
          </div>
        )}
      </div>
    </div>
  );
}
