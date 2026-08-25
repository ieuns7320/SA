"""
Slither JSON 결과를 Markdown 리포트/코드 뷰어 입력용으로 전처리한다.

핵심 설계 원칙:
1. Informational/severity가 낮은 노이즈(solc-version, low-level-calls 등)는
   기본적으로 제외하거나 별도 섹션으로 분리한다. 감사자가 "진짜 취약점"에
   집중할 수 있게 하기 위함.
2. 각 finding에 실제 소스 코드 스니펫을 함께 붙인다. Slither의 description
   텍스트만으로는 코드 맥락(주변 함수, 상태변수)을 파악하기 어렵다.
3. impact/confidence를 함께 넘겨서 감사자가 우선순위를 판단할 근거로 쓴다.
4. import로 여러 파일을 참조하는 프로젝트를 지원한다 — finding마다 Slither가
   알려주는 filename_absolute를 따라가서 그 파일에서 스니펫을 뽑는다. 단일
   파일이라고 가정하지 않는다.
"""

import json
from pathlib import Path

SEVERITY_ORDER = {"High": 0, "Medium": 1, "Low": 2, "Informational": 3}

# 기본적으로 LLM에 넘기지 않는 low-value 노이즈성 detector
NOISE_CHECKS = {"solc-version", "low-level-calls", "naming-convention", "pragma"}

def _load_lines(path: Path, source_cache: dict[str, list[str]]) -> list[str]:
    """source_cache는 호출자(preprocess())가 만들어 넘기는 job 단위 캐시다.

    같은 job 안에서 한 파일에 finding이 여러 개일 때 반복 읽기를 피하는 게
    목적이라 job이 끝나면 함께 버려져야 한다 — 예전엔 모듈 전역 dict였는데,
    웹 서버 프로세스 수명 내내 절대 비워지지 않고(job마다 work_dir 경로가
    달라 캐시가 job 간에 재사용되지도 않으면서) 계속 쌓이기만 하는
    메모리 누수였다.
    """
    key = str(path)
    if key not in source_cache:
        source_cache[key] = path.read_text(errors="ignore").splitlines()
    return source_cache[key]


def extract_snippet(lines: list[str], first_line: int, last_line: int, context: int = 2) -> str:
    start = max(0, first_line - 1 - context)
    end = min(len(lines), last_line + context)
    snippet_lines = lines[start:end]
    numbered = [f"{i + start + 1}: {l}" for i, l in enumerate(snippet_lines)]
    return "\n".join(numbered)


def get_line_range(element: dict) -> tuple[int, int]:
    src_mapping = element.get("source_mapping", {})
    lines = src_mapping.get("lines", [])
    if not lines:
        return (1, 1)
    return (min(lines), max(lines))


def get_finding_file(elements: list[dict], fallback: Path) -> Path:
    """finding이 실제로 위치한 파일 경로를 알아낸다. import된 다른 파일일 수 있다."""
    for e in elements:
        abs_path = e.get("source_mapping", {}).get("filename_absolute")
        if abs_path and Path(abs_path).exists():
            return Path(abs_path)
    return fallback


def _relative_file_label(finding_file: Path, source_root: Path) -> str:
    """코드 뷰어가 파일을 구분할 키. source_root 기준 상대경로(POSIX 슬래시)를
    쓴다 — 파일명만 쓰면(예전 방식) 서로 다른 디렉토리의 동명 파일(두 개의 다른
    IERC20.sol 등)을 구분할 수 없다."""
    try:
        return finding_file.relative_to(source_root).as_posix()
    except ValueError:
        return finding_file.name


# 코드 뷰어 응답에 파일 내용을 그대로 embed할 때의 파일당 크기 상한.
# 로컬 업로드는 web/uploads.py가 이미 2MB로 막지만, 온체인 주소 조회는
# Etherscan이 주는 소스를 그대로 저장하다 보니 캡이 없었다 — 같은 기준으로 맞춘다.
MAX_EMBEDDED_FILE_BYTES = 2 * 1024 * 1024


def _read_embeddable_source(path: Path) -> tuple[str, bool]:
    """파일을 읽되 너무 크면 내용 대신 안내 문구를 반환한다(truncated=True)."""
    size = path.stat().st_size
    if size > MAX_EMBEDDED_FILE_BYTES:
        return (
            f"(파일이 너무 커서 표시할 수 없습니다: {size // 1024}KB, "
            f"최대 {MAX_EMBEDDED_FILE_BYTES // 1024 // 1024}MB)",
            True,
        )
    return path.read_text(errors="ignore"), False


