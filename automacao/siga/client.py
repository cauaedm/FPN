"""
Cliente da API pública do Portal de Extensão da UFRJ.
Busca projetos ativos do Instituto de Computação e identifica novos.
"""

import json
import logging
import unicodedata
import urllib.request
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)

URL_API = "https://portal.extensao.ufrj.br/php/listaAcoes.php"

# Termo que identifica o IC nas unidades.
# Atenção: usar apenas "computa" casaria também com o Instituto Tércio Pacitti
# ("...e Pesquisas Computacionais" / NCE), que NÃO é o IC. Por isso o termo é
# específico. (_normalizar remove acentos: "Computação" -> "computacao".)
IC_KEYWORDS = ("instituto de computacao",)


@dataclass
class Projeto:
    id: str
    titulo: str
    coordenador: str
    unidade: str
    modalidade: str
    area: str
    resumo: str
    descricao: str
    vagas: Optional[str]
    data_inicio: Optional[str]
    data_termino: Optional[str]
    data_inicio_inscricoes: Optional[str]
    data_termino_inscricoes: Optional[str]
    como_inscrever: Optional[str]
    link_inscricoes: Optional[str]
    contato: Optional[str]
    email_atendimento: Optional[str]
    telefone: Optional[str]
    publico: Optional[str]
    tags: list[str] = field(default_factory=list)

    @property
    def descricao_curta(self) -> str:
        texto = self.resumo or self.descricao or ""
        return texto[:300].rstrip() + ("…" if len(texto) > 300 else "")

    @property
    def link_portal(self) -> str:
        return f"https://portal.extensao.ufrj.br"


def _normalizar(texto: str) -> str:
    texto = texto.strip().lower()
    texto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def _eh_ic(acao: dict) -> bool:
    unidade = _normalizar(acao.get("unidade") or "")
    return any(kw in unidade for kw in IC_KEYWORDS)


def _buscar_dados() -> list[dict]:
    """Faz a requisição à API do portal e devolve a lista bruta de ações."""
    logger.info("Buscando projetos na API: %s", URL_API)
    req = urllib.request.Request(URL_API, headers={"User-Agent": "FPN-IC-Bot/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.error("Erro ao buscar API: %s", exc)
        raise


def buscar_acao_por(link: str = None, email: str = None) -> Optional[dict]:
    """
    Procura uma ação no SIGA por link de inscrição ou e-mail (coordenador /
    atendimento / contato). Usada na conferência manual do Comitê (RF06).
    Retorna a ação bruta da API ou None.
    """
    link_norm = (link or "").strip().rstrip("/").lower()
    email_norm = _normalizar(email or "")
    if not link_norm and not email_norm:
        return None

    for acao in _buscar_dados():
        if link_norm:
            acao_link = (acao.get("link_inscricoes") or "").strip().rstrip("/").lower()
            if acao_link and acao_link == link_norm:
                return acao
        if email_norm:
            campos = (
                acao.get("email"),
                acao.get("email_atendimento"),
                acao.get("contato"),
                acao.get("coordenador"),
            )
            if any(email_norm in _normalizar(c or "") for c in campos):
                return acao
    return None


def buscar_projetos_ic(
    apenas_com_vagas: bool = False, incluir_encerrados: bool = False
) -> list[Projeto]:
    """
    Busca os projetos do IC na API do portal.extensao.ufrj.br.

    Por padrão filtra os com inscrição encerrada (usado pelo ciclo automático).
    Com `incluir_encerrados=True` retorna todas as ações do IC, independente do
    prazo — usado pelo site e pela listagem de divulgação do Comitê.
    """
    dados = _buscar_dados()

    logger.info("Total de projetos recebidos: %d", len(dados))

    projetos = []
    hoje = date.today().isoformat()

    for acao in dados:
        if not _eh_ic(acao):
            continue

        # Filtra projetos encerrados (data_termino_inscricoes no passado)
        termino = acao.get("data_termino_inscricoes") or acao.get("data_termino") or ""
        if not incluir_encerrados and termino and termino < hoje:
            continue

        # Obs.: a API do portal NÃO expõe número de vagas hoje — estas chaves
        # ficam ausentes e `vagas` resulta None (o template oculta a linha).
        # Mantido para o dia em que o portal passar a expor o dado.
        vagas = acao.get("vagas") or acao.get("num_vagas")
        if apenas_com_vagas and not vagas:
            continue

        proj = Projeto(
            id=str(acao.get("id_anuncio_acao") or acao.get("id") or ""),
            titulo=acao.get("titulo", "").strip(),
            coordenador=(acao.get("coordenador") or "").strip().title(),
            unidade=(acao.get("unidade") or "").strip(),
            modalidade=(acao.get("modalidade") or "Curso").strip(),
            area=(acao.get("area_principal") or "").strip(),
            resumo=(acao.get("resumo") or "").strip(),
            descricao=(acao.get("descricao") or "").strip(),
            vagas=str(vagas) if vagas else None,
            data_inicio=acao.get("data_inicio"),
            data_termino=acao.get("data_termino"),
            data_inicio_inscricoes=acao.get("data_inicio_inscricoes"),
            data_termino_inscricoes=acao.get("data_termino_inscricoes"),
            como_inscrever=(acao.get("como_inscrever") or "").strip(),
            link_inscricoes=(acao.get("link_inscricoes") or "").strip(),
            contato=(acao.get("contato") or "").strip(),
            email_atendimento=(acao.get("email_atendimento") or "").strip(),
            telefone=(acao.get("telefone_atendimento") or "").strip(),
            publico=(acao.get("publico") or "").strip(),
        )
        projetos.append(proj)

    logger.info("Projetos do IC encontrados: %d", len(projetos))
    return projetos
