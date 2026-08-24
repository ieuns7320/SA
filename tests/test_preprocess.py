"""auditor.analyzers.preprocess 단위 테스트."""

import json
from pathlib import Path

import pytest

from auditor.analyzers.preprocess import (
    build_source_manifest,
    extract_snippet,
    get_finding_file,
    get_line_range,
    preprocess,
)


def _make_element(abs_path: Path, lines: list[int]) -> dict:
    return {"source_mapping": {"filename_absolute": str(abs_path), "lines": lines}}


def _write_sol(path: Path, n_lines: int) -> None:
    path.write_text("\n".join(f"line {i}" for i in range(1, n_lines + 1)) + "\n")


def _write_slither_json(tmp_path: Path, detectors: list[dict]) -> Path:
    out = tmp_path / "slither.json"
    out.write_text(json.dumps({"results": {"detectors": detectors}}))
    return out


@pytest.fixture
def two_files(tmp_path):
    file_a = tmp_path / "A.sol"
    file_b = tmp_path / "B.sol"
    _write_sol(file_a, 20)
    _write_sol(file_b, 300)
    return file_a, file_b


class TestGetLineRange:
    def test_returns_min_max_of_lines(self):
        element = {"source_mapping": {"lines": [10, 11, 12]}}
        assert get_line_range(element) == (10, 12)

    def test_missing_lines_defaults_to_1_1(self):
        assert get_line_range({"source_mapping": {}}) == (1, 1)
        assert get_line_range({}) == (1, 1)


class TestExtractSnippet:
    def test_includes_context_lines_and_numbers(self):
        lines = [f"L{i}" for i in range(1, 11)]
        snippet = extract_snippet(lines, first_line=5, last_line=5, context=2)
        assert snippet.splitlines() == ["3: L3", "4: L4", "5: L5", "6: L6", "7: L7"]

    def test_clamps_to_file_bounds(self):
        lines = ["L1", "L2", "L3"]
        snippet = extract_snippet(lines, first_line=1, last_line=3, context=5)
        assert snippet.splitlines() == ["1: L1", "2: L2", "3: L3"]


class TestGetFindingFile:
    def test_returns_first_element_file_that_exists(self, two_files):
        file_a, file_b = two_files
        elements = [_make_element(file_b, [1]), _make_element(file_a, [1])]
        assert get_finding_file(elements, fallback=Path("/nonexistent")) == file_b

    def test_falls_back_when_no_element_path_exists(self):
        fallback = Path("/some/fallback.sol")
        elements = [{"source_mapping": {"filename_absolute": "/does/not/exist.sol"}}]
        assert get_finding_file(elements, fallback) == fallback

    def test_falls_back_when_no_elements(self):
        fallback = Path("/some/fallback.sol")
        assert get_finding_file([], fallback) == fallback


