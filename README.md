# SA — Smart Contract Auditor

Web3 스마트컨트랙트 정적분석 도구. 컨트랙트 코드의 어디가 왜 취약한지 인라인
코드 뷰어로 보여주고, Markdown 리포트도 함께 제공한다.

```
[컨트랙트 주소 또는 .sol 파일 입력] -> [Slither 취약점 분석] -> [인라인 코드 뷰어 + Markdown 리포트]
```

Slither가 찾아낸 취약점을 정적 지식베이스(`data/detector_explanations.json`)로
사람이 읽기 쉽게 정리해서 보여준다. **판단은 하지 않는다** — Slither가 찾은 것을
그대로, 다만 이해하기 쉽게 정리할 뿐이다.

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
