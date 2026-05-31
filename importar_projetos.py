"""
Busca os projetos especificados na API do portal.extensao.ufrj.br
e gera entradas no formato do extensoes.yaml do site IC/UFRJ.
"""

import json
import urllib.request
import re
import unicodedata

URL_API = "https://portal.extensao.ufrj.br/php/listaAcoes.php"

TITULOS_DESEJADOS = [
    "Educação em TEA (Transtorno do Espectro Autista)",
    "Curso de Linux:  do Básico à Administração",
    "Olimpiadas Matemáticas Universitárias",
    "Curso de Programação em Python Usando e Construindo Jogos",
    "Introdução ao Linux: da Teoria à Prática",
    "Curso Avançado de Linux - Administração",
    "Semana da Computação 2026",
]

def normalizar(texto):
    """Remove acentos e caixa para comparação."""
    texto = texto.strip().lower()
    texto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")

def slug(titulo):
    """Gera chave YAML a partir do título."""
    s = unicodedata.normalize("NFD", titulo.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:50]

def extrair_ano(data_str):
    if data_str:
        return data_str[:4]
    return None

def wrap(texto, largura=72, indent="    "):
    """Quebra texto em linhas para o bloco YAML >."""
    palavras = texto.split()
    linhas = []
    linha_atual = ""
    for palavra in palavras:
        if len(linha_atual) + len(palavra) + 1 <= largura:
            linha_atual += (" " if linha_atual else "") + palavra
        else:
            if linha_atual:
                linhas.append(indent + linha_atual)
            linha_atual = palavra
    if linha_atual:
        linhas.append(indent + linha_atual)
    return "\n".join(linhas)

# ── Buscar dados da API ──────────────────────────────────────────────────────
print(f"Buscando: {URL_API}")
req = urllib.request.Request(URL_API, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=30) as resp:
    dados = json.loads(resp.read().decode("utf-8"))
print(f"Total recebido: {len(dados)} ações")

# ── Filtrar por título (sem duplicatas) ─────────────────────────────────────
titulos_norm = [normalizar(t) for t in TITULOS_DESEJADOS]
vistos = set()
encontrados = []

for acao in dados:
    titulo_api = acao.get("titulo", "")
    tn = normalizar(titulo_api)
    if tn in titulos_norm and tn not in vistos:
        vistos.add(tn)
        encontrados.append(acao)

print(f"Projetos encontrados (sem duplicatas): {len(encontrados)}")
for a in encontrados:
    print(f"  - {a['titulo']}")

nao_encontrados = [t for t in TITULOS_DESEJADOS if normalizar(t) not in vistos]
if nao_encontrados:
    print("\nNAO ENCONTRADOS:")
    for t in nao_encontrados:
        print(f"  - {t}")

# ── Gerar YAML ───────────────────────────────────────────────────────────────
linhas = []
for acao in encontrados:
    chave    = slug(acao["titulo"])
    titulo   = acao.get("titulo", "").strip()
    coord    = acao.get("coordenador", "").strip().title()
    area     = acao.get("area_principal", "").strip()
    modal    = acao.get("modalidade", "Curso").strip()
    ch       = acao.get("carga_horaria", "").strip()
    descricao = (acao.get("descricao") or acao.get("resumo") or "").strip()
    contato  = (acao.get("email_atendimento") or acao.get("contato") or "").strip()
    link     = (acao.get("link_inscricoes") or "").strip()
    ano_ini  = extrair_ano(acao.get("data_inicio"))
    ano_fim  = extrair_ano(acao.get("data_termino"))

    # Bloco de texto longo
    descricao_yaml = wrap(descricao)

    bloco = f"{chave}:\n"
    bloco += f'  titulo: "{titulo}"\n'
    bloco += f'  coordenador: "{coord}"\n'
    if area:
        bloco += f'  area: "{area}"\n'
    bloco += f'  modalidade: "{modal}"\n'
    if ch:
        bloco += f'  carga_horaria: {ch}\n'
    bloco += f'  descricao: >\n{descricao_yaml}\n'
    # vagas e bolsa: não vêm da API, deixar para preenchimento manual
    bloco += f'  vagas: ~  # preencher manualmente\n'
    bloco += f'  bolsa: ~  # preencher manualmente\n'
    bloco += f'  processo_seletivo: ~  # preencher manualmente\n'
    bloco += f'  perfil: ~  # preencher manualmente\n'
    if contato:
        bloco += f'  contato: "{contato}"\n'
    if link:
        bloco += f'  link_inscricao: "{link}"\n'
    if ano_ini:
        bloco += f'  ano_inicio: {ano_ini}\n'
    if ano_fim and ano_fim != ano_ini:
        bloco += f'  ano_fim: {ano_fim}\n'

    linhas.append(bloco)

yaml_novo = "\n".join(linhas)
print("\n" + "="*60)
print(yaml_novo)
print("="*60)

# Salvar resultado separado para revisão
with open("novos_projetos_api.yaml", "w", encoding="utf-8") as f:
    f.write("# Projetos importados da API portal.extensao.ufrj.br\n")
    f.write("# ATENÇÃO: preencher os campos marcados com ~ antes de publicar\n\n")
    f.write(yaml_novo)
print("\nSalvo em: novos_projetos_api.yaml")
