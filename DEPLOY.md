# Deploy do projeto (Demo do TCC)

Dois alvos, ambos no plano gratuito:

| Componente | Onde | Como |
|---|---|---|
| **Site Hugo** (`/`) | GitHub Pages | Workflow `.github/workflows/gh-pages.yml` |
| **Automação** (`automacao/`) | Railway | Worker via `automacao/Dockerfile` |

> ⚠️ O `.env` e o banco (`data/*.db`) **nunca** vão para o Git — já estão no `.gitignore`.
> No Railway, as credenciais são configuradas como variáveis de ambiente (passo B4).

---

## A) Site → GitHub Pages

1. **Criar o repositório no GitHub** (ex.: `fpn-extensoes`), pode ser público.

2. **Subir o código** (a partir da raiz do projeto):
   ```bash
   git add -A
   git commit -m "Deploy inicial: site Hugo + automação"
   git branch -M main
   git remote add origin https://github.com/SEU_USUARIO/SEU_REPO.git
   git push -u origin main
   ```

3. **Ativar o Pages**: no GitHub → **Settings → Pages → Build and deployment → Source = GitHub Actions**.

4. Pronto. A cada `push` na `main`, o workflow compila o Hugo e publica.
   A URL será algo como `https://SEU_USUARIO.github.io/SEU_REPO/`
   (o `baseURL` é ajustado automaticamente pelo workflow — não precisa editar o `config.yaml`).

> O workflow antigo `deploy.yml` (rsync para servidor) continua existindo e é
> independente; ele só roda se os *secrets* `SERVER_*` estiverem configurados.

---

## B) Automação → Railway

1. **Criar conta** em [railway.app](https://railway.app) (login com GitHub).

2. **New Project → Deploy from GitHub repo** → selecione o repositório.

3. **Configurar o serviço** (Settings do serviço):
   - **Root Directory:** `automacao`
     (faz o Railway usar o `Dockerfile` e o `railway.json` de dentro da pasta)
   - O build usa o `Dockerfile` automaticamente (definido no `railway.json`).

4. **Variáveis de ambiente** (aba *Variables*) — copie os valores do seu `.env` local:
   ```
   EMAIL_HOST=smtp.gmail.com
   EMAIL_PORT=587
   EMAIL_USER=...
   EMAIL_PASSWORD=...            (senha de app do Gmail, 16 caracteres)
   EMAIL_FROM=...
   EMAIL_USE_TLS=true
   EMAIL_USE_SSL=false
   TELEGRAM_BOT_TOKEN=...
   TELEGRAM_CHAT_IDS=...
   CRON_DAY_OF_WEEK=mon,thu
   CRON_HOUR=9
   CRON_MINUTE=0
   ```

5. **Volume para o banco** (importante p/ não reenviar notificações):
   - Aba do serviço → **Volumes → New Volume**
   - **Mount path:** `/app/data`
   - Assim o `fpn.db` (lista do que já foi notificado) sobrevive a reinícios/deploys.

6. **Deploy.** O worker fica ligado e o APScheduler dispara seg/qui às 9h (BRT).
   - Para testar na hora, abra o serviço → **... → Shell/Run** e rode:
     `python main.py --testar`
   - Cadastre destinatários de e-mail via shell:
     `python main.py --assinantes add email fulano@exemplo.com`

> 💡 **Economia (opcional):** como o disparo é só 2x/semana, dá para trocar o worker
> sempre-ligado por um **Cron Job do Railway**: start command `python scheduler.py --once`
> e *Cron Schedule* `0 12 * * 1,4` (12h UTC = 9h BRT). Mantenha o Volume mesmo assim.

---

## Checklist pós-deploy

- [ ] Site abre na URL do GitHub Pages
- [ ] Links/CSS do site carregam (baseURL correto)
- [ ] Railway buildou sem erro (logs do deploy)
- [ ] `python main.py --testar` envia e-mail + Telegram
- [ ] Volume montado em `/app/data` (banco persiste)
