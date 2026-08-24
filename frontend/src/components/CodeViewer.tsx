import { useMemo, useRef, useState } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { EditorView } from "@codemirror/view";
import { linter, lintGutter, type Diagnostic } from "@codemirror/lint";
import { oneDark } from "@codemirror/theme-one-dark";
import { solidity } from "@replit/codemirror-lang-solidity";
import type { FindingOut, SourceFileOut } from "../api/types";
import { useTheme } from "../ThemeContext";

interface CodeViewerProps {
  files: SourceFileOut[];
  findings: FindingOut[];
}

const SEVERITY_ORDER: Record<string, number> = {
  Critical: 0,
  High: 1,
  Medium: 2,
  Low: 3,
  Informational: 4,
};

const SEVERITY_LABEL: Record<string, string> = {
  Critical: "치명적",
  High: "높음",
  Medium: "중간",
  Low: "낮음",
  Informational: "정보",
};

// Slither가 이미 매긴 severity를 에디터 진단 레벨로 표현만 바꾼다 — 새 판단이 아니다.
function severityToLintLevel(severity: string): "error" | "warning" | "info" {
  if (severity === "Critical" || severity === "High") return "error";
  if (severity === "Medium") return "warning";
  return "info";
}

function buildDiagnostics(findings: FindingOut[], activeFilePath: string) {
  return (view: EditorView): Diagnostic[] => {
    const doc = view.state.doc;
    const clamp = (n: number) => Math.min(Math.max(n, 1), doc.lines);
    return findings
      .filter((f) => f.file === activeFilePath)
      .map((f) => {
        const start = doc.line(clamp(f.start_line));
        const end = doc.line(clamp(f.end_line));
        return {
          from: start.from,
          to: Math.max(end.to, start.from),
          severity: severityToLintLevel(f.severity),
          source: f.check,
          message: `[${SEVERITY_LABEL[f.severity] ?? f.severity}] ${f.title}\n\n${f.explanation}\n\n해결 방법: ${f.remediation}`,
        } satisfies Diagnostic;
      });
  };
}

function scrollToLine(view: EditorView, line: number) {
  const doc = view.state.doc;
  const pos = doc.line(Math.min(Math.max(line, 1), doc.lines)).from;
  view.dispatch({
    selection: { anchor: pos },
    effects: EditorView.scrollIntoView(pos, { y: "center" }),
  });
  view.focus();
}

export function CodeViewer({ files, findings }: CodeViewerProps) {
  const { theme } = useTheme();
  const [activeFilePath, setActiveFilePath] = useState(files[0]?.path ?? "");
  const activeFile = files.find((f) => f.path === activeFilePath) ?? files[0];

  const viewRef = useRef<EditorView | null>(null);
  const pendingScrollLine = useRef<number | null>(null);

  const findingCountByFile = useMemo(() => {
    const counts = new Map<string, number>();
    for (const f of findings) {
      counts.set(f.file, (counts.get(f.file) ?? 0) + 1);
    }
    return counts;
  }, [findings]);

  const sortedFindings = useMemo(
    () =>
      [...findings].sort(
        (a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9)
      ),
    [findings]
  );

  const extensions = useMemo(
    () => [solidity, linter(buildDiagnostics(findings, activeFilePath)), lintGutter()],
    [findings, activeFilePath]
  );

  function jumpTo(finding: FindingOut) {
    const targetFile = files.find((f) => f.path === finding.file);
    if (targetFile?.truncated) {
      // 이 파일은 너무 커서 에디터가 아예 마운트되지 않으므로 스크롤할 대상이
      // 없다 — 파일만 전환한다.
      pendingScrollLine.current = null;
      setActiveFilePath(finding.file);
      return;
    }
    if (finding.file === activeFilePath && !activeFile.truncated && viewRef.current) {
      scrollToLine(viewRef.current, finding.start_line);
      return;
    }
    pendingScrollLine.current = finding.start_line;
    setActiveFilePath(finding.file);
  }

  function handleCreateEditor(view: EditorView) {
    viewRef.current = view;
    if (pendingScrollLine.current != null) {
      scrollToLine(view, pendingScrollLine.current);
      pendingScrollLine.current = null;
    }
  }

  if (!activeFile) {
    return <p className="muted">표시할 소스 파일이 없습니다.</p>;
  }

  return (
    <div className="code-viewer">
      {files.length > 1 && (
        <div className="code-viewer-filelist">
          {files.map((f) => (
            <button
              key={f.path}
              type="button"
              className={`code-viewer-file-tab ${f.path === activeFilePath ? "active" : ""}`}
              onClick={() => setActiveFilePath(f.path)}
            >
              <span className="code-viewer-file-path">{f.path}</span>
              {findingCountByFile.get(f.path) ? (
                <span className="code-viewer-file-badge">{findingCountByFile.get(f.path)}</span>
              ) : null}
            </button>
          ))}
        </div>
      )}

      <div className="code-viewer-body">
        <div className="code-viewer-editor">
          {activeFile.truncated ? (
            <div className="code-viewer-truncated">
              <p>{activeFile.content}</p>
              <p className="muted">
                이 파일에 대한 finding은 Problems 목록에서 계속 확인할 수 있습니다.
              </p>
            </div>
          ) : (
            <CodeMirror
              key={activeFilePath}
              value={activeFile.content}
              theme={theme === "dark" ? oneDark : "light"}
              readOnly
              height="calc(100vh - 200px)"
              extensions={extensions}
              onCreateEditor={handleCreateEditor}
            />
          )}
        </div>

        <aside className="code-viewer-problems">
          <h3>Problems ({findings.length})</h3>
          {findings.length === 0 ? (
            <p className="muted">발견된 finding이 없습니다.</p>
          ) : (
            <ul className="problems-list">
              {sortedFindings.map((f) => (
                <li key={f.id}>
                  <button type="button" className="problem-item" onClick={() => jumpTo(f)}>
                    <span className={`problem-severity sev-${f.severity.toLowerCase()}`}>
                      {SEVERITY_LABEL[f.severity] ?? f.severity}
                    </span>
                    <span className="problem-title">{f.title}</span>
                    <span className="problem-location">
                      {f.file}:{f.start_line}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>
      </div>
    </div>
  );
}
