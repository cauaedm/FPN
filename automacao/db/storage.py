"""
Armazenamento local (SQLite) para rastrear projetos já notificados.
Evita reenvio de notificações duplicadas.
"""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "data" / "fpn.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def inicializar():
    """Cria as tabelas se não existirem."""
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS projetos_notificados (
                projeto_id      TEXT NOT NULL,
                canal           TEXT NOT NULL,  -- 'email' | 'telegram' | 'whatsapp'
                notificado_em   TEXT NOT NULL,
                PRIMARY KEY (projeto_id, canal)
            );

            CREATE TABLE IF NOT EXISTS assinantes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                canal       TEXT NOT NULL,       -- 'email' | 'telegram' | 'whatsapp'
                destino     TEXT NOT NULL,        -- endereço / chat_id / número
                ativo       INTEGER NOT NULL DEFAULT 1,
                criado_em   TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS log_envios (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                projeto_id  TEXT NOT NULL,
                canal       TEXT NOT NULL,
                destino     TEXT NOT NULL,
                sucesso     INTEGER NOT NULL,
                erro        TEXT,
                enviado_em  TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)
    logger.info("Banco inicializado em: %s", DB_PATH)


# ── Projetos notificados ────────────────────────────────────────────────────

def ja_notificado(projeto_id: str, canal: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM projetos_notificados WHERE projeto_id=? AND canal=?",
            (projeto_id, canal),
        ).fetchone()
    return row is not None


def marcar_notificado(projeto_id: str, canal: str):
    with _connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO projetos_notificados (projeto_id, canal, notificado_em)
               VALUES (?, ?, ?)""",
            (projeto_id, canal, datetime.utcnow().isoformat()),
        )


# ── Assinantes ──────────────────────────────────────────────────────────────

def listar_assinantes(canal: str) -> list[str]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT destino FROM assinantes WHERE canal=? AND ativo=1",
            (canal,),
        ).fetchall()
    return [r["destino"] for r in rows]


def adicionar_assinante(canal: str, destino: str):
    with _connect() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO assinantes (canal, destino, criado_em)
               VALUES (?, ?, ?)""",
            (canal, destino, datetime.utcnow().isoformat()),
        )
    logger.info("Assinante adicionado: [%s] %s", canal, destino)


def remover_assinante(canal: str, destino: str):
    with _connect() as conn:
        conn.execute(
            "UPDATE assinantes SET ativo=0 WHERE canal=? AND destino=?",
            (canal, destino),
        )
    logger.info("Assinante removido: [%s] %s", canal, destino)


# ── Log de envios ────────────────────────────────────────────────────────────

def registrar_envio(projeto_id: str, canal: str, destino: str, sucesso: bool, erro: str = ""):
    with _connect() as conn:
        conn.execute(
            """INSERT INTO log_envios (projeto_id, canal, destino, sucesso, erro)
               VALUES (?, ?, ?, ?, ?)""",
            (projeto_id, canal, destino, int(sucesso), erro),
        )
