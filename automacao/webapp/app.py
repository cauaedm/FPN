"""
Ponto de entrada do web service (FastAPI + Uvicorn).

Sobe a API pública e o painel do Comitê e, em background, mantém o
agendador (APScheduler) que dispara o ciclo de notificação do SIGA —
substituindo o antigo `scheduler.py` rodando como processo separado.

Execução local:
    uvicorn webapp.app:app --reload
"""

import logging
import os
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db import storage
from main import executar_ciclo
from scheduler import DEFAULT_CRON
from webapp.admin import router as admin_router
from webapp.api import router as api_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _cron_config() -> dict:
    """Monta o cron a partir do padrão + overrides via env (CRON_*)."""
    cron = dict(DEFAULT_CRON)
    if os.environ.get("CRON_HOUR"):
        cron["hour"] = os.environ["CRON_HOUR"]
    if os.environ.get("CRON_MINUTE"):
        cron["minute"] = os.environ["CRON_MINUTE"]
    if os.environ.get("CRON_DAY_OF_WEEK"):
        cron["day_of_week"] = os.environ["CRON_DAY_OF_WEEK"]
    return cron


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage.inicializar()

    global _scheduler
    cron = _cron_config()
    _scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")
    _scheduler.add_job(
        executar_ciclo,
        trigger=CronTrigger(**cron, timezone="America/Sao_Paulo"),
        id="verificar_projetos",
        name="Verificar novos projetos de extensão",
        misfire_grace_time=3600,
        max_instances=1,
    )
    _scheduler.start()
    logger.info("Scheduler em background iniciado. Cron: %s", cron)

    yield

    if _scheduler:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler encerrado.")


app = FastAPI(title="Portal de Extensões IC/UFRJ", lifespan=lifespan)

# CORS: permite o site (GitHub Pages) consumir a API em runtime.
_origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGIN", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins or ["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(admin_router)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
