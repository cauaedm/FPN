# Automação de Extensões — IC/UFRJ

Serviço de notificação automática de novos projetos de extensão do Instituto de Computação da UFRJ. Monitora a API pública do portal de extensões e dispara notificações por **e-mail**, **Telegram** e **WhatsApp** quando novos projetos são detectados.

## Estrutura

```
automacao/
├── main.py                        # CLI e ciclo principal
├── scheduler.py                   # Agendador (APScheduler)
├── requirements.txt
├── .env.example                   # Variáveis de ambiente (copie para .env)
├── siga/
│   └── client.py                  # Busca projetos na API do portal.extensao.ufrj.br
├── notificadores/
│   ├── email_notificador.py       # Disparo via SMTP
│   ├── telegram_notificador.py    # Disparo via Telegram Bot API
│   └── whatsapp_notificador.py    # Disparo via Evolution API ou Twilio
├── db/
│   └── storage.py                 # SQLite — rastreia envios e assinantes
└── templates/
    ├── email.html                 # Template HTML do e-mail
    ├── telegram.txt               # Template Markdown do Telegram
    └── whatsapp.txt               # Template texto do WhatsApp
```

## Instalação

```bash
cd automacao
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edite o .env com suas credenciais
```

## Configuração

### 1. E-mail
Configure `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USER`, `EMAIL_PASSWORD` no `.env`.

Depois, adicione os destinatários:
```bash
python main.py --assinantes add email aluno1@dcc.ufrj.br
python main.py --assinantes add email lista-alunos@ic.ufrj.br
```

### 2. Telegram
1. Crie um bot com [@BotFather](https://t.me/BotFather) e copie o token.
2. Crie um canal/grupo, adicione o bot como administrador.
3. Obtenha o `chat_id` do canal (use `/getUpdates` na API do Telegram).
4. Configure `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_IDS` no `.env`.

### 3. WhatsApp (Evolution API — recomendado)

A [Evolution API](https://doc.evolution-api.com) é uma solução open-source que permite conectar um número WhatsApp comum (sem custo de API oficial):

```bash
# Instale via Docker
docker run -d --name evolution-api \
  -p 8080:8080 \
  -e AUTHENTICATION_API_KEY=sua_chave \
  atendai/evolution-api:latest
```

Após iniciar, acesse o painel, crie uma instância e escaneie o QR Code com o WhatsApp do IC. Configure `EVOLUTION_API_URL`, `EVOLUTION_API_KEY` e `EVOLUTION_INSTANCE` no `.env`.

Alternativa: use o **Twilio WhatsApp Sandbox** para testes (configure `WHATSAPP_BACKEND=twilio`).

## Uso

```bash
# Executar ciclo completo (todos os canais)
python main.py

# Apenas um canal
python main.py --canal email
python main.py --canal telegram
python main.py --canal whatsapp

# Listar projetos ativos (sem enviar)
python main.py --listar

# Enviar notificação de teste
python main.py --testar

# Gerenciar assinantes de e-mail
python main.py --assinantes add email fulano@ic.ufrj.br
python main.py --assinantes list email fulano@ic.ufrj.br
python main.py --assinantes remove email fulano@ic.ufrj.br
```

## Agendamento automático

```bash
# Roda em foreground (segunda e quinta às 9h — configurável no .env)
python scheduler.py

# Executa uma vez e sai (ideal para cron do sistema)
python scheduler.py --once
```

### Via cron do sistema (alternativa)

```cron
# Toda segunda e quinta às 9h
0 9 * * 1,4 /caminho/para/automacao/.venv/bin/python /caminho/para/automacao/scheduler.py --once
```

### Via systemd (servidor Linux)

Crie `/etc/systemd/system/fpn-automacao.service`:

```ini
[Unit]
Description=Automação Extensões IC/UFRJ
After=network.target

[Service]
WorkingDirectory=/caminho/para/automacao
ExecStart=/caminho/para/automacao/.venv/bin/python scheduler.py
EnvironmentFile=/caminho/para/automacao/.env
Restart=always
RestartSec=60

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable fpn-automacao
sudo systemctl start fpn-automacao
```

## Como funciona

1. O scheduler chama `executar_ciclo()` no horário configurado.
2. O cliente busca projetos do IC na API `portal.extensao.ufrj.br/php/listaAcoes.php`.
3. Para cada projeto, verifica no SQLite (`data/fpn.db`) se já foi notificado.
4. Projetos novos são enviados para todos os assinantes/canais configurados.
5. Após envio bem-sucedido, o projeto é marcado no banco para evitar reenvio.

## Banco de dados

O SQLite é criado automaticamente em `data/fpn.db` com três tabelas:
- `projetos_notificados` — controla o que já foi enviado por canal
- `assinantes` — lista de destinatários por canal
- `log_envios` — histórico de todos os envios com status de sucesso/erro
