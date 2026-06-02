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
   COMITE_USER=comite
   COMITE_PASSWORD=...           (senha do painel do Comitê)
   ALLOWED_ORIGIN=https://cauaedm.github.io   (origem do site p/ CORS)
   ```

5. **Volume para o banco** (importante p/ não perder submissões/assinantes):
   - Aba do serviço → **Volumes → New Volume**
   - **Mount path:** `/app/data`
   - Assim o `fpn.db` (submissões, assinantes e dedup de notificações) sobrevive a reinícios/deploys.

6. **Deploy.** O serviço agora é um **web service sempre-ligado** (`railway.json` →
   `uvicorn webapp.app:app`). Ele serve:
   - `GET /api/extensoes` — lista consolidada (SIGA-IC + externas aprovadas), consumida pelo site.
   - `POST /api/submissoes` — recebe o formulário de submissão (RF05).
   - `/admin` — painel do Comitê (RF06-09), protegido por `COMITE_USER`/`COMITE_PASSWORD`.
   - `/healthz` — health check.

   O APScheduler roda **em background dentro do app** (ciclo SIGA seg/qui 9h BRT),
   substituindo o antigo cron job. Gere um **Domínio público** (Settings → Networking →
   Generate Domain) e use essa URL no site.

7. **Conectar o site à API.** No `config.yaml` do site, defina:
   ```yaml
   params:
     apiBase: "https://SEU-APP.up.railway.app"
   ```
   Faça commit/push — o GitHub Pages recompila e a página *Projetos de Extensão* passa a
   carregar a lista da API, e *Submeter Extensão Externa* passa a enviar para o backend.
   (Com `apiBase` vazio, o site usa a listagem estática de `data/extensoes.yaml` como fallback.)

> ⚠️ Diferente do cron anterior, o web service consome horas continuamente (precisa estar
> 24/7 para servir o formulário e o painel). No plano gratuito, fique de olho no uso.

---

## Checklist pós-deploy

- [ ] Site abre na URL do GitHub Pages
- [ ] Links/CSS do site carregam (baseURL correto)
- [ ] Railway buildou sem erro (logs do deploy)
- [ ] `python main.py --testar` envia e-mail + Telegram
- [ ] Volume montado em `/app/data` (banco persiste)
