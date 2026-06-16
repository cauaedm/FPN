"""
Painel do Comitê de Extensão, protegido por login com sessão.

  GET  /admin/login                 → tela de login
  POST /admin/login                 → autentica (COMITE_USER/COMITE_PASSWORD)
  GET  /admin/logout                → encerra a sessão
  GET  /admin                       → lista submissões (filtro por status)
  GET  /admin/submissao/{id}        → detalhe + conferência no SIGA
  POST /admin/submissao/{id}/decidir→ verificar | aprovar | rejeitar
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
from fastapi.templating import Jinja2Templates

from db import storage
from main import CANAIS, executar_ciclo
from siga.client import Projeto, buscar_acao_por, buscar_projetos_ic

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


class NaoAutenticado(Exception):
    """Levantada quando a sessão não está autenticada (redireciona p/ login)."""


def exigir_login(request: Request):
    if not request.session.get("autenticado"):
        raise NaoAutenticado()


def _credenciais_ok(usuario: str, senha: str) -> bool:
    esperado_user = os.environ.get("COMITE_USER", "comite")
    esperado_senha = os.environ.get("COMITE_PASSWORD", "")
    user_ok = secrets.compare_digest(usuario, esperado_user)
    pass_ok = bool(esperado_senha) and secrets.compare_digest(senha, esperado_senha)
    return user_ok and pass_ok


# Rotas públicas de autenticação (sem o guard de login).
auth_router = APIRouter(prefix="/admin")


@auth_router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, erro: str | None = None):
    if request.session.get("autenticado"):
        return RedirectResponse(url="/admin", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"erro": erro})


@auth_router.post("/login")
def login(request: Request, usuario: str = Form(...), senha: str = Form(...)):
    if not _credenciais_ok(usuario, senha):
        return templates.TemplateResponse(
            request, "login.html", {"erro": "Usuário ou senha inválidos."}, status_code=401
        )
    request.session["autenticado"] = True
    request.session["usuario"] = usuario
    return RedirectResponse(url="/admin", status_code=303)


@auth_router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/admin/login", status_code=303)


# Rotas protegidas: exigem sessão autenticada.
router = APIRouter(prefix="/admin", dependencies=[Depends(exigir_login)])


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def listar(request: Request, status: str | None = None, msg: str | None = None):
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
        {"submissoes": submissoes, "filtro": status, "contagem": contagem, "msg": msg},
    )


@router.get("/submissao/{sid}", response_class=HTMLResponse)
def detalhe(request: Request, sid: int):
    sub = storage.obter_submissao(sid)
    if not sub:
        raise HTTPException(status_code=404, detail="Submissão não encontrada")

    # Tenta localizar a ação correspondente no SIGA.
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
        _notificar_aprovacao(sub)
    elif acao == "rejeitar":
        storage.decidir_submissao(sid, status="rejeitado", motivo_rejeicao=motivo)
        _notificar_rejeicao(sub, motivo)
    else:
        raise HTTPException(status_code=400, detail="Ação inválida")

    return RedirectResponse(url=f"/admin/submissao/{sid}", status_code=303)


@router.post("/submissao/{sid}/excluir")
def excluir_submissao(sid: int):
    storage.excluir_submissao(sid)
    return RedirectResponse(url="/admin?msg=Submissao+excluida", status_code=303)


@router.post("/submissoes/resetar")
def resetar_submissoes():
    storage.resetar_submissoes_externas()
    return RedirectResponse(
        url="/admin?msg=Submissoes+resetadas+(pendentes+e+nao+divulgadas)",
        status_code=303,
    )


def _email_coordenador(sub: dict, acao: str):
    """Retorna (notificador, destino) ou (None, None) se não der p/ notificar."""
    destino = sub.get("coordenador_email")
    if not destino:
        logger.warning("Submissão #%s sem e-mail do coordenador — sem %s.", sub["id"], acao)
        return None, None
    try:
        from notificadores.email_notificador import EmailNotificador
        return EmailNotificador.from_env(), destino
    except Exception as exc:
        logger.warning("E-mail não configurado — %s não notificada: %s", acao, exc)
        return None, None


def _notificar_aprovacao(sub: dict):
    """Avisa o coordenador que a extensão foi aprovada e será divulgada."""
    notif, destino = _email_coordenador(sub, "aprovação")
    if not notif:
        return
    corpo = (
        f"Olá,\n\n"
        f"Sua solicitação de divulgação da extensão \"{sub['nome_extensao']}\" "
        f"foi APROVADA pelo Comitê de Extensão do IC/UFRJ.\n\n"
        f"A extensão passará a ser divulgada aos alunos do Instituto de Computação "
        f"e aparecerá no portal de extensões do IC.\n\n"
        f"Atenciosamente,\nComitê de Extensão — IC/UFRJ"
    )
    notif.enviar_texto(destino, "[IC/UFRJ Extensão] Sua solicitação foi aprovada", corpo)


def _notificar_rejeicao(sub: dict, motivo: str):
    """Avisa o coordenador sobre a rejeição (best-effort)."""
    notif, destino = _email_coordenador(sub, "rejeição")
    if not notif:
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


# ── Divulgação das extensões do IC (portal SIGA) ──────────────────────────────

def _submissao_para_projeto(sub: dict) -> Projeto:
    """Converte uma submissão externa aprovada em Projeto, para reusar os notificadores.
    Usa id 'sub-<id>' para não colidir com os ids numéricos do SIGA no dedup."""
    return Projeto(
        id=f"sub-{sub['id']}",
        titulo=sub["nome_extensao"],
        coordenador=sub.get("coordenador_nome") or "",
        unidade="Extensão externa",
        modalidade="Extensão externa",
        area="",
        resumo=sub.get("descricao") or "",
        descricao=sub.get("descricao") or "",
        vagas=None,
        data_inicio=None,
        data_termino=None,
        data_inicio_inscricoes=None,
        data_termino_inscricoes=None,
        como_inscrever=sub.get("processo_seletivo") or "",
        link_inscricoes=sub.get("link_siga") or "",
        contato=sub.get("contato") or "",
        email_atendimento=sub.get("contato") or sub.get("coordenador_email") or "",
        telefone="",
        publico=sub.get("perfil_desejado") or "",
    )


@router.get("/divulgacao", response_class=HTMLResponse)
def divulgacao(request: Request):
    """Lista extensões do IC (portal SIGA) + externas aprovadas, com status de divulgação."""
    itens = []
    erro = None
    try:
        for p in buscar_projetos_ic(incluir_encerrados=True):
            itens.append({
                "projeto": p,
                "status": {canal: storage.ja_notificado(p.id, canal) for canal in CANAIS},
                "origem": "portal",
            })
    except Exception as exc:
        erro = str(exc)
        logger.error("Falha ao buscar SIGA para /admin/divulgacao: %s", exc)

    for s in storage.listar_submissoes(status="aprovado"):
        p = _submissao_para_projeto(s)
        itens.append({
            "projeto": p,
            "status": {canal: storage.ja_notificado(p.id, canal) for canal in CANAIS},
            "origem": "externa",
        })

    return templates.TemplateResponse(
        request,
        "admin_divulgacao.html",
        {
            "itens": itens,
            "erro": erro,
            "canais": CANAIS,
        },
    )


@router.post("/divulgacao/divulgar")
def divulgar(request: Request, projeto_id: str = Form(...)):
    """Dispara a divulgação de uma extensão (portal SIGA ou externa) com retorno por canal."""
    if projeto_id.startswith("sub-"):
        sub = storage.obter_submissao(int(projeto_id[4:]))
        alvo = _submissao_para_projeto(sub) if sub else None
    else:
        alvo = next(
            (p for p in buscar_projetos_ic(incluir_encerrados=True) if p.id == projeto_id),
            None,
        )
    if not alvo:
        raise HTTPException(status_code=404, detail="Extensão não encontrada")
    _divulgar_projeto(alvo)
    return RedirectResponse(url="/admin/divulgacao", status_code=303)


def _divulgar_projeto(p) -> dict:
    """Envia a divulgação por canal e devolve {canal: mensagem} explicando o resultado.
    Só envia em canais ainda não notificados (dedup) e registra cada tentativa."""
    from notificadores.email_notificador import EmailNotificador
    from notificadores.telegram_notificador import TelegramNotificador

    res: dict[str, str] = {}

    # E-mail (destinatários da tabela assinantes)
    if storage.ja_notificado(p.id, "email"):
        res["email"] = "já divulgado"
    else:
        try:
            notif = EmailNotificador.from_env()
        except KeyError as e:
            res["email"] = f"não configurado (falta {e})"
        else:
            dest = storage.listar_assinantes("email")
            if not dest:
                res["email"] = "nenhum assinante cadastrado"
            else:
                enviados = 0
                ultimo_erro = ""
                for d in dest:
                    ok, erro = notif.enviar_detalhado(d, p)
                    storage.registrar_envio(p.id, "email", d, ok, erro)
                    if ok:
                        enviados += 1
                    elif erro:
                        ultimo_erro = erro
                if enviados == len(dest):
                    storage.marcar_notificado(p.id, "email")
                    res["email"] = f"enviado p/ {enviados} assinante(s)"
                elif enviados:
                    res["email"] = f"parcial: {enviados}/{len(dest)} — {ultimo_erro}"
                else:
                    res["email"] = f"falha: {ultimo_erro or 'ver logs'}"

    # Telegram (chat_ids da env)
    if storage.ja_notificado(p.id, "telegram"):
        res["telegram"] = "já divulgado"
    else:
        try:
            notif = TelegramNotificador.from_env()
        except KeyError as e:
            res["telegram"] = f"não configurado (falta {e})"
        else:
            if not notif.chat_ids:
                res["telegram"] = "nenhum chat_id configurado"
            else:
                r = notif.enviar_para_todos(p)
                for cid, ok in r.items():
                    storage.registrar_envio(p.id, "telegram", cid, ok)
                if all(r.values()):
                    storage.marcar_notificado(p.id, "telegram")
                    res["telegram"] = f"enviado p/ {len(r)} chat(s)"
                else:
                    res["telegram"] = "falha (ver logs)"

    logger.info("Divulgação manual '%s': %s", p.titulo, res)
    return res


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
