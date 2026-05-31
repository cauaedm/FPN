"""
Notificador via WhatsApp.

Suporta dois backends (configure via WHATSAPP_BACKEND):

1. evolution  — Evolution API (open-source, self-hosted)
   https://doc.evolution-api.com
   Variáveis: EVOLUTION_API_URL, EVOLUTION_API_KEY, EVOLUTION_INSTANCE

2. twilio     — Twilio WhatsApp Sandbox / número aprovado
   https://www.twilio.com/whatsapp
   Variáveis: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER

Para produção com WhatsApp oficial (Meta Business API), use o backend Evolution
com uma instância conectada a uma linha aprovada pela Meta, ou configure
WHATSAPP_BACKEND=meta e forneça META_TOKEN e META_PHONE_NUMBER_ID.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from base64 import b64encode
from pathlib import Path

from siga.client import Projeto

logger = logging.getLogger(__name__)

TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "whatsapp.txt"


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
        vagas=projeto.vagas or "",
        descricao_curta=projeto.descricao_curta,
        data_termino_inscricoes=projeto.data_termino_inscricoes or "",
        como_inscrever=projeto.como_inscrever or "",
        link_inscricoes=projeto.link_inscricoes or "",
    )


# ── Backend: Evolution API ───────────────────────────────────────────────────

class EvolutionBackend:
    """
    Envia mensagens via Evolution API (self-hosted).
    Número destino no formato: 5521999999999 (DDI+DDD+número, sem +).
    """

    def __init__(self, url: str, api_key: str, instance: str):
        self.base_url = url.rstrip("/")
        self.api_key = api_key
        self.instance = instance

    def enviar(self, numero: str, texto: str) -> bool:
        endpoint = f"{self.base_url}/message/sendText/{self.instance}"
        payload = {
            "number": numero,
            "text": texto,
            "delay": 1200,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=data,
            headers={
                "Content-Type": "application/json",
                "apikey": self.api_key,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                logger.info("Evolution: enviado para %s — status: %s", numero, result.get("status"))
                return True
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            logger.error("Evolution HTTP %s para %s: %s", exc.code, numero, body)
            return False
        except Exception as exc:
            logger.error("Evolution erro para %s: %s", numero, exc)
            return False

    @classmethod
    def from_env(cls) -> "EvolutionBackend":
        import os
        return cls(
            url=os.environ["EVOLUTION_API_URL"],
            api_key=os.environ["EVOLUTION_API_KEY"],
            instance=os.environ["EVOLUTION_INSTANCE"],
        )


# ── Backend: Twilio ──────────────────────────────────────────────────────────

class TwilioBackend:
    """
    Envia mensagens via Twilio WhatsApp API.
    Número destino no formato: +5521999999999.
    """

    TWILIO_URL = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"

    def __init__(self, account_sid: str, auth_token: str, from_number: str):
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = f"whatsapp:{from_number}"
        self._auth = b64encode(f"{account_sid}:{auth_token}".encode()).decode()

    def enviar(self, numero: str, texto: str) -> bool:
        url = self.TWILIO_URL.format(sid=self.account_sid)
        to = f"whatsapp:{numero}" if not numero.startswith("whatsapp:") else numero
        payload = urllib.parse.urlencode({
            "From": self.from_number,
            "To": to,
            "Body": texto,
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Authorization": f"Basic {self._auth}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                logger.info("Twilio: enviado para %s — SID: %s", numero, result.get("sid"))
                return True
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            logger.error("Twilio HTTP %s para %s: %s", exc.code, numero, body)
            return False
        except Exception as exc:
            logger.error("Twilio erro para %s: %s", numero, exc)
            return False

    @classmethod
    def from_env(cls) -> "TwilioBackend":
        import os
        return cls(
            account_sid=os.environ["TWILIO_ACCOUNT_SID"],
            auth_token=os.environ["TWILIO_AUTH_TOKEN"],
            from_number=os.environ["TWILIO_FROM_NUMBER"],
        )


# ── Notificador unificado ────────────────────────────────────────────────────

class WhatsAppNotificador:
    """
    Interface única para envio via WhatsApp.
    Seleciona o backend conforme WHATSAPP_BACKEND.
    """

    def __init__(self, backend):
        self._backend = backend
        self.numeros: list[str] = []

    def enviar(self, numero: str, projeto: Projeto) -> bool:
        texto = _render(projeto)
        return self._backend.enviar(numero, texto)

    def enviar_para_todos(self, projeto: Projeto) -> dict[str, bool]:
        return {num: self.enviar(num, projeto) for num in self.numeros}

    @classmethod
    def from_env(cls) -> "WhatsAppNotificador":
        import os
        backend_name = os.environ.get("WHATSAPP_BACKEND", "evolution").lower()

        if backend_name == "twilio":
            backend = TwilioBackend.from_env()
        else:  # evolution (padrão)
            backend = EvolutionBackend.from_env()

        notificador = cls(backend)
        numeros_raw = os.environ.get("WHATSAPP_NUMEROS", "")
        notificador.numeros = [n.strip() for n in numeros_raw.split(",") if n.strip()]
        return notificador
