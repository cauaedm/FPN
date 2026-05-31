"""
Notificador via Telegram Bot API.

Setup:
  1. Crie um bot com @BotFather e obtenha o TELEGRAM_BOT_TOKEN.
  2. Adicione o bot ao canal/grupo do IC e obtenha o TELEGRAM_CHAT_ID.
     Para canais públicos use @nome_do_canal.
     Para grupos, use o ID numérico (ex: -1001234567890).
  3. Configure as variáveis no .env.

Uso multicanal: defina TELEGRAM_CHAT_IDS (separados por vírgula) para enviar
para múltiplos canais/grupos/usuários simultaneamente.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from siga.client import Projeto

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "telegram.txt"


class SimpleTemplate:
    def __init__(self, text: str):
        self._text = text

    def render(self, **kwargs) -> str:
        result = self._text
        for key, value in kwargs.items():
            result = result.replace("{{ " + key + " }}", str(value) if value else "")
        lines = []
        skip = False
        for line in result.splitlines():
            stripped = line.strip()
            if stripped.startswith("{% if "):
                cond_var = stripped[6:].rstrip(" %}").strip()
                skip = not kwargs.get(cond_var)
                continue
            if stripped == "{% endif %}":
                skip = False
                continue
            if not skip:
                lines.append(line)
        # Remove linhas em branco consecutivas
        cleaned = []
        prev_blank = False
        for line in lines:
            is_blank = not line.strip()
            if is_blank and prev_blank:
                continue
            cleaned.append(line)
            prev_blank = is_blank
        return "\n".join(cleaned).strip()


def _render(projeto: Projeto) -> str:
    template_text = TEMPLATE_PATH.read_text(encoding="utf-8")
    t = SimpleTemplate(template_text)
    return t.render(
        titulo=projeto.titulo,
        modalidade=projeto.modalidade,
        coordenador=projeto.coordenador,
        area=projeto.area,
        vagas=projeto.vagas or "",
        descricao_curta=projeto.descricao_curta,
        data_termino_inscricoes=projeto.data_termino_inscricoes or "",
        como_inscrever=projeto.como_inscrever or "",
        email_atendimento=projeto.email_atendimento or "",
        link_inscricoes=projeto.link_inscricoes or "",
    )


class TelegramNotificador:
    """
    Envia mensagens para canais/grupos/usuários via Telegram Bot API.

    Configuração (.env):
      TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
      TELEGRAM_CHAT_IDS=-1001234567890,@ic_ufrj_extensoes
    """

    def __init__(self, token: str, chat_ids: list[str]):
        self.token = token
        self.chat_ids = chat_ids

    def _request(self, method: str, payload: dict) -> dict:
        url = TELEGRAM_API.format(token=self.token, method=method)
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            logger.error("Telegram HTTP %s: %s", exc.code, body)
            raise
        except Exception as exc:
            logger.error("Telegram request error: %s", exc)
            raise

    def enviar(self, chat_id: str, projeto: Projeto) -> bool:
        """Envia mensagem formatada em Markdown V2 para um chat_id."""
        texto = _render(projeto)
        try:
            resp = self._request("sendMessage", {
                "chat_id": chat_id,
                "text": texto,
                "parse_mode": "Markdown",
                "disable_web_page_preview": False,
            })
            if resp.get("ok"):
                logger.info("Telegram enviado para %s — %s", chat_id, projeto.titulo)
                return True
            else:
                logger.error("Telegram erro: %s", resp)
                return False
        except Exception:
            return False

    def enviar_para_todos(self, projeto: Projeto) -> dict[str, bool]:
        """Envia para todos os chat_ids configurados."""
        return {cid: self.enviar(cid, projeto) for cid in self.chat_ids}

    def testar_conexao(self) -> bool:
        """Verifica se o token é válido."""
        try:
            resp = self._request("getMe", {})
            nome = resp.get("result", {}).get("username")
            logger.info("Telegram bot conectado: @%s", nome)
            return True
        except Exception:
            return False

    @classmethod
    def from_env(cls) -> "TelegramNotificador":
        import os
        token = os.environ["TELEGRAM_BOT_TOKEN"]
        ids_raw = os.environ.get("TELEGRAM_CHAT_IDS", "")
        chat_ids = [c.strip() for c in ids_raw.split(",") if c.strip()]
        return cls(token=token, chat_ids=chat_ids)
