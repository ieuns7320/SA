#!/usr/bin/env bash
# 웹 UI 백엔드(:8000)와 프론트엔드(:5173)를 터미널 하나에서 같이 띄운다.
# Ctrl+C 한 번으로 둘 다 종료된다.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -d .venv ]; then
  echo "가상환경(.venv)이 없습니다. 먼저 다음을 실행하세요:" >&2
  echo "  python -m venv .venv && source .venv/bin/activate && pip install -e \".[dev,web]\"" >&2
  exit 1
fi

if [ ! -d frontend/node_modules ]; then
  echo "프론트엔드 의존성이 설치되어 있지 않습니다. 먼저 다음을 실행하세요:" >&2
  echo "  cd frontend && npm install" >&2
  exit 1
fi

check_port() {
  local port="$1" name="$2"
  if lsof -ti ":$port" >/dev/null 2>&1; then
    echo "포트 $port(${name})가 이미 사용 중입니다. 다음으로 정리하세요:" >&2
    echo "  lsof -ti :$port | xargs kill" >&2
    exit 1
  fi
}
check_port 8000 백엔드
check_port 5173 프론트엔드

# shellcheck disable=SC1091
source .venv/bin/activate

BACKEND_PID=""
FRONTEND_PID=""

# uvicorn --reload와 npm run dev 둘 다 자식 프로세스를 새로 fork하기 때문에,
# 배경으로 띄운 PID 하나만 kill해서는 하위 프로세스가 안 죽고 남는다.
# pgrep -P로 자손 프로세스 트리를 재귀적으로 찾아서 전부 종료한다.
kill_tree() {
  local pid="$1"
  local child
  for child in $(pgrep -P "$pid" 2>/dev/null || true); do
    kill_tree "$child"
  done
  kill "$pid" 2>/dev/null || true
}

cleanup() {
  trap - EXIT INT TERM  # cleanup 도중 재진입 방지
  echo ""
  echo "서버 종료 중..."
  [ -n "$BACKEND_PID" ] && kill_tree "$BACKEND_PID"
  [ -n "$FRONTEND_PID" ] && kill_tree "$FRONTEND_PID"
  # vite/esbuild는 detached 프로세스를 띄우기도 해서 위 트리 종료로 못 잡을 때가
  # 있다 — 실제 점유 포트 기준으로 한 번 더 확실히 정리한다. 여기서 wait로
  # 자식이 죽을 때까지 기다리면(특히 프론트엔드 트리가 안 죽었을 때) 스크립트
  # 자체가 멈춰버리므로 기다리지 않는다.
  lsof -ti :8000 2>/dev/null | xargs -r kill -9 2>/dev/null || true
  lsof -ti :5173 2>/dev/null | xargs -r kill -9 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "백엔드 실행 중...  http://localhost:8000"
uvicorn auditor.web.app:app --reload --port 8000 &
BACKEND_PID=$!

echo "프론트엔드 실행 중... http://localhost:5173"
(cd frontend && npm run dev) &
FRONTEND_PID=$!

echo ""
echo "준비 완료 — http://localhost:5173 에서 확인하세요. (Ctrl+C로 둘 다 종료)"
wait
