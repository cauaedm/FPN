# Imagem da automação de divulgação de extensões IC/UFRJ (deploy no Railway).
FROM python:3.13-slim

# Fuso horário para o scheduler (seg/qui 9h America/Sao_Paulo)
ENV TZ=America/Sao_Paulo \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1

WORKDIR /app

# Instala dependências primeiro (melhor cache de build)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o restante do código
COPY . .

# Web service sempre-ligado: serve o formulário (RF05), a API consolidada
# (RF11/12) e o painel do Comitê (RF06-09); o APScheduler roda em background
# dentro do app (ciclo SIGA seg/qui 9h). O banco fica em /app/data — monte um
# Volume do Railway nesse caminho para persistir submissões/assinantes/dedup.
EXPOSE 8080
CMD ["sh", "-c", "uvicorn webapp.app:app --host 0.0.0.0 --port ${PORT:-8080}"]