class TestPreprocess:
    def test_filters_noise_checks_by_default(self, tmp_path, two_files):
        file_a, _ = two_files
        detectors = [
            {
                "check": "solc-version",
                "impact": "Informational",
                "confidence": "High",
                "description": "outdated pragma\n",
                "elements": [_make_element(file_a, [1])],
            },
            {
                "check": "reentrancy-eth",
                "impact": "High",
                "confidence": "Medium",
                "description": "reentrancy\n",
                "elements": [_make_element(file_a, [5])],
            },
        ]
        slither_json = _write_slither_json(tmp_path, detectors)
        result = preprocess(str(slither_json), str(file_a))
        assert result["total_findings"] == 1
        assert result["findings"][0]["check"] == "reentrancy-eth"

    def test_include_noise_keeps_noise_checks(self, tmp_path, two_files):
        file_a, _ = two_files
        detectors = [
            {
                "check": "solc-version",
                "impact": "Informational",
                "confidence": "High",
                "description": "outdated pragma\n",
                "elements": [_make_element(file_a, [1])],
            }
        ]
        slither_json = _write_slither_json(tmp_path, detectors)
        result = preprocess(str(slither_json), str(file_a), include_noise=True)
        assert result["total_findings"] == 1

    def test_sorts_findings_by_severity(self, tmp_path, two_files):
        file_a, _ = two_files
        detectors = [
            {
                "check": "timestamp",
                "impact": "Low",
                "confidence": "Medium",
                "description": "low\n",
                "elements": [_make_element(file_a, [1])],
            },
            {
                "check": "reentrancy-eth",
                "impact": "High",
                "confidence": "Medium",
                "description": "high\n",
                "elements": [_make_element(file_a, [2])],
            },
            {
                "check": "unchecked-transfer",
                "impact": "Medium",
                "confidence": "Medium",
                "description": "medium\n",
                "elements": [_make_element(file_a, [3])],
            },
        ]
        slither_json = _write_slither_json(tmp_path, detectors)
        result = preprocess(str(slither_json), str(file_a))
        assert [f["impact"] for f in result["findings"]] == ["High", "Medium", "Low"]

    def test_multi_file_finding_uses_only_matching_file_lines(self, tmp_path, two_files):
        """
        회귀 테스트(2026-08): finding의 elements가 여러 파일에 걸쳐 있을 때
        (예: 다른 파일 함수를 호출하는 reentrancy), 라인 범위와 스니펫이 스니펫이
        실제로 뽑히는 파일(finding_file)과 무관한 다른 파일의 라인 번호로 오염되면
        안 된다.
        """
        file_a, file_b = two_files  # A: 20줄, B: 300줄
        detectors = [
            {
                "check": "reentrancy-eth",
                "impact": "High",
                "confidence": "Medium",
                "description": "cross-file reentrancy\n",
                "elements": [
                    _make_element(file_a, [5, 6]),  # 스니펫이 뽑힐 파일
                    _make_element(file_b, [250, 260]),  # 다른 파일의 훨씬 뒤쪽 라인
                ],
            }
        ]
        slither_json = _write_slither_json(tmp_path, detectors)
        result = preprocess(str(slither_json), str(file_a))

        finding = result["findings"][0]
        assert finding["file"] == file_a.name
        assert finding["lines"] == "5-6"
        # 버그가 있었다면 라인 범위가 5-260으로 계산되어 스니펫이 3~20행 전체를
        # 끌고 왔을 것이다 (context=2 기준 정상은 5줄 이내여야 한다).
        assert len(finding["code_snippet"].splitlines()) <= 6

    def test_missing_source_file_falls_back_gracefully(self, tmp_path):
        entry = tmp_path / "missing.sol"
        detectors = [
            {
                "check": "reentrancy-eth",
                "impact": "High",
                "confidence": "Medium",
                "description": "desc\n",
                "elements": [],
            }
        ]
        slither_json = _write_slither_json(tmp_path, detectors)
        result = preprocess(str(slither_json), str(entry))
        assert result["findings"][0]["code_snippet"] == (
            "(소스 파일을 찾을 수 없어 스니펫을 표시할 수 없습니다)"
        )

    def test_start_and_end_line_are_ints_alongside_lines_string(self, tmp_path, two_files):
        file_a, _ = two_files
        detectors = [
            {
                "check": "reentrancy-eth",
                "impact": "High",
                "confidence": "Medium",
                "description": "desc\n",
                "elements": [_make_element(file_a, [5, 6])],
            }
        ]
        slither_json = _write_slither_json(tmp_path, detectors)
        result = preprocess(str(slither_json), str(file_a))
        finding = result["findings"][0]
        assert finding["lines"] == "5-6"
        assert finding["start_line"] == 5
        assert finding["end_line"] == 6

    def test_file_field_is_relative_to_source_root(self, tmp_path):
        """
        회귀 테스트(2026-08): 코드 뷰어는 파일명만으로는 서로 다른 디렉토리의
        동명 파일(예: 두 개의 다른 IERC20.sol)을 구분할 수 없다 — source_root
        기준 상대경로여야 한다.
        """
        project_root = tmp_path / "MyContract"
        nested = project_root / "@openzeppelin" / "contracts"
        nested.mkdir(parents=True)
        entry = project_root / "MyContract.sol"
        entry.write_text("contract MyContract {}\n")
        imported = nested / "IERC20.sol"
        _write_sol(imported, 10)

        detectors = [
            {
                "check": "reentrancy-eth",
                "impact": "High",
                "confidence": "Medium",
                "description": "desc\n",
                "elements": [_make_element(imported, [3])],
            }
        ]
        slither_json = _write_slither_json(tmp_path, detectors)
        result = preprocess(str(slither_json), str(entry), source_root=project_root)
        assert result["findings"][0]["file"] == "@openzeppelin/contracts/IERC20.sol"

    def test_file_field_falls_back_to_name_outside_source_root(self, tmp_path, two_files):
        file_a, _ = two_files
        other_root = tmp_path / "unrelated"
        other_root.mkdir()
        detectors = [
            {
                "check": "reentrancy-eth",
                "impact": "High",
                "confidence": "Medium",
                "description": "desc\n",
                "elements": [_make_element(file_a, [1])],
            }
        ]
        slither_json = _write_slither_json(tmp_path, detectors)
        result = preprocess(str(slither_json), str(file_a), source_root=other_root)
        assert result["findings"][0]["file"] == file_a.name


