import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { createJobByAddress, createJobByFile } from "../api/client";

const ADDRESS_PATTERN = /^0x[a-fA-F0-9]{40}$/;

type Mode = "address" | "file";

export function SubmitPage() {
  const [mode, setMode] = useState<Mode>("address");
  const [address, setAddress] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (mode === "address") {
      if (!ADDRESS_PATTERN.test(address.trim())) {
        setError("올바른 컨트랙트 주소 형식이 아닙니다 (0x로 시작하는 40자리 16진수).");
        return;
      }
    } else if (!file) {
      setError(".sol 파일을 선택하세요.");
      return;
    }

    setSubmitting(true);
    try {
      const created =
        mode === "address"
          ? await createJobByAddress(address.trim())
          : await createJobByFile(file!);
      navigate(`/jobs/${created.job_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "요청에 실패했습니다.");
      setSubmitting(false);
    }
  }

  return (
    <div className="page">
      <h1 className="hero-title">스마트컨트랙트 보안 분석</h1>
      <p className="subtitle">
        컨트랙트 주소 또는 .sol 파일을 제출하면 Slither 정적분석 결과를 리포트로
        보여줍니다. LLM 판단 없이 규칙 기반으로 자동 생성됩니다.
      </p>

      <div className="card">
        <div className="mode-toggle" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "address"}
            className={mode === "address" ? "active" : ""}
            onClick={() => setMode("address")}
          >
            주소로 분석
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "file"}
            className={mode === "file" ? "active" : ""}
            onClick={() => setMode("file")}
          >
            파일 업로드
          </button>
        </div>

        <form onSubmit={handleSubmit} className="submit-form">
          {mode === "address" ? (
            <input
              type="text"
              placeholder="0x1234...5678"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              autoComplete="off"
              spellCheck={false}
            />
          ) : (
            <label className="file-drop">
              <input
                type="file"
                accept=".sol"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
              <span>{file ? file.name : ".sol 파일 선택"}</span>
            </label>
          )}

          {error && <p className="error">{error}</p>}

          <button type="submit" className="btn-primary" disabled={submitting}>
            {submitting ? "제출 중..." : "분석 시작"}
          </button>
        </form>
      </div>
    </div>
  );
}
