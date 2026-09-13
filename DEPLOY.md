# Deploying CEGE 3102 AITA to Fly.io

This app currently runs via `docker compose` on a UMN GPU host. This guide moves it
to **[Fly.io](https://fly.io)** at `https://cege-3102-aita.fly.dev`.

## What changes vs. the host deployment

| Concern | GPU host (docker-compose) | Fly.io |
|---|---|---|
| LLM auth | Vertex AI via your personal `gcloud` ADC (mounted) | **Vertex AI** via a service-account key (`GCP_SA_KEY` secret) |
| Data (`aita.db`) | host bind-mount `/data2/aita_3102` | **Fly volume** `aita_data` at `/app/data` |
| Config | `.env` + compose mounts | **Fly secrets** |
| URL / TLS | `http://…:30005` | `https://cege-3102-aita.fly.dev` (HTTPS, free) |
| Scale | single container | **exactly one** always-on machine |

> **Why one machine?** SQLite and the admin `config_overrides.json` live on a single
> Fly volume (single-attach, no multi-writer). Never scale this app past 1 machine.

---

## 1. Prerequisites

```bash
# Install flyctl and sign in
curl -L https://fly.io/install.sh | sh      # or: brew install flyctl
fly auth login
```

**Create a Vertex AI service-account key in Google Cloud Console** (the app uses OAuth via
a service account — no API key):

1. Console → project **`aita-489419`** → **IAM & Admin → Service Accounts**.
2. **Create service account** `aita-vertex`; grant role **Vertex AI User**
   (`roles/aiplatform.user`).
3. Open it → **Keys → Add key → Create new key → JSON**. Save to `/tmp/adc.json`
   (a live credential — keep it out of the repo; it is never committed or baked in).
4. Ensure the **Vertex AI API** (`aiplatform.googleapis.com`) is enabled for the project.

---

## 2. Verify the key + models (Vertex)

Confirm the service-account key reaches Vertex and both models before deploying:

```bash
GOOGLE_APPLICATION_CREDENTIALS=/tmp/adc.json python3 - <<'PY'
from google import genai
from google.genai import types
c = genai.Client(vertexai=True, project="aita-489419", location="global")
print("chat:", c.models.generate_content(model="gemini-3.1-flash-lite",
      contents="Reply OK", config=types.GenerateContentConfig(max_output_tokens=10)).text.strip())
print("embed dims:", len(c.models.embed_content(model="gemini-embedding-001",
      contents=["confidence interval"],
      config=types.EmbedContentConfig(output_dimensionality=3072)).embeddings[0].values))
PY
```

Expect `chat: OK` and `embed dims: 3072`. `gemini-3.1-flash-lite` is served on Vertex's
**global** endpoint (hence `GOOGLE_CLOUD_LOCATION=global`); `gemini-embedding-001` @ 3072
matches the pre-built FAISS index, so no re-ingestion is needed.

(`scripts/check_gemini.py` tests the *Developer API* path instead — only relevant if you
later switch off Vertex.)

---

## Capacity for ~100 users & the day-1 burst

**Short answer:** one machine is enough for 100 students **if** the API key is on the
**paid tier** (the Cloud Console key from step 1) and the launch-day machine is sized up.
Both are already set. The first-day crunch hits the Gemini **rate limit** long before it
strains the server.

**1. Vertex AI quotas — the thing that actually breaks first.** Vertex enforces
per-project, per-region requests-per-minute limits; a class hitting them at once gets
HTTP 429s and the "couldn't generate a response" fallback. Each student question =
**2 calls** (1 embedding + 1 generate), so budget ~2× your peak questions/minute.
- Before launch, check the limit: Console → **IAM & Admin → Quotas** (or Vertex AI →
  Quotas), filter for `gemini-3.1-flash-lite` generate-content requests per minute in the
  **global** region. If it looks tight for a 100-person burst, **request an increase a few
  days ahead** — approval is not instant.
- **Billing/trial:** the project is on a free trial (credit + a time limit). A semester
  outlasts the trial window, so **upgrade to a standard billing account before launch** —
  unused credit carries over and the project can't lapse mid-course.

**2. Machine size.** `fly.toml` launches a **`shared-cpu-2x` / 2 GB** machine (2 vCPUs) —
comfortably ~30–50 concurrent active sessions (FAISS is ~10 MB; the wait is network I/O,
so session threads overlap). After the first week, scale down if idle:
```bash
fly scale vm shared-cpu-1x --memory 1024 --app cege-3102-aita
```
Want extra margin for launch day only? `fly scale vm shared-cpu-4x --memory 4096` for
week 1, then back down.

**3. Pre-warm before class.** The FAISS index and Gemini client load lazily on the first
question per process. Ask one question yourself ~10 minutes before class so the first
student doesn't pay that one-time cost.

**4. Known limits of the single-machine design.**
- SQLite is on one volume → **no horizontal scaling**; vertical scale (bigger VM) is the
  only lever. Fine for 100 users; revisit only if the course grows to many hundreds.
- Under a concurrent-write burst, default SQLite can throw `database is locked`. Two small
  aita-core hardening changes remove this (WAL + `busy_timeout`) along with a graceful 429
  message — see **P0** in `STUDENT_UX_PLAN.md`. Recommended before a large launch.

---

## 3. Create the app and volume

```bash
fly apps create cege-3102-aita
fly volumes create aita_data --region ord --size 1 --app cege-3102-aita
```

`fly.toml` in this repo already points at the app, region (`ord`), volume, health
check, and a single warm `shared-cpu-2x` / 2 GB machine (see Capacity above).

---

## 4. Set secrets

```bash
fly secrets set --app cege-3102-aita \
  GCP_SA_KEY="$(base64 -w0 /tmp/adc.json)" \
  GOOGLE_REDIRECT_URI="https://cege-3102-aita.fly.dev/" \
  GOOGLE_COOKIE_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')" \
  ADMIN_PASSWORD="<choose-a-strong-password>"
```

- **`GCP_SA_KEY`** is the base64 of the service-account JSON; `main.py` decodes it to
  `/app/adc.json` at startup. `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION=global`, and
  `GOOGLE_APPLICATION_CREDENTIALS` are already in `fly.toml [env]` — not secrets.
- **`GOOGLE_COOKIE_KEY`** signs the auth cookie. Use a strong random value (as above) —
  **not** the OAuth client id the host `.env` currently uses. On a public URL a
  guessable key lets anyone forge a signed `@umn.edu` session, including admin access.
- **`ADMIN_PASSWORD`**: the code default is `admin3102` — change it here.
- **Do NOT set** `GEMINI_API_KEY`, `GOOGLE_GENAI_USE_VERTEXAI`, or
  `GOOGLE_GENAI_USE_ENTERPRISE` — those would select a different backend.

The Google OAuth `client_secret*.json` is baked into the image by the Dockerfile — no
secret needed for it. (Fly images are private.)

---

## 5. Configure the OAuth client & consent screen

Two separate things live under **APIs & Services** — both must be right or students
can't sign in.

### 5a. Authorized redirect URI (fixes `redirect_uri_mismatch`)

1. Console → **APIs & Services → Credentials**.
2. Open the OAuth 2.0 Client ID `943166039378-…apps.googleusercontent.com`.
3. Under **Authorized redirect URIs** add: `https://cege-3102-aita.fly.dev/`
   — it must match `GOOGLE_REDIRECT_URI` **exactly**, including `https` and the
   **trailing slash** (a missing slash is the #1 cause of the mismatch error). Keep
   the old host URI too if that deployment still runs.
4. (Optional) under **Authorized JavaScript origins** add `https://cege-3102-aita.fly.dev`.
5. Save. Propagation is usually immediate.

### 5b. Consent screen — let all ~100 students sign in

Console → **APIs & Services → OAuth consent screen**. Its publishing status decides who
may log in. (The `@umn.edu` restriction itself is enforced in app code, not here — a
non-UMN account that gets through Google is bounced by the app.)

| User type / status | Who can sign in | Verdict |
|---|---|---|
| **Internal** | any `@umn.edu` account — no cap, no verification | ✅ Best, if `aita-489419` is under the UMN Workspace org |
| **External + Testing** | only manually-added test users, **capped at 100** | ❌ Trap for a class |
| **External + In production** | anyone (app then limits to `@umn.edu`) — no cap | ✅ Fine |

This app requests only **non-sensitive scopes** (openid / email / profile), so publishing
an External app to **In production** needs **no Google verification** — just click
**Publish app**.

**Do:** use **Internal** if it's offered; otherwise **Publish** the External app to
production. **Don't** leave it in **Testing** — every student past the 100 test-user cap
(and anyone you didn't pre-add by email) will be blocked at sign-in.

---

## 6. Deploy

```bash
fly deploy --app cege-3102-aita
```

The build bakes in the FAISS index (`faiss_db/`), course materials, and the OAuth
client secret. First build takes a few minutes.

---

## 7. Post-deploy checks

```bash
fly status --app cege-3102-aita
fly logs   --app cege-3102-aita
```

Then in a browser:
- `https://cege-3102-aita.fly.dev/_stcore/health` → `ok`
- Sign in with an **@umn.edu** Google account.
- Ask *"What is Bayes' theorem?"* → expect a **pedagogical (non-answer)** reply plus a
  **Sources referenced** expander with downloadable handouts.
- Ask a homework-style problem → it must guide, not solve.
- Admin panel: sidebar **Admin Panel** (auto-granted to `chois@umn.edu` / `mlevin@umn.edu`,
  or via `ADMIN_PASSWORD`).

---

## 8. Operations

```bash
fly logs                                   # tail logs
fly ssh console                            # shell into the machine
fly deploy                                 # redeploy after code / wheel changes

# Back up the SQLite log DB (data lives on the volume):
fly ssh console -C "sqlite3 /app/data/aita.db .dump" > aita-backup-$(date +%F).sql
fly volumes snapshots list <volume-id>     # Fly also snapshots volumes daily
```

**Updating aita-core:** build a new wheel in the `aita-core` repo, drop
`aita_core-<ver>-py3-none-any.whl` into this repo (the Dockerfile globs `aita_core-*.whl`),
remove the old one, and `fly deploy`.

---

## 9. Cost

- One `shared-cpu-1x` / 1 GB machine, always on ≈ a few USD/month.
- Gemini Developer API: each student question = 1 embedding + 1 generate call. The free
  tier may cover a class; watch quota in AI Studio and add billing if you hit limits.

---

## 10. Rollback to Vertex AI (only if UMN policy forbids the Developer API)

1. Create a service-account key (role `roles/aiplatform.user`) in `aita-489419`.
2. `fly secrets set GCP_SA_KEY="$(base64 -w0 sa-key.json)"`
3. `fly secrets set GOOGLE_CLOUD_PROJECT=aita-489419 GOOGLE_CLOUD_LOCATION=global GOOGLE_APPLICATION_CREDENTIALS=/app/adc.json`
4. Uncomment the `[[files]]` block at the bottom of `fly.toml` (Fly base64-decodes the
   secret into `/app/adc.json`), then `fly deploy`.
