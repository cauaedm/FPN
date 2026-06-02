"""
Notificador por e-mail.

Dois backends, escolhidos por EMAIL_BACKEND:
  - "smtp"  (padrão): SMTP com STARTTLS (587) ou SSL (465).
  - "resend": API HTTP da Resend (porta 443) — usar quando o host bloqueia SMTP
              de saída (ex.: Railway no plano gratuito).
"""

import json
import logging
import os
import smtplib
import ssl
import urllib.error
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from string import Template

from siga.client import Projeto

logger = logging.getLogger(__name__)

TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "email.html"


class SimpleTemplate:
    """Template mínimo sem dependências externas (substitui {{ var }})."""

    def __init__(self, text: str):
        self._text = text

    def render(self, **kwargs) -> str:
        result = self._text
        for key, value in kwargs.items():
            result = result.replace("{{ " + key + " }}", str(value) if value else "")
            result = result.replace("{{" + key + "}}", str(value) if value else "")
        # Remove linhas de blocos condicionais não resolvidos ({% if ... %})
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
        return "\n".join(lines)


def _texto_plano(projeto: Projeto) -> str:
    return (
        f"Nova oportunidade de extensão no IC/UFRJ\n\n"
        f"{projeto.titulo}\n\n"
        f"{projeto.descricao_curta}\n\n"
        f"Coordenador: {projeto.coordenador}\n"
        + (f"Link: {projeto.link_inscricoes}\n" if projeto.link_inscricoes else "")
        + "\nic.ufrj.br"
    )


def _render_template(projeto: Projeto, link_descadastro: str = "#") -> str:
    template_text = TEMPLATE_PATH.read_text(encoding="utf-8")
    t = SimpleTemplate(template_text)
    return t.render(
        titulo=projeto.titulo,
        modalidade=projeto.modalidade,
        coordenador=projeto.coordenador,
        area=projeto.area,
        vagas=projeto.vagas or "",
        descricao_curta=projeto.descricao_curta,
        data_inicio_inscricoes=projeto.data_inicio_inscricoes or "",
        data_termino_inscricoes=projeto.data_termino_inscricoes or "",
        como_inscrever=projeto.como_inscrever or "",
        contato=projeto.contato or "",
        email_atendimento=projeto.email_atendimento or "",
        telefone=projeto.telefone or "",
        link_inscricoes=projeto.link_inscricoes or "",
        link_descadastro=link_descadastro,
    )


