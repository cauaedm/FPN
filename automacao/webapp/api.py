"""
Rotas públicas da API:
  - POST /api/submissoes  → recebe a submissão de extensão externa (RF05)
  - GET  /api/extensoes   → lista consolidada (SIGA-IC + externas aprovadas) (RF11/RF12)
"""

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from db import storage
from siga.client import Projeto, buscar_projetos_ic

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


class SubmissaoIn(BaseModel):
    nome_extensao: str = Field(min_length=3)
    descricao: str = Field(min_length=10)
    perfil_desejado: str | None = None
    bolsa: bool = False
    processo_seletivo: str | None = None
    contato: str | None = None
    link_siga: str | None = None
    coordenador_nome: str | None = None
    coordenador_email: str | None = None
    website: str | None = None  # honeypot anti-spam (deve vir vazio)


def _card_interno(p: Projeto) -> dict:
    ano_inicio = (p.data_inicio or "")[:4] or None
    return {
        "titulo": p.titulo,
        "coordenador": p.coordenador,
        "area": p.area or None,
        "modalidade": p.modalidade or None,
        "descricao": p.resumo or p.descricao or "",
        "vagas": p.vagas,
        "bolsa": None,
        "processo_seletivo": p.como_inscrever or None,
        "perfil": p.publico or None,
        "contato": p.email_atendimento or p.contato or None,
        "link_inscricao": p.link_inscricoes or None,
        "ano_inicio": ano_inicio,
        "ano_fim": None,
        "origem": "interna",
    }


def _card_externo(s: dict) -> dict:
    return {
        "titulo": s["nome_extensao"],
        "coordenador": s.get("coordenador_nome") or "—",
        "area": None,
        "modalidade": "Extensão externa",
        "descricao": s.get("descricao") or "",
        "vagas": None,
        "bolsa": bool(s.get("bolsa")),
        "processo_seletivo": s.get("processo_seletivo") or None,
        "perfil": s.get("perfil_desejado") or None,
        "contato": s.get("contato") or None,
        "link_inscricao": s.get("link_siga") or None,
        "ano_inicio": (s.get("criado_em") or "")[:4] or None,
        "ano_fim": None,
        "origem": "externa",
    }


@router.get("/extensoes")
def listar_extensoes() -> list[dict]:
    """Consolida extensões internas (SIGA-IC ativas) e externas aprovadas."""
    cards: list[dict] = []
    try:
        for p in buscar_projetos_ic():
            cards.append(_card_interno(p))
    except Exception as exc:  # API do SIGA fora do ar não derruba o endpoint
        logger.error("Falha ao buscar SIGA para /api/extensoes: %s", exc)

    for s in storage.listar_submissoes(status="aprovado"):
        cards.append(_card_externo(s))

    return cards


@router.post("/submissoes")
def criar_submissao(dados: SubmissaoIn) -> dict:
    """Recebe a solicitação de divulgação (RF05). Entra como 'pendente'."""
    if dados.website:  # honeypot preenchido → provável bot
        return {"ok": True}
    novo_id = storage.criar_submissao(dados.model_dump(exclude={"website"}))
    return {"ok": True, "id": novo_id}