class TestBuildSourceManifest:
    def test_single_file_mode_returns_only_entry(self, tmp_path, two_files):
        file_a, file_b = two_files
        manifest = build_source_manifest(file_a, tmp_path, multi_file=False)
        assert [f["path"] for f in manifest] == ["A.sol"]
        assert manifest[0]["content"] == file_a.read_text()
        # 스니펫의 "N: code" 번호매김 포맷이 아니라 원본 그대로여야 한다.
        assert not manifest[0]["content"].startswith("1: ")

    def test_multi_file_mode_lists_all_sol_files_entry_first(self, tmp_path, two_files):
        file_a, file_b = two_files  # A.sol, B.sol (알파벳순으론 A가 먼저지만 entry는 B)
        manifest = build_source_manifest(file_b, tmp_path, multi_file=True)
        assert [f["path"] for f in manifest] == ["B.sol", "A.sol"]

    def test_multi_file_mode_uses_relative_posix_paths(self, tmp_path):
        project_root = tmp_path / "MyContract"
        nested = project_root / "lib"
        nested.mkdir(parents=True)
        entry = project_root / "MyContract.sol"
        entry.write_text("contract MyContract {}\n")
        (nested / "Lib.sol").write_text("library Lib {}\n")

        manifest = build_source_manifest(entry, project_root, multi_file=True)
        assert {f["path"] for f in manifest} == {"MyContract.sol", "lib/Lib.sol"}

    def test_normal_size_file_is_not_truncated(self, tmp_path, two_files):
        file_a, _ = two_files
        manifest = build_source_manifest(file_a, tmp_path, multi_file=False)
        assert manifest[0]["truncated"] is False

    def test_oversized_file_is_replaced_with_placeholder(self, tmp_path, monkeypatch):
        """
        회귀 테스트(2026-08): 로컬 업로드는 web/uploads.py가 2MB로 막지만, 온체인
        주소 조회는 캡이 없어 대형 컨트랙트의 전체 소스가 findings.json/API
        응답에 그대로 embed됐다. MAX_EMBEDDED_FILE_BYTES를 넘으면 내용 대신
        안내 문구로 대체하고 truncated=True를 표시해야 한다.
        """
        from auditor.analyzers import preprocess as preprocess_module

        monkeypatch.setattr(preprocess_module, "MAX_EMBEDDED_FILE_BYTES", 10)
        big = tmp_path / "Big.sol"
        big.write_text("x" * 100)

        manifest = build_source_manifest(big, tmp_path, multi_file=False)

        assert manifest[0]["truncated"] is True
        assert "x" * 100 not in manifest[0]["content"]
        assert "너무 커서" in manifest[0]["content"]
