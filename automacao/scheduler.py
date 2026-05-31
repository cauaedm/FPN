"""
Agendador de tarefas usando APScheduler.
Executa a verificação de novos projetos em intervalos configuráveis.

Uso:
    python scheduler.py            # roda em foreground (Ctrl+C para parar)
    python scheduler.py --once     # executa uma vez e sai (útil para cron)
"""

import logging
import signal
import sys
import time
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from main import executar_ciclo

logger = logging.getLogger(__name__)

# Cron padrão: toda segunda e quinta às 9h
DEFAULT_CRON = {"day_of_week": "mon,thu", "hour": 9, "minute": 0}


def _shutdown(scheduler: BlockingScheduler, signum, frame):
    logger.info("Sinal %s recebido — encerrando scheduler...", signum)
    scheduler.shutdown(wait=False)
    sys.exit(0)


def iniciar_scheduler(cron: dict = None):
    """Inicia o scheduler em modo blocking (foreground)."""
    cron = cron or DEFAULT_CRON

    scheduler = BlockingScheduler(timezone="America/Sao_Paulo")
    scheduler.add_job(
        executar_ciclo,
        trigger=CronTrigger(**cron, timezone="America/Sao_Paulo"),
        id="verificar_projetos",
        name="Verificar novos projetos de extensão",
        misfire_grace_time=3600,
        max_instances=1,
    )

    signal.signal(signal.SIGTERM, lambda s, f: _shutdown(scheduler, s, f))
    signal.signal(signal.SIGINT, lambda s, f: _shutdown(scheduler, s, f))

    proxima = scheduler.get_job("verificar_projetos").next_run_time
    logger.info("Scheduler iniciado. Próxima execução: %s", proxima)
    logger.info("Cron configurado: %s", cron)

    scheduler.start()


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if "--once" in sys.argv:
        logger.info("Modo --once: executando ciclo único.")
        executar_ciclo()
        sys.exit(0)

    # Cron configurável via env
    cron_override = {}
    if os.environ.get("CRON_HOUR"):
        cron_override["hour"] = os.environ["CRON_HOUR"]
    if os.environ.get("CRON_MINUTE"):
        cron_override["minute"] = os.environ["CRON_MINUTE"]
    if os.environ.get("CRON_DAY_OF_WEEK"):
        cron_override["day_of_week"] = os.environ["CRON_DAY_OF_WEEK"]

    iniciar_scheduler(cron={**DEFAULT_CRON, **cron_override})
