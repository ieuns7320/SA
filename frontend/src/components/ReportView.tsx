import { useEffect, useState } from "react";
import DOMPurify from "dompurify";
import { marked } from "marked";
import { getJobReport } from "../api/client";

interface ReportViewProps {
  jobId: string;
}

function deriveFilename(markdown: string, jobId: string): string {
  const match = markdown.match(/^# 보안 분석 리포트 — (.+)$/m);
  const base = (match ? match[1].trim() : jobId).replace(/\.sol$/i, "");
  const safe = base.replace(/[^\w.\-가-힣]+/g, "_");
  return `${safe}.report.md`;
}

export function ReportView({ jobId }: ReportViewProps) {
  const [html, setHtml] = useState<string | null>(null);
  const [downloadName, setDownloadName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    getJobReport(jobId)
      .then((markdown) => {
        if (cancelled) return;
        // 리포트 안 코드 스니펫은 사용자가 업로드/지정한 컨트랙트 소스에서 그대로
        // 뽑혀온 신뢰 안 된 텍스트다. marked가 기본적으로 이스케이프하지만,
        // DOMPurify로 한 번 더 살균한 뒤에만 innerHTML로 주입한다.
        const rawHtml = marked.parse(markdown, { async: false }) as string;
        setHtml(DOMPurify.sanitize(rawHtml));
        setDownloadName(deriveFilename(markdown, jobId));
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "리포트를 불러오지 못했습니다.");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [jobId]);

  if (error) {
    return <p className="error">{error}</p>;
  }

  if (!html) {
    return <p className="muted">리포트를 불러오는 중...</p>;
  }

  return (
    <div>
      <div className="report-toolbar">
        {/* 같은 오리진(/api/jobs/.../report)으로의 일반 네비게이션이라 쿠키가
            자동으로 실려서, fetch+blob 없이 download 속성만으로 충분하다. */}
        <a href={`/api/jobs/${jobId}/report`} download={downloadName ?? undefined} className="btn-secondary">
          ⬇ 다운로드
        </a>
      </div>
      <div className="markdown-body" dangerouslySetInnerHTML={{ __html: html }} />
    </div>
  );
}
