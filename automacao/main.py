"""
Ponto de entrada principal da automação de extensões IC/UFRJ.

Uso:
    python main.py                         # ciclo completo (todos os canais)
    python main.py --canal email           # apenas e-mail
    python main.py --canal telegram        # apenas Telegram
    python main.py --canal whatsapp        # apenas WhatsApp
    python main.py --listar                # lista projetos ativos do IC (sem enviar)
    python main.py --assinantes add email fulano@ic.ufrj.br
    python main.py --assinantes add telegram -1001234567890
    python main.py --assinantes add whatsapp 5521999999999
    python main.py --testar                # envia mensagens de teste (1 projeto)
"""

import argparse
import logging
import os
import sys
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Adiciona o diretório pai ao path para imports relativos funcionarem
sys.path.insert(0, os.path.dirname(__file__))

from siga.client import buscar_projetos_ic, Projeto
from db import storage
from notificadores.email_notificador import EmailNotificador
from notificadores.telegram_notificador import TelegramNotificador


CANAIS = ["email", "telegram"]


def _notificador_email() -> EmailNotificador | None:
    try:
        return EmailNotificador.from_env()
    except KeyError as e:
        logger.warning("Email não configurado (falta %s) — ignorando canal.", e)
        return None


def _notificador_telegram() -> TelegramNotificador | None:
    try:
        return TelegramNotificador.from_env()
    except KeyError as e:
        logger.warning("Telegram não configurado (falta %s) — ignorando canal.", e)
        return None


def processar_projeto(projeto: Projeto, canais: list[str]):
    """Envia notificações de um projeto nos canais especificados (se ainda não enviado)."""

    if "email" in canais:
        if not storage.ja_notificado(projeto.id, "email"):
            notif = _notificador_email()
            if notif:
                destinatarios = storage.listar_assinantes("email")
                if destinatarios:
                    resultados = notif.enviar_para_lista(destinatarios, projeto)
                    sucesso = all(resultados.values())
                    for dest, ok in resultados.items():
                        storage.registrar_envio(projeto.id, "email", dest, ok)
                    if sucesso:
                        storage.marcar_notificado(projeto.id, "email")
                else:
                    logger.info("Nenhum assinante de e-mail cadastrado.")
        else:
            logger.debug("Projeto %s já notificado via e-mail.", projeto.id)

    if "telegram" in canais:
        if not storage.ja_notificado(projeto.id, "telegram"):
            notif = _notificador_telegram()
            if notif and notif.chat_ids:
                resultados = notif.enviar_para_todos(projeto)
                sucesso = all(resultados.values())
                for chat_id, ok in resultados.items():
                    storage.registrar_envio(projeto.id, "telegram", chat_id, ok)
                if sucesso:
                    storage.marcar_notificado(projeto.id, "telegram")
        else:
            logger.debug("Projeto %s já notificado via Telegram.", projeto.id)

def executar_ciclo(canais: list[str] = None):
    """
    Ciclo principal: busca projetos do IC, filtra novos, notifica.
    Chamado pelo scheduler e pelo CLI.
    """
    canais = canais or CANAIS
    logger.info("=== Iniciando ciclo de verificação (%s) ===", ", ".join(canais))

    try:
        projetos = buscar_projetos_ic()
    except Exception as exc:
        logger.error("Falha ao buscar projetos: %s", exc)
        return

    novos = [p for p in projetos if any(
        not storage.ja_notificado(p.id, canal) for canal in canais
    )]

    logger.info("Projetos ativos do IC: %d | Novos para notificar: %d", len(projetos), len(novos))

    for projeto in novos:
        logger.info("Processando: %s (id=%s)", projeto.titulo, projeto.id)
        processar_projeto(projeto, canais)

    logger.info("=== Ciclo concluído ===")


