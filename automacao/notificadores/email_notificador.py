"""
Notificador por e-mail institucional (SMTP).
Suporta SMTP com STARTTLS (porta 587) e SSL (porta 465).
"""

import logging
import smtplib
import ssl
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
        texto = (
            f"Nova oportunidade de extensão no IC/UFRJ\n\n"
            f"{projeto.titulo}\n\n"
            f"{projeto.descricao_curta}\n\n"
            f"Coordenador: {projeto.coordenador}\n"
            + (f"Link: {projeto.link_inscricoes}\n" if projeto.link_inscricoes else "")
            + "\nic.ufrj.br"
        )
        msg.attach(MIMEText(texto, "plain", "utf-8"))

        # Versão HTML
        html = _render_template(projeto)
        msg.attach(MIMEText(html, "html", "utf-8"))

        return msg

    def enviar(self, destino: str, projeto: Projeto) -> bool:
        """Envia e-mail para um único destinatário. Retorna True se bem-sucedido."""
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
            return True

        except smtplib.SMTPException as exc:
            logger.error("Erro ao enviar e-mail para %s: %s", destino, exc)
            return False

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
        except smtplib.SMTPException as exc:
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
    def from_env(cls) -> "EmailNotificador":
        """Cria instância a partir de variáveis de ambiente."""
        import os
        return cls(
            host=os.environ["EMAIL_HOST"],
            port=int(os.environ.get("EMAIL_PORT", "587")),
            user=os.environ["EMAIL_USER"],
            password=os.environ["EMAIL_PASSWORD"],
            from_addr=os.environ.get("EMAIL_FROM", os.environ["EMAIL_USER"]),
            use_tls=os.environ.get("EMAIL_USE_TLS", "true").lower() == "true",
            use_ssl=os.environ.get("EMAIL_USE_SSL", "false").lower() == "true",
        )
