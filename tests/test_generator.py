"""auditor.report.generator 단위 테스트."""

from auditor.report.generator import (
    enrich_finding,
    generate_markdown_report,
    load_explanations,
)

REQUIRED_KB_FIELDS = {"title", "explanation", "remediation", "default_severity"}


def _finding(check="reentrancy-eth", impact="High", **overrides):
    base = {
        "id": f"{check}-1",
        "check": check,
        "impact": impact,
        "confidence": "Medium",
        "file": "Contract.sol",
        "lines": "10-12",
        "summary": "summary text",
        "code_snippet": "10: code",
    }
    base.update(overrides)
    return base


class TestEnrichFinding:
    def test_known_detector_uses_knowledge_base(self):
        explanations = {
            "reentrancy-eth": {
                "title": "재진입 공격",
                "explanation": "설명",
                "remediation": "해결법",
                "default_severity": "High",
            }
        }
        enriched = enrich_finding(_finding(), explanations)
        assert enriched["title"] == "재진입 공격"
        assert enriched["severity"] == "High"  # Slither impact를 우선 사용

    def test_unknown_detector_falls_back_without_inventing_explanation(self):
        enriched = enrich_finding(_finding(check="some-new-detector", impact="Medium"), {})
        assert enriched["title"] == "some-new-detector"
        assert "알려진 설명 없음" in enriched["explanation"]
        assert enriched["severity"] == "Medium"

    def test_missing_impact_uses_kb_default_severity(self):
        explanations = {
            "weak-prng": {
                "title": "약한 난수",
                "explanation": "e",
                "remediation": "r",
                "default_severity": "Medium",
            }
        }
        enriched = enrich_finding(_finding(check="weak-prng", impact=""), explanations)
        assert enriched["severity"] == "Medium"


class TestGenerateMarkdownReport:
    def test_report_contains_summary_and_findings_sorted_by_severity(self):
        preprocessed = {
            "contract_file": "Vault.sol",
            "total_findings": 2,
            "findings": [
                _finding(check="reentrancy-eth", impact="High"),
                _finding(check="tx-origin", impact="Medium", lines="20-21"),
            ],
        }
        explanations = {
            "reentrancy-eth": {
                "title": "재진입",
                "explanation": "e",
                "remediation": "r",
                "default_severity": "High",
            },
            "tx-origin": {
                "title": "tx.origin",
                "explanation": "e",
                "remediation": "r",
                "default_severity": "Medium",
            },
        }
        report = generate_markdown_report(preprocessed, explanations)
        assert "Vault.sol" in report
        assert "LLM 판단 없이 자동 생성" in report
        assert "재진입" in report
        assert "tx.origin" in report
        assert report.index("재진입") < report.index("tx.origin")

    def test_severity_summary_counts(self):
        preprocessed = {
            "contract_file": "V.sol",
            "total_findings": 2,
            "findings": [_finding(impact="High"), _finding(check="x", impact="High")],
        }
        report = generate_markdown_report(preprocessed, explanations={})
        assert "| 높음 | 2 |" in report


def test_detector_explanations_json_has_required_fields():
    """
    CLAUDE.md 컨벤션: data/detector_explanations.json의 모든 detector는
    title/explanation/remediation/default_severity 네 필드를 모두 채워야 한다.
    하나라도 비면 리포트에서 어색하게 노출된다.
    """
    explanations = load_explanations()
    assert explanations, "detector_explanations.json이 비어있거나 로드되지 않음"
    for check, kb in explanations.items():
        missing = REQUIRED_KB_FIELDS - kb.keys()
        assert not missing, f"{check}에 누락된 필드: {missing}"
        for field in REQUIRED_KB_FIELDS:
            assert kb[field], f"{check}.{field}가 비어있음"
