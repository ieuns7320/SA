import { useState } from "react";
import { Link } from "react-router-dom";
import { HelpPanel } from "./HelpPanel";
import { useTheme } from "../ThemeContext";

export function Header() {
  const [helpOpen, setHelpOpen] = useState(false);
  const { theme, toggleTheme } = useTheme();

  return (
    <header className="site-header">
      <div className="site-header-inner">
        <Link to="/" className="brand">
          <span className="brand-mark" aria-hidden="true" />
          Contract&nbsp;Auditor
        </Link>
        <nav className="header-actions">
          <Link to="/history" className="history-link">
            히스토리
          </Link>
          <button
            type="button"
            className="theme-toggle"
            onClick={toggleTheme}
            aria-label={theme === "dark" ? "라이트 모드로 전환" : "다크 모드로 전환"}
            title={theme === "dark" ? "라이트 모드로 전환" : "다크 모드로 전환"}
          >
            {theme === "dark" ? (
              <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
                <circle cx="12" cy="12" r="4.5" fill="currentColor" />
                <g stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
                  <path d="M12 2.5v2.2M12 19.3v2.2M21.5 12h-2.2M4.7 12H2.5" />
                  <path d="M18.4 5.6l-1.55 1.55M7.15 16.85L5.6 18.4M18.4 18.4l-1.55-1.55M7.15 7.15L5.6 5.6" />
                </g>
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
                <path
                  d="M20.5 14.7A8.5 8.5 0 1 1 9.3 3.5a7 7 0 0 0 11.2 11.2Z"
                  fill="currentColor"
                />
              </svg>
            )}
          </button>
          <button
            type="button"
            className={`help-toggle${helpOpen ? " active" : ""}`}
            onClick={() => setHelpOpen((v) => !v)}
            aria-expanded={helpOpen}
          >
            {helpOpen ? "닫기" : "도움말"}
          </button>
        </nav>
      </div>
      {helpOpen && <HelpPanel />}
    </header>
  );
}