def cmd_listar():
    projetos = buscar_projetos_ic()
    print(f"\n{'='*60}")
    print(f"Projetos ativos do IC/UFRJ ({len(projetos)} encontrados)")
    print('='*60)
    for p in projetos:
        notif_status = " | ".join(
            f"{c}:{'✓' if storage.ja_notificado(p.id, c) else '✗'}"
            for c in CANAIS
        )
        print(f"\n[{p.id}] {p.titulo}")
        print(f"  Coordenador: {p.coordenador}")
        print(f"  Modalidade:  {p.modalidade}")
        if p.vagas:
            print(f"  Vagas:       {p.vagas}")
        if p.data_termino_inscricoes:
            print(f"  Inscrições:  até {p.data_termino_inscricoes}")
        print(f"  Notificado:  {notif_status}")


def cmd_assinantes(acao: str, canal: str, destino: str):
    if canal not in CANAIS:
        print(f"Canal inválido. Use: {', '.join(CANAIS)}")
        sys.exit(1)
    if acao == "add":
        storage.adicionar_assinante(canal, destino)
        print(f"✓ Assinante adicionado: [{canal}] {destino}")
    elif acao == "remove":
        storage.remover_assinante(canal, destino)
        print(f"✓ Assinante removido: [{canal}] {destino}")
    elif acao == "list":
        assinantes = storage.listar_assinantes(canal)
        print(f"Assinantes [{canal}]: {len(assinantes)}")
        for a in assinantes:
            print(f"  - {a}")
    else:
        print("Ação inválida. Use: add | remove | list")


def _projeto_demo() -> Projeto:
    """Projeto fictício para testar os canais quando não há ativos no portal."""
    return Projeto(
        id="demo",
        titulo="[TESTE] Curso de Extensão do IC/UFRJ",
        coordenador="Coordenação de Extensão",
        unidade="Instituto de Computação",
        modalidade="Curso",
        area="Computação",
        resumo="Mensagem de teste da automação de divulgação de extensões do IC/UFRJ.",
        descricao="Mensagem de teste da automação de divulgação de extensões do IC/UFRJ.",
        vagas=None,
        data_inicio=None,
        data_termino=None,
        data_inicio_inscricoes=None,
        data_termino_inscricoes=None,
        como_inscrever="Este é apenas um envio de teste — ignore.",
        link_inscricoes="https://portal.extensao.ufrj.br",
        contato="extensao@ic.ufrj.br",
        email_atendimento="extensao@ic.ufrj.br",
        telefone="",
        publico="Comunidade IC",
    )


def cmd_testar(canal: str = None):
    """Envia o primeiro projeto encontrado como teste (ou um projeto demo)."""
    canais = [canal] if canal else CANAIS
    projetos = buscar_projetos_ic()
    if not projetos:
        print("Nenhum projeto ativo no portal — usando projeto de demonstração.")
        projeto = _projeto_demo()
    else:
        projeto = projetos[0]
    print(f"Enviando projeto de teste: {projeto.titulo}")

    if "email" in canais:
        notif = _notificador_email()
        if notif:
            destinos = storage.listar_assinantes("email")
            if destinos:
                notif.enviar_para_lista(destinos, projeto)
            else:
                print("Nenhum assinante de e-mail. Adicione com: --assinantes add email <endereço>")

    if "telegram" in canais:
        notif = _notificador_telegram()
        if notif and notif.chat_ids:
            notif.enviar_para_todos(projeto)

    print("Teste concluído.")


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    storage.inicializar()

    parser = argparse.ArgumentParser(
        description="Automação de divulgação de extensões — IC/UFRJ"
    )
    parser.add_argument(
        "--canal", choices=CANAIS,
        help="Executar apenas para este canal",
    )
    parser.add_argument(
        "--listar", action="store_true",
        help="Listar projetos ativos sem enviar notificações",
    )
    parser.add_argument(
        "--assinantes", nargs=3,
        metavar=("AÇÃO", "CANAL", "DESTINO"),
        help="Gerenciar assinantes: add|remove|list <canal> <destino>",
    )
    parser.add_argument(
        "--testar", action="store_true",
        help="Enviar notificação de teste com o primeiro projeto encontrado",
    )

    args = parser.parse_args()

    if args.listar:
        cmd_listar()
    elif args.assinantes:
        acao, canal, destino = args.assinantes
        cmd_assinantes(acao, canal, destino)
    elif args.testar:
        cmd_testar(args.canal)
    else:
        canais = [args.canal] if args.canal else CANAIS
        executar_ciclo(canais)
