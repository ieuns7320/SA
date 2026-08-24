# llm-contract-auditor

Web3 스마트컨트랙트 정적분석 결과보고서 생성 도구.

```
[컨트랙트 주소 또는 .sol 파일 입력] -> [Slither 취약점 분석] -> [Markdown 결과보고서]
```

**현재 버전은 LLM을 전혀 호출하지 않는다.** Slither 정적분석 결과를 정적 지식베이스
(`data/detector_explanations.json`)로 사람이 읽기 쉽게 정리해서 보여주는 것이
전부다. 비용은 발생하지 않는다. LLM 판단 레이어는 `docs/future/`에 설계만 남겨두고
추후 재도입 여부를 논의한다.

## 빠른 시작

```bash
pip install -e ".[dev]"

# solc 컴파일러 (Apple Silicon Mac)
brew tap ethereum/ethereum && brew install solidity

# 로컬 파일 분석
python -m auditor.cli tests/fixtures/contracts/vulnerable_vault.sol

# 온체인 주소 분석 (.env에 ETHERSCAN_API_KEY 필요, 무료 발급)
cp .env.example .env
python -m auditor.cli 0x1234...
```

결과는 `reports/<컨트랙트명>.report.md`에 저장됩니다.

## 웹 UI로 실행

```bash
pip install -e ".[dev,web]"
cd frontend && npm install && cd ..

./scripts/dev.sh   # 백엔드(:8000)+프론트엔드(:5173)를 한 번에 실행, Ctrl+C로 둘 다 종료
```

브라우저에서 http://localhost:5173 을 엽니다. 두 서버를 각자 다른 터미널에서 따로
띄우고 싶다면 `CLAUDE.md`의 "웹 UI로" 섹션 참고.

## 프로젝트 구조

`CLAUDE.md`의 "디렉토리 구조" 섹션 참고.
