import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listJobs } from "../api/client";
import type { JobStatusResponse } from "../api/types";

const STATUS_LABEL: Record<string, string> = {
  queued: "대기중",
  running: "분석중",
  succeeded: "완료",
  failed: "실패",
};

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("ko-KR", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function HistoryPage() {
  const [jobs, setJobs] = useState<JobStatusResponse[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listJobs()
      .then((data) => {
        if (!cancelled) setJobs(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "히스토리를 불러오지 못했습니다.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="page">
      <h1>분석 히스토리</h1>
      <p className="subtitle">이 브라우저 세션에서 지금까지 제출한 분석 기록이에요.</p>

      {error && (
        <div className="card">
          <p className="error">{error}</p>
        </div>
      )}

      {!error && jobs === null && (
        <div className="card">
          <p className="muted">불러오는 중...</p>
        </div>
      )}

      {!error && jobs !== null && jobs.length === 0 && (
        <div className="card">
          <p className="muted">아직 분석 기록이 없어요.</p>
          <Link to="/">첫 분석 시작하기 →</Link>
        </div>
      )}

      {jobs && jobs.length > 0 && (
        <ul className="history-list">
          {jobs.map((job) => (
            <li key={job.job_id}>
              <Link to={`/jobs/${job.job_id}`} className="history-item">
                <div className="history-item-main">
                  <span className="history-target">{job.target_display}</span>
                  <span className="history-date">{formatDate(job.created_at)}</span>
                </div>
                <span className={`status-badge status-${job.status}`}>
                  {STATUS_LABEL[job.status] ?? job.status}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
