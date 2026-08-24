# CLAUDE.md

이 파일은 Claude Code가 이 저장소에서 작업할 때 참고하는 프로젝트 컨텍스트입니다.

## 프로젝트 개요

Web3 스마트컨트랙트 정적분석 결과보고서 생성 도구.

**현재 버전은 LLM을 전혀 사용하지 않는다.** 핵심 흐름은 다음 3단계뿐이다:

```
[컨트랙트 주소 또는 .sol 파일 입력] -> [Slither 취약점 분석] -> [Markdown 결과보고서]
```

- 1단계: 주소가 입력되면 Etherscan API로 검증된 소스코드를 받아오고, 파일 경로가
  입력되면 그대로 사용한다.
- 2단계: Slither를 서브프로세스로 실행해 정적분석한다.
- 3단계: `data/detector_explanations.json`의 정적 매핑을 이용해 Slither 결과를
  사람이 읽을 수 있는 한국어 Markdown 리포트로 변환한다. **판단은 하지 않는다** —
  Slither가 찾은 것을 그대로, 다만 이해하기 쉽게 정리할 뿐이다.

CLI(`auditor.cli.run_pipeline`)가 이 3단계의 유일한 진입점이며, 웹 UI(`auditor.web`)는
이 함수를 그대로 감싸는 얇은 API 레이어일 뿐이다 — 파이프라인 로직 자체를 다시
구현하지 않는다. 웹 UI는 로그인 없는 익명 세션 기반으로 여러 사용자가 동시에 쓸 수
있게 설계되어 있다 (아래 "개발 단계" 1단계 후반부 참고).

**이 도구의 진짜 목적은 "리포트를 낸다"가 아니라 "감사자가 컨트랙트 코드의 어느
부분이 왜 취약한지 빠르게 파악하게 돕는다"는 것에 가깝다.** 그래서 웹 UI의 주
화면은 Markdown 리포트가 아니라, 실제 소스 코드 위에 Slither finding을 VSCode
Problems 패널처럼 인라인으로 표기하는 코드 뷰어다 — Markdown 리포트는 다운로드
가능한 부가 탭으로 유지된다 (아래 "개발 단계" 1단계의 코드 뷰어 항목 참고). 이건
새로운 판단 로직이 아니라 표현 계층 변경일 뿐이다 — Slither가 이미 찾아낸 finding을
다르게 보여줄 뿐, "판단은 하지 않는다" 원칙과 LLM 미사용 원칙 둘 다 그대로 유지된다.

## 비용에 대한 원칙

이 프로젝트는 어떤 LLM API도 호출하지 않는다 (`anthropic`, `openai` SDK 등을
의존성에 추가하지 않는다). Slither 실행은 완전히 로컬이고, Etherscan API는
무료 티어로 충분하다. **새 기능을 추가할 때 이 원칙을 조용히 깨지 말 것** — LLM
호출이 필요해 보이는 작업을 요청받으면 먼저 사용자에게 "이건 비용이 발생하는
방향"이라고 알리고 확인받는다.

## 알려진 한계 (LLM 없이는 못 잡는 것들)

`data/detector_explanations.json`은 Slither가 **이미 찾아낸** finding을 설명해줄
뿐, Slither 자체가 놓친 이슈(예: 함수에 접근 제어가 아예 없는 경우 — Slither는
zero-check 누락 정도만 지적하고 접근 제어 자체의 부재는 잡지 못함)는 찾지 못한다.
이건 의도된 트레이드오프이며, 나중에 LLM 레이어를 다시 붙일 때의 핵심 가치
포인트로 `docs/future/`에 남겨둔다.

그 외에도 현재 남아있는 구조적 한계:

- `input/address_fetcher.py`가 `@openzeppelin/...` 같은 패키지 스타일 import를
  remapping 없이는 해석하지 못한다 — Etherscan에서 소스는 받아와도 solc가
  해당 import를 못 찾아 컴파일이 실패할 수 있다. foundry.toml/hardhat.config
  기반 remapping 자동 추론은 아직 없음.
- 로컬 파일 입력(`python -m auditor.cli <path>.sol`)은 단일 파일만 지원한다.
  파일이 다른 로컬 파일을 import하는 멀티파일 프로젝트는 아직 처리하지 못함
  (온체인 주소 입력은 import 그래프 전체를 저장하도록 개선됨 — 아래 1단계 참고).
- 프록시 컨트랙트 해석은 1홉만 따라간다. 구현 컨트랙트가 다시 다른 프록시를
  가리키는 이중 프록시나, Etherscan이 `Implementation` 필드로 정적 표현하지
  못하는 비콘 프록시(beacon proxy) 패턴은 대응하지 못하고 그 시점 주소의
  소스를 그대로 분석한다.
- `solc-select install <version>`이 네트워크 문제 등으로 중간에 실패하면
  (예: 다운로드 도중 `subprocess` timeout) 빈 아티팩트 디렉토리만 생성된 채로
  남을 수 있다. solc-select의 "이미 설치됨" 판단이 디렉토리 존재 여부만
  보는 것으로 보여서, 이후 같은 버전 요청이 재설치 없이 "이미 설치됨"으로
  스킵되고 `artifact_path().exists()`가 계속 False가 되어 매번 시스템
  solc로 폴백할 수 있다(웹 UI 동시성 검증 중 실제로 목격, 수동으로
  `.venv/.solc-select/artifacts/solc-<version>/` 삭제 후 재설치해서 해결).
  자동 복구 로직은 아직 없음 — 발생하면 해당 버전 디렉토리를 지우고
  `solc-select install <version>`을 다시 실행.
- 웹 UI의 레이트리밋 카운터와 `ThreadPoolExecutor`는 프로세스 인메모리
  상태라 서버 재시작하면 리셋된다. job 메타데이터(SQLite)는 재시작에도
  남지만, 재시작 시점에 `queued`/`running`이던 job은 `failed`로 정리된다
  (`db.sweep_stale_jobs`).

## 개발 단계

