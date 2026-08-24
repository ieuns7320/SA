import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { getJobSource } from "../api/client";
import type { AnnotatedSourceResponse } from "../api/types";
import { CodeViewer } from "../components/CodeViewer";
import { ReportView } from "../components/ReportView";

type Tab = "code" | "report";

export function JobResultPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get("tab");
  const tab: Tab = requestedTab === "report" ? "report" : "code";

  const [source, setSource] = useState<AnnotatedSourceResponse | null>(null);
  const [sourceError, setSourceError] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId || tab !== "code" || source) return;
    let cancelled = false;

    getJobSource(jobId)
      .then((data) => {
        if (!cancelled) setSource(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setSourceError(err instanceof Error ? err.message : "코드를 불러오지 못했습니다.");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [jobId, tab, source]);

  if (!jobId) return null;

  function selectTab(next: Tab) {
    setSearchParams(next === "code" ? {} : { tab: next }, { replace: true });
  }

  return (
    <div className="page job-result-page">
      <div className="report-toolbar">
        <Link to="/" className="back-link">
          ← 새 분석 시작
        </Link>
      </div>

      <div className="tab-bar">
        <button
          type="button"
          className={`tab-button ${tab === "code" ? "active" : ""}`}
          onClick={() => selectTab("code")}
        >
          코드 보기
        </button>
        <button
          type="button"
          className={`tab-button ${tab === "report" ? "active" : ""}`}
          onClick={() => selectTab("report")}
        >
          리포트
        </button>
      </div>

      <div className="card job-result-card">
        {tab === "code" && (
          <>
            {sourceError && (
              <div>
                <p className="error">{sourceError}</p>
                <button type="button" className="btn-secondary" onClick={() => selectTab("report")}>
                  리포트 보기
                </button>
              </div>
            )}
            {!sourceError && !source && <p className="muted">코드를 불러오는 중...</p>}
            {source && <CodeViewer files={source.source_files} findings={source.findings} />}
          </>
        )}
        {tab === "report" && <ReportView jobId={jobId} />}
      </div>
    </div>
  );
}