class EmailNotificador:
    """
    Envia e-mails HTML via SMTP.

    Configuração via variáveis de ambiente (ver .env.example):
      EMAIL_HOST, EMAIL_PORT, EMAIL_USER, EMAIL_PASSWORD,
      EMAIL_FROM, EMAIL_USE_TLS, EMAIL_USE_SSL
    """

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        from_addr: str,
        use_tls: bool = True,
        use_ssl: bool = False,
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.from_addr = from_addr
        self.use_tls = use_tls
        self.use_ssl = use_ssl

    def _criar_mensagem(
        self, destino: str, projeto: Projeto
    ) -> MIMEMultipart:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[IC/UFRJ Extensão] {projeto.titulo}"
        msg["From"] = self.from_addr
        msg["To"] = destino

        # Versão texto plano (fallback)
        msg.attach(MIMEText(_texto_plano(projeto), "plain", "utf-8"))

        # Versão HTML
        html = _render_template(projeto)
        msg.attach(MIMEText(html, "html", "utf-8"))

        return msg

    def enviar_detalhado(self, destino: str, projeto: Projeto) -> tuple[bool, str]:
        """Envia e retorna (sucesso, mensagem_de_erro). Erro vazio em caso de sucesso."""
        msg = self._criar_mensagem(destino, projeto)
        try:
            if self.use_ssl:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(self.host, self.port, context=context) as smtp:
                    smtp.login(self.user, self.password)
                    smtp.sendmail(self.from_addr, destino, msg.as_string())
            else:
                with smtplib.SMTP(self.host, self.port) as smtp:
                    if self.use_tls:
                        smtp.starttls(context=ssl.create_default_context())
                    smtp.login(self.user, self.password)
                    smtp.sendmail(self.from_addr, destino, msg.as_string())

            logger.info("E-mail enviado para %s — %s", destino, projeto.titulo)
            return True, ""

        except Exception as exc:  # SMTP, conexão, DNS, TLS — não deixa quebrar o request
            logger.error("Erro ao enviar e-mail para %s: %s", destino, exc)
            return False, str(exc)

    def enviar(self, destino: str, projeto: Projeto) -> bool:
        """Envia e-mail para um único destinatário. Retorna True se bem-sucedido."""
        return self.enviar_detalhado(destino, projeto)[0]

    def _enviar_raw(self, destino: str, msg: MIMEMultipart) -> bool:
        try:
            if self.use_ssl:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(self.host, self.port, context=context) as smtp:
                    smtp.login(self.user, self.password)
                    smtp.sendmail(self.from_addr, destino, msg.as_string())
            else:
                with smtplib.SMTP(self.host, self.port) as smtp:
                    if self.use_tls:
                        smtp.starttls(context=ssl.create_default_context())
                    smtp.login(self.user, self.password)
                    smtp.sendmail(self.from_addr, destino, msg.as_string())
            return True
        except Exception as exc:
            logger.error("Erro ao enviar e-mail para %s: %s", destino, exc)
            return False

    def enviar_texto(self, destino: str, assunto: str, corpo: str) -> bool:
        """Envia um e-mail de texto livre (ex.: aviso de rejeição — RF09)."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = assunto
        msg["From"] = self.from_addr
        msg["To"] = destino
        msg.attach(MIMEText(corpo, "plain", "utf-8"))
        ok = self._enviar_raw(destino, msg)
        if ok:
            logger.info("E-mail (texto) enviado para %s — %s", destino, assunto)
        return ok

    def enviar_para_lista(
        self, destinatarios: list[str], projeto: Projeto
    ) -> dict[str, bool]:
        """Envia para múltiplos destinatários. Retorna dict destino→sucesso."""
        resultados = {}
        for dest in destinatarios:
            resultados[dest] = self.enviar(dest, projeto)
        return resultados

    @classmethod
    def from_env(cls):
        """Cria o notificador conforme EMAIL_BACKEND (smtp padrão | resend)."""
        if os.environ.get("EMAIL_BACKEND", "smtp").lower() == "resend":
            return ResendEmailNotificador.from_env()
        return cls(
            host=os.environ["EMAIL_HOST"],
            port=int(os.environ.get("EMAIL_PORT", "587")),
            user=os.environ["EMAIL_USER"],
            password=os.environ["EMAIL_PASSWORD"],
            from_addr=os.environ.get("EMAIL_FROM", os.environ["EMAIL_USER"]),
            use_tls=os.environ.get("EMAIL_USE_TLS", "true").lower() == "true",
            use_ssl=os.environ.get("EMAIL_USE_SSL", "false").lower() == "true",
        )


class ResendEmailNotificador:
    """
    Envia e-mail pela API HTTP da Resend (https://resend.com) — porta 443.
    Mesma interface do EmailNotificador (enviar/enviar_detalhado/enviar_para_lista/
    enviar_texto), para funcionar onde o SMTP de saída é bloqueado (ex.: Railway).

    Env: RESEND_API_KEY (obrigatório), EMAIL_FROM (remetente; no plano grátis use
    'onboarding@resend.dev' ou um domínio verificado).
    """

    API_URL = "https://api.resend.com/emails"

    def __init__(self, api_key: str, from_addr: str):
        self.api_key = api_key
        self.from_addr = from_addr

    def _post(self, payload: dict) -> tuple[bool, str]:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.API_URL,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp.read()
            return True, ""
        except urllib.error.HTTPError as exc:
            corpo = exc.read().decode("utf-8", "replace")
            return False, f"HTTP {exc.code}: {corpo[:200]}"
        except Exception as exc:
            return False, str(exc)

    def enviar_detalhado(self, destino: str, projeto: Projeto) -> tuple[bool, str]:
        ok, erro = self._post({
            "from": self.from_addr,
            "to": [destino],
            "subject": f"[IC/UFRJ Extensão] {projeto.titulo}",
            "html": _render_template(projeto),
            "text": _texto_plano(projeto),
        })
        if ok:
            logger.info("E-mail (Resend) enviado para %s — %s", destino, projeto.titulo)
        else:
            logger.error("Erro Resend ao enviar para %s: %s", destino, erro)
        return ok, erro

    def enviar(self, destino: str, projeto: Projeto) -> bool:
        return self.enviar_detalhado(destino, projeto)[0]

    def enviar_para_lista(self, destinatarios: list[str], projeto: Projeto) -> dict[str, bool]:
        return {dest: self.enviar(dest, projeto) for dest in destinatarios}

    def enviar_texto(self, destino: str, assunto: str, corpo: str) -> bool:
        ok, erro = self._post({
            "from": self.from_addr,
            "to": [destino],
            "subject": assunto,
            "text": corpo,
        })
        if ok:
            logger.info("E-mail (Resend, texto) enviado para %s — %s", destino, assunto)
        else:
            logger.error("Erro Resend (texto) ao enviar para %s: %s", destino, erro)
        return ok

    @classmethod
    def from_env(cls) -> "ResendEmailNotificador":
        return cls(
            api_key=os.environ["RESEND_API_KEY"],
            from_addr=os.environ.get("EMAIL_FROM", "onboarding@resend.dev"),
        )