def build_source_manifest(entry_path: Path, source_root: Path, multi_file: bool) -> list[dict]:
    """코드 뷰어에 넘길 소스 파일 목록을 만든다. 스니펫의 "12: code" 번호매김 포맷이
    아니라 원본 그대로의 텍스트를 담는다(파일이 너무 크면 예외 — 아래 참고).

    multi_file=False(로컬 업로드/CLI 임의 경로)면 entry 파일 하나만 담는다 —
    source_root를 통째로 훑으면 분석과 무관한 이웃 파일까지 끌려올 수 있다.
    multi_file=True(주소 조회, import 그래프 전체가 저장된 경우)면 source_root
    아래 모든 .sol 파일을 entry 파일을 맨 앞에 두고 나머지는 경로순으로 담는다.
    """
    if not multi_file:
        content, truncated = _read_embeddable_source(entry_path)
        return [{
            "path": _relative_file_label(entry_path, source_root),
            "content": content,
            "truncated": truncated,
        }]

    paths = sorted(source_root.rglob("*.sol"))
    paths.sort(key=lambda p: (p != entry_path, p))
    manifest = []
    for p in paths:
        content, truncated = _read_embeddable_source(p)
        manifest.append({
            "path": _relative_file_label(p, source_root),
            "content": content,
            "truncated": truncated,
        })
    return manifest


def preprocess(
    slither_json_path: str,
    entry_sol_path: str,
    include_noise: bool = False,
    source_root: Path | None = None,
) -> dict:
    data = json.loads(Path(slither_json_path).read_text())
    detectors = data.get("results", {}).get("detectors", [])
    entry_path = Path(entry_sol_path)
    source_root = source_root or entry_path.parent

    findings = []
    source_cache: dict[str, list[str]] = {}
    for d in detectors:
        if not include_noise and d["check"] in NOISE_CHECKS:
            continue

        elements = d.get("elements", [])
        finding_file = get_finding_file(elements, entry_path)

        # finding이 여러 파일에 걸친 elements를 가질 수 있으므로(예: 다른 파일의
        # 함수를 호출하는 reentrancy), 스니펫을 뽑을 파일(finding_file)과 같은
        # 파일의 elements만으로 라인 범위를 계산한다. 안 그러면 다른 파일 기준
        # 라인 번호로 엉뚱한 스니펫이 잘려나온다.
        same_file_elements = [
            e for e in elements
            if e.get("source_mapping", {}).get("filename_absolute") == str(finding_file)
        ] or elements

        if same_file_elements:
            lines = [get_line_range(e) for e in same_file_elements if e.get("source_mapping")]
            first = min((l[0] for l in lines), default=1)
            last = max((l[1] for l in lines), default=1)
        else:
            first, last = 1, 1

        try:
            snippet = extract_snippet(_load_lines(finding_file, source_cache), first, last)
        except FileNotFoundError:
            snippet = "(소스 파일을 찾을 수 없어 스니펫을 표시할 수 없습니다)"

        file_label = _relative_file_label(finding_file, source_root)
        findings.append({
            # file까지 포함해야 한다 — 멀티파일 컨트랙트에서 서로 다른 파일이
            # 같은 detector·같은 시작 라인으로 겹치면(흔치 않지만 가능) id가
            # 충돌해서 프론트(CodeViewer.tsx)의 React key로 쓰일 때 엉뚱한
            # finding으로 스크롤되는 문제가 있었다.
            "id": f"{d['check']}-{file_label}-{first}",
            "check": d["check"],
            "impact": d["impact"],
            "confidence": d["confidence"],
            "file": file_label,
            "lines": f"{first}-{last}",
            "start_line": first,
            "end_line": last,
            "summary": d["description"].strip().split("\n")[0],
            "code_snippet": snippet,
        })

    findings.sort(key=lambda f: SEVERITY_ORDER.get(f["impact"], 9))

    return {
        "contract_file": entry_path.name,
        "total_findings": len(findings),
        "findings": findings,
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("사용법: python -m auditor.analyzers.preprocess <slither_json_path> <sol_path>")
        sys.exit(1)

    result = preprocess(sys.argv[1], sys.argv[2])
    print(json.dumps(result, indent=2, ensure_ascii=False))