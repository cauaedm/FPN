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

            -- Submissões de extensões externas (RF05-RF09).
            -- status: pendente | verificado | aprovado | rejeitado
            CREATE TABLE IF NOT EXISTS submissoes (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                nome_extensao       TEXT NOT NULL,
                descricao           TEXT NOT NULL,
                perfil_desejado     TEXT,
                bolsa               INTEGER NOT NULL DEFAULT 0,
                processo_seletivo   TEXT,
                contato             TEXT,
                link_siga           TEXT,
                coordenador_nome    TEXT,
                coordenador_email   TEXT,
                status              TEXT NOT NULL DEFAULT 'pendente',
                verificado_siga     INTEGER NOT NULL DEFAULT 0,
                motivo_rejeicao     TEXT,
                criado_em           TEXT NOT NULL DEFAULT (datetime('now')),
                decidido_em         TEXT
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


def listar_log_envios(limite: int = 100) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM log_envios ORDER BY id DESC LIMIT ?",
            (limite,),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Submissões de extensões externas (RF05-RF09) ──────────────────────────────

def criar_submissao(dados: dict) -> int:
    """Cria uma submissão com status 'pendente'. Retorna o id gerado."""
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO submissoes
                 (nome_extensao, descricao, perfil_desejado, bolsa,
                  processo_seletivo, contato, link_siga,
                  coordenador_nome, coordenador_email)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                dados["nome_extensao"],
                dados["descricao"],
                dados.get("perfil_desejado"),
                int(bool(dados.get("bolsa"))),
                dados.get("processo_seletivo"),
                dados.get("contato"),
                dados.get("link_siga"),
                dados.get("coordenador_nome"),
                dados.get("coordenador_email"),
            ),
        )
        novo_id = cur.lastrowid
    logger.info("Submissão criada: #%s — %s", novo_id, dados.get("nome_extensao"))
    return novo_id


def listar_submissoes(status: str = None) -> list[dict]:
    with _connect() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM submissoes WHERE status=? ORDER BY id DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM submissoes ORDER BY id DESC"
            ).fetchall()
    return [dict(r) for r in rows]


def obter_submissao(submissao_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM submissoes WHERE id=?", (submissao_id,)
        ).fetchone()
    return dict(row) if row else None


def excluir_submissao(submissao_id: int):
    """Remove uma submissão e a marca de divulgação dela ('sub-<id>')."""
    with _connect() as conn:
        conn.execute("DELETE FROM submissoes WHERE id=?", (submissao_id,))
        conn.execute(
            "DELETE FROM projetos_notificados WHERE projeto_id=?",
            (f"sub-{submissao_id}",),
        )
    logger.info("Submissão #%s excluída.", submissao_id)


def resetar_submissoes_externas():
    """Volta todas as submissões para 'pendente' e limpa a divulgação das externas."""
    with _connect() as conn:
        conn.execute(
            """UPDATE submissoes
               SET status='pendente', verificado_siga=0,
                   motivo_rejeicao=NULL, decidido_em=NULL"""
        )
        conn.execute("DELETE FROM projetos_notificados WHERE projeto_id LIKE 'sub-%'")
    logger.info("Submissões externas resetadas (pendentes + não divulgadas).")


def decidir_submissao(
    submissao_id: int,
    status: str,
    verificado_siga: bool = None,
    motivo_rejeicao: str = None,
):
    """Atualiza o status de uma submissão (verificado/aprovado/rejeitado)."""
    campos = ["status=?", "decidido_em=?"]
    valores = [status, datetime.utcnow().isoformat()]
    if verificado_siga is not None:
        campos.append("verificado_siga=?")
        valores.append(int(verificado_siga))
    if motivo_rejeicao is not None:
        campos.append("motivo_rejeicao=?")
        valores.append(motivo_rejeicao)
    valores.append(submissao_id)

    with _connect() as conn:
        conn.execute(
            f"UPDATE submissoes SET {', '.join(campos)} WHERE id=?",
            valores,
        )
    logger.info("Submissão #%s → %s", submissao_id, status)
