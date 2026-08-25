"""
전처리된 Slither finding 목록을 사람이 읽는 Markdown 리포트로 변환한다.
LLM을 전혀 호출하지 않는다 — data/detector_explanations.json의 정적 매핑만 사용한다.
매핑에 없는 detector는 Slither의 원본 summary를 그대로 보여준다 (판단 없이 있는 그대로).
"""

import json
from pathlib import Path

SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Informational": 4}
SEVERITY_LABEL_KO = {
    "Critical": "치명적",
    "High": "높음",
    "Medium": "중간",
    "Low": "낮음",
    "Informational": "정보",
}

EXPLANATIONS_PATH = Path(__file__).resolve().parents[3] / "data" / "detector_explanations.json"


def load_explanations() -> dict:
    if not EXPLANATIONS_PATH.exists():
        return {}
    return json.loads(EXPLANATIONS_PATH.read_text(encoding="utf-8"))


def enrich_finding(finding: dict, explanations: dict) -> dict:
    """전처리된 finding에 정적 지식베이스 설명을 붙인다. 매핑이 없으면 원본 impact를 그대로 사용."""
    kb = explanations.get(finding["check"])
    enriched = dict(finding)
    if kb:
        enriched["title"] = kb["title"]
        enriched["explanation"] = kb["explanation"]
        enriched["remediation"] = kb["remediation"]
        # Slither가 매긴 impact를 우선 사용하고, 없으면 지식베이스 기본값을 쓴다.
        enriched["severity"] = finding.get("impact") or kb["default_severity"]
    else:
        enriched["title"] = finding["check"]
        enriched["explanation"] = finding["summary"] + " (알려진 설명 없음 — Slither 원문 참고)"
        enriched["remediation"] = "수동 검토가 필요합니다."
        enriched["severity"] = finding.get("impact", "Informational")
    return enriched


def generate_markdown_report(preprocessed: dict, explanations: dict | None = None) -> str:
    if explanations is None:
        explanations = load_explanations()

    enriched = [enrich_finding(f, explanations) for f in preprocessed["findings"]]
    enriched.sort(key=lambda f: SEVERITY_ORDER.get(f["severity"], 9))

    lines = [
        f"# 보안 분석 리포트 — {preprocessed['contract_file']}",
        "",
        f"총 {len(enriched)}개의 finding이 발견되었습니다. "
        "이 리포트는 정적분석(Slither) 결과를 규칙 기반으로 정리한 것입니다. "
        "**판단은 하지 않습니다** — Slither가 찾은 것을 그대로, 다만 이해하기 쉽게 "
        "정리할 뿐이며, 최종 판단은 감사관의 검토가 필요합니다.",
        "",
        "## 요약",
        "",
        "| 심각도 | 개수 |",
        "|---|---|",
    ]
    counts = {}
    for f in enriched:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    for sev in SEVERITY_ORDER:
        if sev in counts:
            lines.append(f"| {SEVERITY_LABEL_KO[sev]} | {counts[sev]} |")

    lines += ["", "## 상세 내역", ""]

    for i, f in enumerate(enriched, 1):
        sev_ko = SEVERITY_LABEL_KO.get(f["severity"], f["severity"])
        lines += [
            f"### {i}. [{sev_ko}] {f['title']} — {f.get('file', '')} {f['lines']}행",
            "",
            f"**설명**: {f['explanation']}",
            "",
            f"**해결 방법**: {f['remediation']}",
            "",
            "```solidity",
            f["code_snippet"],
            "```",
            "",
            f"<sub>detector: `{f['check']}` · confidence: {f.get('confidence', '-')}</sub>",
            "",
        ]

    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from auditor.analyzers.preprocess import preprocess

    if len(sys.argv) != 3:
        print("사용법: python -m auditor.report.generator <slither_json> <sol_path>")
        sys.exit(1)

    result = preprocess(sys.argv[1], sys.argv[2])
    report = generate_markdown_report(result)
    print(report)