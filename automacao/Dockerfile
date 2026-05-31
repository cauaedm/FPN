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

# Worker sempre-ligado: o APScheduler dispara nos horários configurados.
# O banco fica em /app/data — monte um Volume do Railway nesse caminho
# para que os envios já feitos persistam entre reinícios/deploys.
CMD ["python", "scheduler.py"]
