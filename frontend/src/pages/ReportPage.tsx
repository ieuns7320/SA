import { Navigate, useParams } from "react-router-dom";

/**
 * 예전 리포트 전용 URL(/jobs/:id/report) 호환용 리다이렉트. 코드 뷰어가 주
 * 화면이 된 뒤로는 실제 렌더링은 JobResultPage의 리포트 탭이 담당한다 —
 * 북마크/공유된 옛 링크가 계속 동작하게 하기 위해 라우트 자체는 남겨둔다.
 */
export function ReportPage() {
  const { jobId } = useParams<{ jobId: string }>();
  return <Navigate to={`/jobs/${jobId}/view?tab=report`} replace />;
}
