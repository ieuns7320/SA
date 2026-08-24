export type JobStatus = "queued" | "running" | "succeeded" | "failed";

export interface JobCreatedResponse {
  job_id: string;
  status: JobStatus;
}

export interface JobStatusResponse {
  job_id: string;
  status: JobStatus;
  target_display: string;
  created_at: string;
  updated_at: string;
  error_message: string | null;
}

export interface FindingOut {
  id: string;
  check: string;
  impact: string;
  confidence: string;
  file: string;
  start_line: number;
  end_line: number;
  lines: string;
  summary: string;
  title: string;
  explanation: string;
  remediation: string;
  severity: string;
  code_snippet: string;
}

export interface SourceFileOut {
  path: string;
  content: string;
  truncated: boolean;
}

export interface AnnotatedSourceResponse {
  contract_file: string;
  total_findings: number;
  findings: FindingOut[];
  source_files: SourceFileOut[];
}
