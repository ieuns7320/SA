"""FastAPI app factory.

기존 CLI 파이프라인(auditor.cli.run_pipeline)을 감싸는 얇은 API 레이어일 뿐이다.
LLM 호출은 여기서도 없다 — CLAUDE.md의 비용 원칙 참고.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from auditor.web import db
from auditor.web.jobs import create_executor
from auditor.web.routers.jobs import router as jobs_router

logger = logging.getLogger(__name__)

MAX_CONCURRENT_JOBS = int(os.environ.get("WEB_MAX_CONCURRENT_JOBS", "2"))

# 웹 백엔드는 uvicorn이 "uvicorn"/"uvicorn.error"/"uvicorn.access" 로거만 설정하고
# 루트 로거는 그대로 두기 때문에, 여기서 직접 설정하지 않으면 auditor.* 로거의
# INFO 레벨 로그(파이프라인 진행상황 등)가 어디에도 찍히지 않는다. basicConfig는
# 이미 핸들러가 있으면(예: 테스트의 로그 캡처) 조용히 no-op이라 여러 번 호출돼도
# 안전하다.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

# Vite dev 서버 프록시를 쓰면 same-origin이라 CORS가 필요 없지만, 누군가 :5173을
# 거치지 않고 :8000을 직접 호출하는 경우를 위한 안전망으로만 둔다.
# allow_origins=["*"] + allow_credentials=True 조합은 브라우저가 거부하며,
# 실제로 위험하므로 절대 쓰지 않는다.
DEV_FRONTEND_ORIGIN = "http://localhost:5173"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    stale = db.sweep_stale_jobs()
    if stale:
        logger.info("이전 실행에서 멈춘 job %d개를 failed로 정리했습니다.", stale)
    app.state.executor = create_executor(MAX_CONCURRENT_JOBS)
    yield
    app.state.executor.shutdown(wait=False)


def create_app() -> FastAPI:
    app = FastAPI(title="llm-contract-auditor web", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[DEV_FRONTEND_ORIGIN],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(jobs_router)
    return app


app = create_app()
