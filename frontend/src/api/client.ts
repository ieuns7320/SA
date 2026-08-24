import type { AnnotatedSourceResponse, JobCreatedResponse, JobStatusResponse } from "./types";

async function extractErrorDetail(resp: Response): Promise<string> {
  const body: unknown = await resp.json().catch(() => null);
  if (body && typeof body === "object" && "detail" in body) {
    return String((body as { detail: unknown }).detail);
  }
  return `요청에 실패했습니다 (${resp.status})`;
}

async function postJob(form: FormData): Promise<JobCreatedResponse> {
  const resp = await fetch("/api/jobs", {
    method: "POST",
    body: form,
    credentials: "include",
  });
  if (!resp.ok) {
    throw new Error(await extractErrorDetail(resp));
  }
  return resp.json() as Promise<JobCreatedResponse>;
}

export function createJobByAddress(address: string): Promise<JobCreatedResponse> {
  const form = new FormData();
  form.append("address", address);
  return postJob(form);
}

export function createJobByFile(file: File): Promise<JobCreatedResponse> {
  const form = new FormData();
  form.append("file", file);
  return postJob(form);
}

export async function getJobStatus(jobId: string): Promise<JobStatusResponse> {
  const resp = await fetch(`/api/jobs/${jobId}`, { credentials: "include" });
  if (!resp.ok) {
    throw new Error(await extractErrorDetail(resp));
  }
  return resp.json() as Promise<JobStatusResponse>;
}

export async function getJobReport(jobId: string): Promise<string> {
  const resp = await fetch(`/api/jobs/${jobId}/report`, { credentials: "include" });
  if (!resp.ok) {
    throw new Error(await extractErrorDetail(resp));
  }
  return resp.text();
}

export async function getJobSource(jobId: string): Promise<AnnotatedSourceResponse> {
  const resp = await fetch(`/api/jobs/${jobId}/source`, { credentials: "include" });
  if (!resp.ok) {
    throw new Error(await extractErrorDetail(resp));
  }
  return resp.json() as Promise<AnnotatedSourceResponse>;
}

export async function listJobs(): Promise<JobStatusResponse[]> {
  const resp = await fetch("/api/jobs", { credentials: "include" });
  if (!resp.ok) {
    throw new Error(await extractErrorDetail(resp));
  }
  return resp.json() as Promise<JobStatusResponse[]>;
}
