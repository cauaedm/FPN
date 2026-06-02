"""
Painel do Comitê de Extensão (RF06-RF09), protegido por senha compartilhada.

  GET  /admin                       → lista submissões (filtro por status)
  GET  /admin/submissao/{id}        → detalhe + conferência no SIGA (RF06/RF07)
  POST /admin/submissao/{id}/decidir→ verificar | aprovar | rejeitar (RF08/RF09)
  GET  /admin/automacoes            → interação com as automações + banco
  POST /admin/automacoes/rodar-ciclo
  POST /admin/automacoes/assinante
"""

import logging
import os
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates

from db import storage
from main import executar_ciclo
from siga.client import buscar_acao_por

logger = logging.getLogger(__name__)

security = HTTPBasic()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def verificar_senha(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    senha = os.environ.get("COMITE_PASSWORD", "")
    usuario = os.environ.get("COMITE_USER", "comite")
    user_ok = secrets.compare_digest(credentials.username, usuario)
    pass_ok = bool(senha) and secrets.compare_digest(credentials.password, senha)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=401,
            detail="Não autorizado",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


router = APIRouter(prefix="/admin", dependencies=[Depends(verificar_senha)])


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def listar(request: Request, status: str | None = None):
    submissoes = storage.listar_submissoes(status=status or None)
    contagem = {
        "pendente": len(storage.listar_submissoes("pendente")),
        "verificado": len(storage.listar_submissoes("verificado")),
        "aprovado": len(storage.listar_submissoes("aprovado")),
        "rejeitado": len(storage.listar_submissoes("rejeitado")),
    }
    return templates.TemplateResponse(
        request,
        "admin_list.html",
        {"submissoes": submissoes, "filtro": status, "contagem": contagem},
    )


@router.get("/submissao/{sid}", response_class=HTMLResponse)
def detalhe(request: Request, sid: int):
    sub = storage.obter_submissao(sid)
    if not sub:
        raise HTTPException(status_code=404, detail="Submissão não encontrada")

    # Conferência manual no SIGA (RF06): tenta localizar a ação correspondente.
    siga = None
    try:
        siga = buscar_acao_por(link=sub.get("link_siga"), email=sub.get("coordenador_email"))
    except Exception as exc:
        logger.error("Falha ao consultar SIGA para submissão #%s: %s", sid, exc)

    return templates.TemplateResponse(
        request,
        "admin_detail.html",
        {"s": sub, "siga": siga},
    )


@router.post("/submissao/{sid}/decidir")
def decidir(sid: int, acao: str = Form(...), motivo: str = Form("")):
    sub = storage.obter_submissao(sid)
    if not sub:
        raise HTTPException(status_code=404, detail="Submissão não encontrada")

    if acao == "verificar":
        storage.decidir_submissao(sid, status="verificado", verificado_siga=True)
    elif acao == "aprovar":
        storage.decidir_submissao(sid, status="aprovado", verificado_siga=True)
    elif acao == "rejeitar":
        storage.decidir_submissao(sid, status="rejeitado", motivo_rejeicao=motivo)
        _notificar_rejeicao(sub, motivo)
    else:
        raise HTTPException(status_code=400, detail="Ação inválida")

    return RedirectResponse(url=f"/admin/submissao/{sid}", status_code=303)


def _notificar_rejeicao(sub: dict, motivo: str):
    """RF09: avisa o coordenador sobre a rejeição (best-effort)."""
    destino = sub.get("coordenador_email")
    if not destino:
        logger.warning("Submissão #%s sem e-mail do coordenador — sem notificação.", sub["id"])
        return
    try:
        from notificadores.email_notificador import EmailNotificador
        notif = EmailNotificador.from_env()
    except Exception as exc:
        logger.warning("E-mail não configurado — rejeição não notificada: %s", exc)
        return

    corpo = (
        f"Olá,\n\n"
        f"Sua solicitação de divulgação da extensão \"{sub['nome_extensao']}\" "
        f"não foi aprovada pelo Comitê de Extensão do IC/UFRJ.\n\n"
        f"Motivo: {motivo or 'não informado'}\n\n"
        f"Você pode ajustar o cadastro (ex.: regularizar no SIGA) e submeter novamente.\n\n"
        f"Atenciosamente,\nComitê de Extensão — IC/UFRJ"
    )
    notif.enviar_texto(destino, "[IC/UFRJ Extensão] Sua solicitação não foi aprovada", corpo)


# ── Interação com as automações + banco ───────────────────────────────────────

@router.get("/automacoes", response_class=HTMLResponse)
def automacoes(request: Request, msg: str | None = None):
    return templates.TemplateResponse(
        request,
        "admin_automacoes.html",
        {
            "msg": msg,
            "assinantes_email": storage.listar_assinantes("email"),
            "logs": storage.listar_log_envios(50),
        },
    )


@router.post("/automacoes/rodar-ciclo")
def rodar_ciclo():
    executar_ciclo()
    return RedirectResponse(url="/admin/automacoes?msg=Ciclo+executado", status_code=303)


@router.post("/automacoes/assinante")
def gerir_assinante(acao: str = Form(...), canal: str = Form("email"), destino: str = Form(...)):
    if acao == "add":
        storage.adicionar_assinante(canal, destino)
    elif acao == "remove":
        storage.remover_assinante(canal, destino)
    return RedirectResponse(url="/admin/automacoes?msg=Assinantes+atualizados", status_code=303)