- [x] **0단계**: 프로젝트 구조 셋업
- [x] **1단계 (현재)**: 주소/파일 입력 → Slither → 규칙 기반 Markdown 리포트
  - `input/address_fetcher.py`, `analyzers/slither_runner.py`,
    `analyzers/preprocess.py`, `report/generator.py`, `cli.py` 완료
  - `tests/fixtures/contracts/vulnerable_vault.sol`로 실제 검증 완료 (4개 finding
    → 리포트 생성 확인)
  - `address_fetcher.py`: Etherscan API V1 → V2로 마이그레이션 (`chainid` 파라미터
    필수). import로 연결된 여러 파일을 전부 저장하도록 수정 (예전엔 첫 파일만 저장).
  - `preprocess.py`: finding마다 실제 소속 파일(`filename_absolute`)을 따라가서
    코드 스니펫을 뽑도록 수정 (멀티파일 프로젝트에서 잘못된 파일의 스니펫이
    붙는 문제 해결).
  - `slither_runner.py`: 컨트랙트의 pragma를 읽어서 solc-select로 필요한 solc
    버전을 자동 설치/전환하도록 수정.
  - `cli.py`: `python-dotenv`로 `.env` 자동 로드 — 처음엔 의존성만 추가되고
    실제 `load_dotenv()` 호출이 빠져 있던 버그가 있었음(환경변수를 직접
    export해야만 동작). `cli.py` 모듈 로드 시 `load_dotenv()`를 호출하도록
    고쳐서 `.env`만으로 `ETHERSCAN_API_KEY`가 정상 로드되는 것까지 검증 완료.
  - `preprocess.py`: finding의 라인 범위(first/last)를 스니펫이 뽑히는 파일
    (`finding_file`)과 같은 파일의 elements로만 계산하도록 수정. 기존엔 여러
    파일에 걸친 elements 전체에서 라인 범위를 계산해놓고 스니펫은 그중 한
    파일에서만 뽑아서, 다른 파일 함수를 호출하는 reentrancy 같은 멀티파일
    finding에서 엉뚱한 라인 번호의 코드가 스니펫으로 잘려 나올 수 있었음.
  - `tests/`에 pytest 테스트 스위트 추가 (47개, 전부 통과) — 각 모듈 단위
    테스트(`test_preprocess.py`, `test_generator.py`, `test_slither_runner.py`,
    `test_address_fetcher.py`, `test_cli.py`)와 실제 slither를 돌리는
    end-to-end 테스트(`test_pipeline_integration.py`, slither 미설치 환경에선
    자동 skip)로 구성. 위 두 버그(`.env` 미로드, 멀티파일 라인범위)에 대한
    회귀 테스트 포함, `detector_explanations.json`의 4개 필수 필드 검증도
    테스트로 강제함.
  - `address_fetcher.py`: 실사용 신뢰성 개선 3건.
    1) **프록시 컨트랙트 해석** — Etherscan 응답의 `Proxy`/`Implementation`
       필드를 확인해 프록시로 판별되면 구현 컨트랙트 주소로 재귀 호출,
       delegatecall 껍데기가 아니라 실제 로직 소스를 분석 대상으로 삼음
       (1홉만 따라감, 이중 프록시는 아래 "알려진 한계" 참고).
    2) **네트워크 에러 재시도** — `_request_with_retries`로 감싸서 타임아웃/
       연결 끊김 시 지수 백오프 재시도, 실패하면 트레이스백 대신 명확한
       한국어 `RuntimeError`.
    3) **레이트리밋 대응** — Etherscan 무료 티어 레이트리밋(HTTP 429가 아니라
       `status=0` + "rate limit" 메시지로 옴)을 감지해 재시도.
    관련 테스트 6개 추가 (`TestProxyResolution`, `TestRetries`, `time.sleep`
    모킹으로 실제 지연 없이 검증).
  - **웹 UI 추가** (`src/auditor/web/` + `frontend/`) — 처음부터 다중 사용자를
    상정한 설계. 상세 설계 문서는 `~/.claude/plans/steady-humming-pebble.md` 참고.
    - 백엔드는 FastAPI. `POST /api/jobs`(주소 또는 파일 업로드) →
      `ThreadPoolExecutor`로 `run_pipeline()`을 백그라운드 실행(동시성 캡 =
      `WEB_MAX_CONCURRENT_JOBS`, 기본 2) → `GET /api/jobs/{id}`로 폴링 →
      `GET /api/jobs/{id}/report`로 리포트 조회. job 메타데이터는
      `reports/web_jobs.sqlite3`, 리포트/소스는 기존처럼 `reports/<job_id>/`에
      파일로 저장 (`db.py`, `jobs.py`, `routers/jobs.py`, `app.py`).
    - 로그인 없는 익명 세션(`session.py`) — 서명 없는 랜덤 토큰 쿠키를 조회
      키로만 사용, 소유권 불일치 시 403이 아니라 404로 존재 자체를 감춤.
    - 세션+IP 슬라이딩 윈도우 레이트리밋(`ratelimit.py`, 인메모리, 신규
      의존성 없음) — 공유 `ETHERSCAN_API_KEY`와 제한된 slither 동시 실행
      슬롯을 한 세션이 독점하지 못하게 막음.
    - 업로드 안전장치(`uploads.py`) — 크기 캡 2MB, `.sol` 확장자 체크, 경로
      조작 방지, UTF-8/최소 Solidity 키워드 확인.
    - **`slither_runner.py` 아키텍처 변경**: `ensure_solc_version()`이 더 이상
      `solc-select use <version>`으로 전역 solc 버전을 전환하지 않는다 — 웹
      백엔드에서 서로 다른 pragma 버전의 컨트랙트가 동시에(멀티스레드) 분석될
      수 있는데, 전역 전환은 레이스 컨디션이 되기 때문. 대신 `solc-select
      install`만 하고 `solc_select.solc_select.artifact_path()`로 바이너리
      경로를 얻어 slither에 `--solc <경로>`로 직접 넘긴다. 버전별
      `threading.Lock`으로 "같은 버전 동시 첫 설치" 레이스만 막는다. CLI
      단일 실행 경로는 동작 무변화(하위호환 확인됨).
    - `pyproject.toml`: `solc-select`를 전이 의존성에서 명시적 직접
      의존성으로 승격(`artifact_path()`를 직접 import하므로). `web` extra
      신설(`fastapi`, `uvicorn[standard]`, `python-multipart`), `dev`에
      `httpx` 추가(FastAPI `TestClient` 요구사항).
    - 프론트엔드: React + Vite + TypeScript(`frontend/`). 헤더(`Header.tsx`)가
      모든 페이지 상단에 고정 노출되며 "도움말"(펼치면 `HelpPanel.tsx`가 사용
      3단계를 안내)과 "히스토리" 링크를 담고 있다. 주소/파일 토글 입력폼
      (`SubmitPage`) → 2초 간격 폴링 상태 화면(`JobStatusPage`) →
      `marked`+`dompurify`로 렌더링하는 리포트 화면(`ReportPage`). Vite dev
      서버가 `/api`를 `:8000`으로 프록시해서 CORS/쿠키 SameSite 문제를 우회.
      다크 전용 테마로 재디자인(카드 UI, 인디고 accent, 상태별 뱃지/스피너).
    - **리포트 다운로드**: `ReportPage`에 다운로드 버튼 추가. 백엔드 변경 없이
      `/api/jobs/{id}/report`로 향하는 `<a download>` 링크로 구현(같은
      오리진 네비게이션이라 쿠키가 자동으로 실림). 파일명은 리포트 본문의
      `# 보안 분석 리포트 — {이름}` 제목 줄에서 정규식으로 뽑아
      `{이름}.report.md`로 만듦.
    - **분석 히스토리**: 세션이 지금까지 제출한 job을 최신순으로 보여주는
      기능. 백엔드에 `GET /api/jobs`(세션 소유 job만, 최신순, `db.py`의
      `list_jobs_by_session`) 신설. 프론트에 `HistoryPage.tsx`(`/history`)
      추가 — 목록 항목 클릭 시 `/jobs/{id}`로 이동하면 `JobStatusPage`가
      이미 완료된 job은 즉시 리포트로 리다이렉트하므로 별도 분기 없이
      재사용됨. `POST /api/jobs`(job 생성)와 경로가 같아 HTTP 메서드로만
      구분(`GET`은 목록, `POST`는 생성).
    - 테스트 39개 추가(`test_web_db.py`, `test_web_ratelimit.py`,
      `test_web_api.py` — 세션 격리, 레이트리밋, 업로드 검증, 경로 조작 방지,
      job 실패 시 에러 메시지 전달, 히스토리 목록/세션 격리, 실제 slither를
      태우는 e2e 1개 포함). 전체 스위트 85개 전부 통과.
    - **실제 브라우저로 검증 완료**: 온체인 주소(WETH9, USDT) 입력 →
      Etherscan 조회 → Slither 분석(pragma 자동 인식) → 리포트 렌더링 →
      다운로드 버튼 파일명 확인 → 히스토리 목록에서 재접근까지 전체 플로우
      스크린샷으로 확인. 서로 다른 pragma 버전(0.6.12, 0.7.6) 컨트랙트
      2개를 동시에 제출해서 각각 올바른 solc로 컴파일되고 결과가 안 섞이는
      것도 확인 — 아키텍처 변경의 핵심 검증 포인트.
    - **검증 중 발견한 이슈** (아래 "알려진 한계"에 기록): `solc-select
      install`이 네트워크 문제로 중간에 실패하면(예: `subprocess` timeout)
      빈 아티팩트 디렉토리만 남아, 이후 "이미 설치됨"으로 오인되어 재설치를
      건너뛸 수 있음.
    - **`scripts/dev.sh` 추가** — 터미널 두 개를 오가야 하는 게 번거롭다는
      피드백으로, 백엔드+프론트엔드를 한 명령으로 같이 띄우고 Ctrl+C 한 번에
      둘 다 정리되게 함. `uvicorn --reload`와 `npm run dev`(vite/esbuild)
      둘 다 자식 프로세스를 새로 fork해서 최상위 PID만 kill하면 하위
      프로세스가 안 죽고 남는 문제가 있었음 — `pgrep -P`로 프로세스 트리를
      재귀적으로 추적해서 죽이는 `kill_tree` + 혹시 못 잡는 경우(vite/esbuild
      가 detached로 뜨는 경우 등)를 위한 포트 기준 강제 정리(`lsof -ti`)를
      이중으로 둠. 포트 8000/5173 선점 여부도 시작 전에 확인해서 명확한
      에러 메시지를 준다.
    - **업로드 분석 subprocess에 CPU/메모리 상한 추가** (`slither_runner.py`)
      — 익명 사용자가 올린 신뢰할 수 없는 컨트랙트를 분석하는 subprocess가
      무제한 자원을 먹을 수 있던 문제. `resource.setrlimit`을 쓰는 표준적인
      `preexec_fn` 방식은 멀티스레드 웹 백엔드에서 fork 이후 데드락 위험이
      있어(Python 공식 문서 경고) 피하고, 대신 POSIX 셸의 `ulimit` 빌트인으로
      실제 명령을 감싸서 `exec`으로 셸 자신을 그 명령으로 치환하는 방식을
      씀 — 제한 설정이 파이썬 스레드 상태와 무관한 별도 셸 프로세스 안에서
      끝나고, 별도 프로세스 트리가 안 남는다. CPU 시간 150초 / 가상메모리
      3GB 기본값(`SLITHER_MAX_CPU_SECONDS`/`SLITHER_MAX_MEMORY_KB` env로
      조정 가능). **실제 테스트로 확인한 플랫폼 제약**: macOS는 커널이
      `ulimit -v` 설정 자체를 거부함(`cannot modify limit: Invalid
      argument`) — 이 경우 실패를 무시하고 CPU 제한만 적용되는 best-effort
      로 동작하도록 함(Linux 배포 환경에서는 두 제한 모두 정상 적용).
      `TestWrapWithResourceLimits` 테스트 3개 추가, `vulnerable_vault.sol`
      재실행으로 기존과 동일하게 4개 finding 나오는 것까지 회귀 확인.
    - `pyproject.toml` description을 "LLM 기반..."에서 "Slither 정적분석
      기반... (LLM 미사용)"으로 수정 — "비용에 대한 원칙"과 모순되던 문구
      정리.
    - 테스트 3개 추가로 전체 스위트 88개 전부 통과.
    - **파이프라인 결과 캐싱 추가** (`cache.py` 신규) — 같은 대상(같은 주소,
      또는 동일 "내용"의 로컬 파일 — 경로가 아니라 sha256 해시가 키)을
      재분석하면 Etherscan 재조회+Slither 재실행 없이 캐시된 리포트를 바로
      돌려준다. TTL 기본 6시간(프록시 구현체가 업그레이드될 수 있어 너무
      길게 신뢰하지 않도록 보수적으로 설정, `PIPELINE_CACHE_TTL_SECONDS`로
      조정 가능), CLI `--refresh` 플래그로 강제 무시 가능. `run_pipeline()`이
      유일한 진입점이라 웹 UI(`jobs.py`)도 코드 변경 없이 캐싱 혜택을 그대로
      받는다. 실측: 1차 실행 0.56초 → 캐시 히트 0.07초(Slither 완전히
      스킵). `test_cache.py`(9개) + `test_cli.py` 캐싱 통합 테스트 4개 추가.
    - **`print()` → `logging` 전환** — `cli.py`/`address_fetcher.py`/
      `slither_runner.py`/`web/app.py`의 라이브러리 코드 경로(웹 백엔드에서도
      실행되는 함수들)를 `logging`으로 통일. `python -m auditor.xxx` 직접
      실행 시 최종 결과 출력(`__main__` 블록)은 그대로 `print()` 유지 — 로그가
      아니라 스크립트의 실제 stdout 결과물이라서. `web/app.py`에
      `logging.basicConfig` 추가 — 이게 없으면 uvicorn이 root 로거를 자동
      설정해주지 않아 INFO 로그가 어디에도 안 찍히는 문제가 있었음(직접
      확인). `test_slither_runner.py`의 capsys 의존 테스트 3개를 `caplog`로
      전환.
    - **`detector_explanations.json` 커버리지 36 → 101/101 (100%)** —
      `slither --list-detectors` 전체 목록과 대조해 빠짐없이 채움. 65개
      신규(오라클 연동 관련 니치한 detector 포함), 4개 필수 필드 전부 채움.
      `vulnerable_vault.sol`/`safe_vault.sol` 재실행으로 리포트에 "알려진
      설명 없음" fallback이 0건인 것까지 확인.
    - 테스트 16개 추가로 전체 스위트 100개 전부 통과.
    - **코드 뷰어(인라인 취약점 표기) 추가 — 웹 UI의 주 화면을 리포트에서
      코드 뷰어로 전환.** 사용자가 "이 도구의 목적은 리포트가 아니라 코드의
      어디가 왜 취약한지 보여주는 것"이라고 방향을 잡아서 진행. 새 판단
      로직은 없음 — `preprocess()`가 이미 계산하던 finding별 파일/라인/설명을
      다르게 보여줄 뿐.
      1. **`run_pipeline()` 반환 계약 확장** — `Path` 하나(report.md)만
         반환하던 걸 `PipelineResult`(`pipeline_types.py` 신규,
         `report_path` + `findings_path`)로 바꿈. 코드 뷰어가 쓸 두 번째
         산출물(`<이름>.findings.json` — 구조화된 finding 목록 + 소스 파일
         원문)의 경로를 웹 레이어(`jobs.py`)가 알아야 하는데, 파일명 규칙을
         `web/`에서 다시 계산하면 "웹 레이어는 감싸기만 한다" 원칙이 깨지므로
         반환 계약 자체를 넓히는 쪽을 택함. CLI `__main__`/`test_cli.py`의
         기존 `run_pipeline(...)` 호출부 전부 `.report_path` 접근으로 갱신.
      2. **`preprocess.py`**: `finding["file"]`을 파일명(`Path.name`)에서
         `source_root` 기준 상대경로로 변경(POSIX 슬래시) — 파일명만으로는
         서로 다른 디렉토리의 동명 파일(두 개의 다른 `IERC20.sol` 등)을
         구분 못 하는 문제 해결. `start_line`/`end_line` 정수 필드를 기존
         `"lines"` 문자열 옆에 추가(에디터 데코레이션엔 정수가 필요, 기존
         문자열 포맷은 리포트 호환을 위해 유지). 신규
         `build_source_manifest()` — 코드 뷰어에 넘길 소스 파일 원문 목록을
         만듦(로컬 업로드는 entry 파일 하나만, 주소 조회는 import 그래프
         전체를 entry 파일 우선 정렬로).
      3. **캐시(`cache.py`) 확장** — 예전엔 `report.md` 한 파일만 캐시했는데
         (공유 `work_dir` 전체를 복사하는 위험을 피하려는 의도적 설계였음),
         `findings.json`도 함께 저장/복사하도록 확장. 둘 중 하나라도 없으면
         (이 기능 이전의 옛날 캐시 엔트리 포함) 부분 히트가 아니라 완전
         미스로 처리 — TTL이 6시간이라 한 번 다시 분석하는 비용은 감수
         가능. 캐시 히트에서도 코드 뷰어가 즉시 채워지는 것까지 브라우저로
         확인(WETH9 주소 재제출 → 로그에 "캐시 히트" 찍히고 코드 탭이
         폴링 화면 없이 바로 렌더링됨).
      4. **웹 API**: `GET /api/jobs/{id}/source` 신규(`AnnotatedSourceResponse`
         — findings + source_files). `findings.json`엔 `title`/`explanation`/
         `remediation`/`severity`가 없음(이건 `generate_markdown_report`의
         `enrich_finding()`이 렌더링 시점에만 붙이는 값) — 새 엔드포인트도
         기존 `report/generator.py::enrich_finding` + `load_explanations()`를
         그대로 재사용해서 읽을 때 붙임(로직 재구현 아님, "설명"의 정의가
         한 곳에 유지됨). `web/db.py`에 `findings_path` 컬럼 추가 — 이미
         존재하는 `reports/web_jobs.sqlite3`엔 `CREATE TABLE IF NOT EXISTS`가
         안 먹으므로 `init_db()`에 `PRAGMA table_info` 확인 후
         `ALTER TABLE` 마이그레이션 로직을 명시적으로 추가함(레거시 스키마로
         만들어진 DB에 기존 데이터 보존하면서 컬럼만 추가하는 테스트로 검증).
      5. **프론트엔드 — CodeMirror 6 채택** (Monaco 대신). 이유: 여긴 편집이
         아니라 읽기 전용 진단 뷰만 필요한데 Monaco는 Solidity 모드가 기본
         내장이 아니고 웹워커 번들링이 따로 필요하며 무거움(500KB+).
         CodeMirror 6의 `@codemirror/lint`가 정확히 이 용도(정적
         `linter()` → `Diagnostic[]`)라 인라인 밑줄/gutter 점/hover 상세가
         거의 공짜로 나옴. Solidity 문법은 `@replit/codemirror-lang-solidity`
         (Replit이 유지하는 CM6 전용 패키지, 확인 후 채택 — 애초 계획했던
         `@codemirror/legacy-modes` 기반 clike 대체보다 나음). 신규
         `components/CodeViewer.tsx`(파일 목록 + 진단 + Problems 패널 +
         클릭 시 해당 줄로 스크롤), `pages/JobResultPage.tsx`(`?tab=code|report`
         쿼리로 탭 전환, 기본은 code), `components/ReportView.tsx`(기존
         `ReportPage.tsx`의 렌더링 로직을 `jobId` prop 받는 컴포넌트로 추출).
         `pages/ReportPage.tsx`는 `<Navigate to=".../view?tab=report" />`로
         축소 — 예전 리포트 URL이 계속 동작함(리포트 기능을 없애지 않고
         부가 탭으로 내림). `JobStatusPage.tsx`의 성공 리다이렉트 대상을
         `/report` → `/view`로 변경.
      6. **발견 및 수정한 버그**: `JobResultPage`의 소스 fetch `useEffect`가
         `sourceLoading` state를 의존성 배열에 넣었다가, `setSourceLoading(true)`
         가 effect를 즉시 재실행시켜서 방금 시작한 fetch를 스스로
         cleanup(`cancelled=true`)해버리는 자기취소 버그가 있었음(React
         StrictMode의 이중 effect 실행에서 실제로 재현됨 — 코드 탭이 "코드를
         불러오는 중..."에서 영원히 멈춤). API 응답(`curl`로 직접 확인)은
         정상이었는데 화면만 안 갱신되는 증상으로 발견. `sourceLoading`을
         의존성/가드에서 빼고 렌더링에서도 안 쓰길래(원래 `!source`로 이미
         로딩 여부를 판단하고 있었음) state 자체를 제거해서 해결.
      7. **실제 브라우저로 검증**: WETH9 주소 제출 → 코드 탭 기본 진입 →
         gutter 점/밑줄 표기 → hover 시 title/explanation/remediation 팝업
         → Problems 목록 클릭 시 해당 함수로 스크롤+선택 확인. 리포트 탭
         전환/다운로드 정상. `/jobs/{id}/report` 직접 접속 시
         `/view?tab=report`로 리다이렉트 확인. 히스토리에서 완료 job
         재접속 시 코드 뷰로 정상 진입 확인. 로컬 파일 업로드 경로는
         브라우저 자동화 툴이 `<input type=file>`을 프로그래밍적으로 채울
         수 없어(브라우저 보안 제약) `curl` 멀티파트 업로드로 실제 구동 중인
         백엔드에 대해 직접 검증(성공, 4개 finding, 올바른 source_files/
         finding 매핑 확인). 멀티파일 온체인 주소는 실제 검증된 컨트랙트
         상당수가 remapping 미지원(`@openzeppelin/...`) 또는 구버전 solc
         바이너리 문제로 이 환경에서 컴파일 자체가 실패해(둘 다 이 기능과
         무관한 기존 알려진 한계) 브라우저로는 단일 파일 케이스만 실측
         확인했고, 멀티파일 상대경로/entry-우선-정렬 로직은
         `test_preprocess.py`의 `TestBuildSourceManifest`
         단위 테스트로 검증함.
    - `.claude/launch.json`에 `backend`(uvicorn) 프리뷰 설정 추가 — 기존엔
      `frontend`만 있어서 브라우저 프리뷰로 백엔드를 못 띄웠음. venv
      활성화 없이 `.venv/bin/uvicorn`을 직접 실행하면 solc-select가
      `VIRTUAL_ENV`를 못 봐서(위 "알려진 한계" 참고) 온체인 주소 분석이
      전부 시스템 solc로 폴백하는 걸 실제로 겪어서, `bash -c "source
      .venv/bin/activate && uvicorn ..."` 형태로 감쌈.
    - 백엔드 테스트 추가(`test_preprocess.py`/`test_cache.py`/`test_cli.py`/
      `test_pipeline_integration.py`/`test_web_db.py`/`test_web_api.py`)로
      전체 스위트 113개 전부 통과. 프론트엔드 타입체크(`tsc -b`)/린트
      (`oxlint`) 통과.
    - **코드 뷰어 화면 확대** — 사용자 피드백으로 결과 화면 `max-width`를
      `1100px` → `min(1800px, 96vw)`, 에디터/Problems 패널 높이를
      `70vh` → `calc(100vh - 200px)`로 늘림. 데스크톱/모바일 리사이즈
      양쪽으로 가로 스크롤 없이 잘 들어차는 것까지 확인.
    - **라이트 모드 지원 추가** — 기존엔 다크 전용이었는데, 헤더에 토글
      버튼(해/달 아이콘)을 추가해 라이트/다크를 전환할 수 있게 함.
      - `src/theme.ts` — 초기 테마 결정 로직(localStorage에 저장된 값 우선,
        없으면 `prefers-color-scheme`로 시스템 설정을 따름) + 저장 함수.
        `src/ThemeContext.tsx`의 `ThemeProvider`/`useTheme()`이 이걸 감싸서
        `<html data-theme="...">` 속성을 관리.
      - `main.tsx`에서 React가 마운트되기 **전에** 동기적으로
        `data-theme`를 세팅 — `ThemeProvider`의 `useEffect` 안에서만 하면
        첫 렌더에 다크 기본값이 잠깐 보였다 라이트로 바뀌는 깜빡임(FOUC)이
        생김.
      - `index.css`: 기존 다크 팔레트는 `:root` 기본값 그대로 두고,
        `:root[data-theme="light"]`로 라이트 팔레트를 추가. 같은
        accent/success/warning/error 색상 계열을 유지하되 흰 배경에서
        충분한 대비를 갖도록 더 진한 톤을 씀. 헤더 배경색, 리포트 인라인
        코드 텍스트 색, 버튼 그라데이션 등에 하드코딩되어 있던 hex 값
        3곳을 CSS 변수로 바꿈(`--code-text` 신규 토큰 추가 포함) — 안
        바꾸면 라이트 모드에서도 다크 전용 색이 그대로 남아 깨져 보임.
      - `CodeViewer.tsx`의 CodeMirror 에디터 테마도 앱 테마를 따라
        전환(다크는 기존 `oneDark`, 라이트는 `@uiw/react-codemirror`
        내장 `"light"` 테마 — 새 의존성 추가 없이 해결).
      - 브라우저로 다크/라이트 양쪽 다 확인: 제출 폼, 도움말 패널,
        코드 뷰어(gutter/hover 팝업), 리포트 탭(코드 스니펫 포함) 전부
        라이트 모드에서도 가독성 확인. 새로고침 시 테마 유지(FOUC 없음)도 확인.
    - **프로젝트명을 SA(Smart Contract Auditor)로 변경, GitHub 공개 레포로
      전환.** 이름에 `llm`이 들어가 있었는데 실제로는 LLM을 안 써서 사용자가
      직접 지적, 정리. `pyproject.toml` 패키지명(`sc-auditor`)/FastAPI 앱
      타이틀/README 제목·설명 갱신. 로컬 개발 폴더명도 `sc-auditor`로 변경
      (동명의 무관한 다른 프로젝트가 이미 `~/project/SA`를 쓰고 있어서 로컬
      폴더명은 GitHub 레포명 `SA`와 다르게 감 — 로컬 폴더명과 GitHub 레포명이
      같아야 할 필요는 없다는 걸 이 과정에서 확인). 폴더 rename 직후
      `.venv`가 깨짐(활성화 스크립트에 절대경로가 박혀있어서) — 재생성으로
      해결, venv는 원래 재현 가능한 산출물이라 git에도 안 잡힘. `gh repo
      create --public`으로 https://github.com/ieuns7320/SA 에 push 완료
      (라이선스는 사용자 선택으로 없음 = All rights reserved 유지, CI는
      나중에 별도 진행하기로 함).
    - **README/`pyproject.toml`에서 불필요한 "LLM 미사용" 문구 제거.**
      사용자 지적: "LLM을 전혀 호출하지 않는다" 같은 문구는 프로젝트를
      소개/사용할 때 필요한 정보가 아님(기술 구현 선택이지 사용자 관심사가
      아님). README는 "판단하지 않고 있는 그대로 정리한다"는 실제 동작
      원칙만 남기고 LLM 언급 자체를 뺌. **CLAUDE.md의 이 섹션(비용에 대한
      원칙)과 "하지 말아야 할 것"은 의도적으로 그대로 둠** — 이건 사용자
      안내문이 아니라 AI 에이전트가 이 원칙을 조용히 깨지 않도록 못박아둔
      운영 규칙이라 성격이 다름.
    - **높음 우선순위 실사용 이슈 4건 수정** (사용자가 프로젝트 리뷰를 요청해서
      다시 우선순위 정리 후 진행):
      1. **캐시 무한 증식** — `cache.py::load()`는 만료 판정만 하고 파일은 안
         지웠다. 한 번도 재조회 안 되는 키는 `reports/.cache`에 영원히 남아
         디스크를 계속 잡아먹는 문제. `load()`가 만료/손상 엔트리를 그 자리에서
         지우도록 수정 + 신규 `sweep_expired()`(재조회 안 되는 키까지 정리,
         웹 서버 시작 시 호출).
      2. **레이트리밋이 프로세스 인메모리** — 재시작하면 카운터 리셋, 여러
         워커 프로세스 사이에 공유도 안 됨. Redis 같은 새 인프라를 추가하는
         대신, 이미 있는 `web_jobs.sqlite3`에 `rate_limit_hits` 테이블을
         추가해서 옮김 — 신규 의존성 없이 재시작 생존 + 다중 프로세스 공유
         둘 다 해결. `db.py::check_rate_limit()`이 DELETE(윈도우 밖 정리)
         → COUNT → INSERT를 한 트랜잭션으로 처리해 동시 요청 레이스를
         SQLite 쓰기 락으로 막음. `ratelimit.py`는 `db.check_rate_limit()`을
         호출하는 얇은 래퍼로 축소(라우터 쪽 호출부 `ratelimit.check(...)`는
         무변화). `db.sweep_old_rate_limit_hits()`(24시간 넘은 기록 정리)도
         웹 서버 시작 시 호출. 실제 서버로 재현: curl+브라우저로 요청 보낸 뒤
         `rate_limit_hits` 테이블에 세션/IP별 기록이 실제로 쌓이는 것까지
         확인.
      3. **쿠키 `Secure` 플래그가 기본 꺼짐** — `WEB_SECURE_COOKIES` env를
         배포 시 깜빡하면 HTTPS인데도 세션 쿠키가 평문으로 나갈 위험.
         `session.py::_resolve_secure_cookie_flag()` 신규 — env가 명시적으로
         설정 안 됐으면 요청 자체(스킴 또는 `X-Forwarded-Proto` 헤더, 리버스
         프록시 뒤에 있는 경우 대비)를 보고 자동으로 켠다. env는 자동 판단이
         안 맞는 배포 환경을 위한 탈출구로만 남김. `curl -D -`로 로컬
         `http://`에선 여전히 `Secure` 안 붙는 것, 실제로는 `https` 스킴이면
         자동으로 붙는 것 둘 다 확인.
      4. **코드 뷰어 응답 크기 무제한** — 로컬 업로드는 `uploads.py`가 2MB로
         막지만 온체인 주소 조회는 캡이 없어 대형 멀티파일 컨트랙트의 전체
         소스가 `findings.json`/API 응답에 그대로 embed됐다.
         `preprocess.py::MAX_EMBEDDED_FILE_BYTES`(2MB, 업로드 캡과 동일
         기준) 초과 파일은 내용 대신 안내 문구로 대체하고 `truncated: true`
         표시. `SourceFileOut` 스키마/프론트 `SourceFileOut` 타입에
         `truncated` 필드 추가(기존 findings.json에는 없는 필드라 Pydantic
         기본값 `False`로 하위호환 유지). `CodeViewer.tsx`는 truncated인
         파일은 CodeMirror 대신 플레이스홀더를 보여주고, Problems 목록에서
         그 파일의 finding을 클릭하면 스크롤 시도 없이 파일 전환만 함(에디터가
         아예 안 마운트되므로).
      - 테스트 13개 추가(`test_cache.py`의 만료 삭제/`sweep_expired`,
        `test_web_ratelimit.py` sqlite 기반으로 전면 재작성, 신규
        `test_web_session.py`, `test_preprocess.py`의 truncation)로 전체
        스위트 113 → 126개 전부 통과. 프론트엔드 타입체크/린트 통과.
  - 다음 할 일: 패키지 import remapping 지원, 로컬 파일 입력의 멀티파일 지원.
    그 외 실사용 개선 백로그(아직 미착수): CI 파이프라인 없음(사용자가 나중에
    따로 하기로 함), CLI 옵션 빈약(`chain_id` 등 미노출), 프론트엔드 테스트
    전무. 웹 UI 관련 추가 백로그: 레이트리밋 수치(세션 10/hr, IP 30/hr)는
    여전히 placeholder라 운영하면서 조정 필요, 히스토리 목록에 페이지네이션
    없음(`list_jobs_by_session` 기본 limit=50으로 절단), 프로덕션 배포
    가이드 없음(로컬 dev 워크플로우만 문서화됨 — 프론트엔드가 `/api`를
    상대경로로 호출해서 같은 오리진 배포를 전제하는데 이것도 명시적으로
    문서화된 적 없음), solc-select 부분 설치 실패 자동 복구 없음, 프록시
    1홉만 해석, 코드 뷰어 파일 목록이 트리가 아니라 플랫 리스트.
- [ ] **2단계 (보류)**: RAG 기반 과거 해킹 사례 유사도 매칭. 로컬 임베딩만 사용.
- [ ] **3단계 (보류)**: Foundry PoC 자동 검증.
- [ ] **4단계 (보류, `docs/future/` 참고)**: LLM 판단 레이어 재도입 — 오탐 필터링,
  Slither가 놓친 이슈 발견. 재도입 시 비용 문제를 다시 사용자와 논의할 것.

## 워크플로우

```bash
# 로컬 파일로
python -m auditor.cli tests/fixtures/contracts/vulnerable_vault.sol

# 온체인 주소로 (ETHERSCAN_API_KEY 필요, 무료 발급)
python -m auditor.cli 0x1234...

# 결과: reports/<컨트랙트명>.report.md (사람이 읽는 리포트)
#      reports/<컨트랙트명>.findings.json (구조화된 finding+소스 — 웹 UI 코드 뷰어가 사용)
```

웹 UI로 (로컬 개발):

```bash
# 터미널 하나로 백엔드+프론트엔드를 같이 실행 (Ctrl+C로 둘 다 종료)
./scripts/dev.sh
```

`scripts/dev.sh`가 하는 일: `.venv`/`frontend/node_modules` 존재 확인 → 8000/5173
포트 선점 여부 확인 → 백엔드(`uvicorn --reload`)와 프론트엔드(`npm run dev`)를 배경으로
동시 실행 → `trap`으로 Ctrl+C(SIGINT/TERM) 시 둘 다 정리. `uvicorn --reload`와
`npm run dev`(vite/esbuild) 둘 다 자식 프로세스를 새로 fork하기 때문에, 단순히
최상위 PID만 kill해서는 하위 프로세스가 좀비로 남는다 — 프로세스 트리를 재귀적으로
추적해서 죽이고(`kill_tree`), 혹시 못 잡은 게 있으면 실제 점유 포트(`lsof -ti`) 기준
으로 한 번 더 강제 정리하는 이중 안전장치가 들어있다.

터미널을 따로 쓰고 싶으면 (예: 로그를 분리해서 보고 싶을 때) 여전히 개별 실행 가능:

```bash
# 터미널 1 — 백엔드 (:8000). VIRTUAL_ENV가 설정된 상태(venv 활성화)여야
# solc-select가 올바른 아티팩트 디렉토리를 본다.
source .venv/bin/activate
uvicorn auditor.web.app:app --reload --port 8000

# 터미널 2 — 프론트엔드 (:5173, /api를 :8000으로 프록시)
cd frontend && npm install && npm run dev
```

## 디렉토리 구조

```
src/auditor/
  input/
    address_fetcher.py   Etherscan API로 검증된 소스코드 조회 (무료)
  analyzers/
    slither_runner.py     Slither 서브프로세스 실행 (--solc 플래그로 버전 지정,
                             solc-select use는 안 씀 — 동시 실행 안전)
    preprocess.py           Slither JSON 정제 + 코드 스니펫 첨부. finding['file']은
                               source_root 기준 상대경로, start_line/end_line 정수
                               필드 포함. build_source_manifest()로 코드 뷰어용
                               소스 원문 목록도 생성 — MAX_EMBEDDED_FILE_BYTES(2MB)
                               넘는 파일은 내용 대신 안내 문구 + truncated=True.
  report/
    generator.py             전처리 결과 + 정적 지식베이스 -> Markdown 리포트.
                                enrich_finding()/load_explanations()는 web의
                                /source 엔드포인트에서도 재사용됨.
  web/                     FastAPI 웹 백엔드 (기존 파이프라인을 감싸는 API 레이어)
    app.py                     app factory, lifespan(DB 초기화, ThreadPoolExecutor)
    jobs.py                     job 실행: run_pipeline()을 백그라운드로 감싸는 래퍼
    db.py                        SQLite job 메타데이터 CRUD + list_jobs_by_session
                                    (히스토리용) (reports/web_jobs.sqlite3).
                                    init_db()가 findings_path 컬럼 마이그레이션도 함.
                                    rate_limit_hits 테이블 + check_rate_limit()/
                                    sweep_old_rate_limit_hits()도 여기 있음
                                    (ratelimit.py가 이걸 감싸는 얇은 래퍼).
    schemas.py                    Pydantic 응답 모델 (FindingOut/SourceFileOut/
                                     AnnotatedSourceResponse 포함, SourceFileOut에
                                     truncated: bool = False)
    session.py                    익명 세션 쿠키 (로그인 없음). Secure 플래그는
                                     WEB_SECURE_COOKIES가 명시적으로 없으면 요청
                                     스킴/X-Forwarded-Proto로 자동 판단.
    ratelimit.py                  세션+IP 슬라이딩 윈도우. db.py의 rate_limit_hits
                                     테이블에 저장(재시작 생존, 다중 프로세스 공유,
                                     신규 의존성 없음).
    uploads.py                    업로드 파일 크기/확장자/경로안전 검증
    routers/jobs.py                GET/POST /api/jobs(목록/생성), GET /api/jobs/{id},
                                      GET /api/jobs/{id}/report,
                                      GET /api/jobs/{id}/source(코드 뷰어용)
  knowledge_base/          [2단계 보류]
  verification/            [3단계 보류]
  pipeline_types.py          PipelineResult dataclass (report_path + findings_path) —
                                run_pipeline()의 반환 타입
  cache.py                   파이프라인 결과 파일 캐시 (주소/파일내용 해시 키, TTL 6시간).
                                report.md + findings.json 둘 다 캐시, 하나라도
                                없으면 완전 미스로 취급. load()가 만료/손상 엔트리를
                                그 자리에서 삭제, sweep_expired()로 재조회 안 되는
                                엔트리까지 서버 시작 시 정리(디스크 무한 증식 방지).
  cli.py                     전체 파이프라인 진입점 (입력 -> 분석 -> 리포트+findings,
                                --refresh 지원). run_pipeline()은 PipelineResult 반환.

frontend/                React + Vite + TypeScript 웹 UI
  vite.config.ts             /api를 :8000으로 프록시 (dev 환경 CORS 회피)
  src/theme.ts                  초기 테마 결정(localStorage > prefers-color-scheme) + 저장
  src/ThemeContext.tsx            ThemeProvider/useTheme() — <html data-theme> 관리
  src/api/client.ts            fetch wrapper (job 생성/폴링/리포트+코드뷰어 데이터
                                  조회/히스토리 목록)
  src/components/
    Header.tsx                   모든 페이지 상단 고정 헤더 (도움말/히스토리 링크)
    HelpPanel.tsx                   사용법 3단계 안내 (Header에서 toggle)
    CodeViewer.tsx                  CodeMirror 6 기반 코드+진단 뷰어 (파일 목록,
                                       gutter/인라인 진단, Problems 패널, 클릭 시
                                       스크롤). @uiw/react-codemirror +
                                       @codemirror/lint + @replit/codemirror-lang-solidity.
    ReportView.tsx                   Markdown 리포트 렌더링(marked+dompurify)+다운로드
                                       — ReportPage.tsx에서 추출된 컴포넌트, JobResultPage
                                       리포트 탭에서 재사용
  src/pages/
    SubmitPage.tsx               주소/파일 입력 폼
    JobStatusPage.tsx              2초 간격 상태 폴링, 성공 시 /jobs/:id/view로 이동
    JobResultPage.tsx              주 결과 화면. ?tab=code|report 쿼리로 탭 전환
                                       (기본 code), CodeViewer/ReportView를 각각 렌더링
    ReportPage.tsx                   /jobs/:id/view?tab=report로의 리다이렉트만 함
                                       (예전 리포트 전용 URL 호환용)
    HistoryPage.tsx                  세션이 제출한 job 목록 (최신순)

data/detector_explanations.json   detector별 한국어 설명/해결법 (수동 관리, LLM 아님)

tests/
  test_preprocess.py         전처리 로직(스니펫, 라인범위, noise 필터링, source_root
                                 기준 상대경로, build_source_manifest) 단위 테스트
  test_generator.py           리포트 생성 + detector_explanations.json 필드 검증
  test_cache.py                 파이프라인 결과 캐시 키/TTL/만료 단위 테스트
                                   (report.md+findings.json 동시 캐싱, 만료/손상
                                   엔트리 삭제, sweep_expired() 포함)
  test_slither_runner.py     pragma 파싱, solc-select 폴백, --solc 플래그 전달,
                                 리소스 제한 셸 래핑 단위 테스트
  test_address_fetcher.py   Etherscan 응답 처리 단위 테스트 (requests 모킹, 실제 API 미호출)
  test_cli.py                     입력 라우팅 + .env 자동 로드 + PipelineResult 캐싱 단위 테스트
  test_pipeline_integration.py  실제 slither로 돌리는 end-to-end 테스트 (slither 없으면 skip,
                                   findings.json/source_files까지 검증)
  test_web_db.py                   web/db.py CRUD + list_jobs_by_session + 재시작 후
                                      정리 로직 + findings_path 컬럼 마이그레이션 단위 테스트
  test_web_ratelimit.py              web/ratelimit.py 슬라이딩 윈도우 단위 테스트 (sqlite
                                        기반 — 재시작 생존 회귀 테스트 포함)
  test_web_session.py                web/session.py Secure 쿠키 플래그 자동 판단
                                        (스킴/X-Forwarded-Proto/env 오버라이드) 단위 테스트
  test_web_api.py                      FastAPI TestClient 통합 테스트 (세션 격리, 레이트리밋,
                                          업로드 검증, job 실패 전달, 히스토리 목록,
                                          GET /api/jobs/{id}/source, 실제 slither e2e 1개 포함)
  fixtures/contracts/
    vulnerable_vault.sol    reentrancy, tx.origin, 접근제어 누락 등 포함
    safe_vault.sol            방어 로직 완비 (Slither가 여기선 finding을 거의 안 내야 정상)

docs/future/    LLM 레이어 재도입 시 참고할 이전 설계 문서
reports/          생성된 리포트 + 웹 UI job 메타데이터(web_jobs.sqlite3) (git에 커밋하지 않음)
scripts/dev.sh    백엔드+프론트엔드 동시 실행 스크립트 (터미널 하나로 실행)
```

## 자주 쓰는 명령어

```bash
pip install -e ".[dev]"          # CLI만
pip install -e ".[dev,web]"      # 웹 UI 백엔드까지 포함

# solc 컴파일러 설치 (Apple Silicon Mac)
brew tap ethereum/ethereum && brew install solidity

# 전체 파이프라인 실행 (CLI)
python -m auditor.cli tests/fixtures/contracts/vulnerable_vault.sol

# 각 단계 개별 실행 (디버깅용)
python -m auditor.analyzers.slither_runner <sol_path> <output.json>
python -m auditor.analyzers.preprocess <slither.json> <sol_path>
python -m auditor.report.generator <slither.json> <sol_path>

# 웹 UI 실행 (백엔드+프론트엔드 한 번에, Ctrl+C로 둘 다 종료)
./scripts/dev.sh

# 웹 백엔드만 실행 (venv 활성화 상태에서)
uvicorn auditor.web.app:app --reload --port 8000

# 웹 프론트엔드만 실행
cd frontend && npm install && npm run dev

pytest
```

## 코딩 컨벤션

- Python 3.11+, 타입힌트 필수.
- 라이브러리 코드(웹 백엔드에서도 호출될 수 있는 함수)에서는 `print()` 대신
  `logging`을 쓴다 — `logging.getLogger(__name__)`. `if __name__ == "__main__":`
  블록의 최종 결과 출력(예: `저장됨: ...`)은 로그가 아니라 그 스크립트를 직접
  실행했을 때의 실제 stdout 결과물이므로 예외적으로 `print()` 그대로 둔다.
- 외부 프로세스(Slither) 호출은 항상 타임아웃을 설정한다.
- 신뢰할 수 없는 입력(업로드 파일 등)을 처리하는 subprocess에 자원 제한을
  걸 때는 `preexec_fn` + `resource.setrlimit`을 쓰지 않는다 — 멀티스레드
  프로세스에서 fork 이후 데드락 위험이 있다. 대신 `slither_runner.py`의
  `_wrap_with_resource_limits`처럼 POSIX 셸의 `ulimit`으로 명령을 감싸고
  `exec`으로 셸을 치환하는 방식을 쓴다.
- `data/detector_explanations.json`에 새 detector를 추가할 때는 반드시
  `title`, `explanation`, `remediation`, `default_severity` 네 필드를 모두 채운다.
  하나라도 비어 있으면 리포트에서 어색하게 노출된다.
- 새 detector 대응을 추가했다면 해당 취약점이 실제로 발생하는 fixture가
  `tests/fixtures/contracts/`에 있는지 확인한다.
- `slither_runner.py`에서 `solc-select use <version>`을 다시 쓰지 않는다 —
  전역 상태 전환이라 웹 백엔드의 동시 job 실행에서 레이스 컨디션이 된다.
  버전 지정은 항상 `--solc <경로>` 플래그로.
- `run_pipeline()`의 반환값은 `Path`가 아니라 `pipeline_types.PipelineResult`
  (`report_path` + `findings_path`)다. 파이프라인에 새 산출물을 추가할 때는
  이 dataclass에 필드를 늘리고, `cache.py`의 `store()`/`load()`도 함께
  갱신한다 — 캐시가 새 산출물을 빠뜨리면 캐시 히트 시점에 그 데이터만 없는
  상태가 되는데, 부분 히트로 어물쩍 넘기지 말고 완전 미스로 처리한다(이미
  `findings.json` 도입 때 이 패턴을 따름).
- 웹 레이어(`src/auditor/web/`)는 `auditor.cli.run_pipeline()`을 감싸기만
  한다 — 파이프라인 로직을 웹 레이어에 다시 구현하지 않는다.
- 웹 백엔드에 재시작/다중 프로세스 사이에 공유되어야 하는 상태(레이트리밋
  카운터 등)가 필요해지면, 먼저 이미 있는 `web_jobs.sqlite3`에 테이블을
  추가하는 걸 고려한다 — Redis 같은 새 인프라 의존성을 추가하기 전에.
  실제로 인메모리 레이트리밋을 sqlite로 옮기면서 신규 의존성 없이 "재시작
  생존"과 "다중 프로세스 공유" 두 문제를 한 번에 해결했다.

## 하지 말아야 할 것

- 어떤 LLM API도 코드에서 프로그래밍 방식으로 호출하지 않는다 (위 "비용에 대한
  원칙" 참고).
- `detector_explanations.json`에 없는 detector에 대해 그럴듯한 설명을 지어내지
  않는다 — `report/generator.py`의 fallback처럼 "알려진 설명 없음"이라고 명시한다.
- 이 저장소의 어떤 코드도 실제 메인넷/테스트넷에 트랜잭션을 전송하지 않는다.
- 비공개 컨트랙트 코드를 사용자 동의 없이 외부 서비스로 전송하지 않는다.

## 참고 문서

- Slither detector 문서: https://github.com/crytic/slither/wiki/Detector-Documentation
- Etherscan API 문서: https://docs.etherscan.io/api-endpoints/contracts
