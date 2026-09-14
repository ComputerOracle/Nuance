# Nuance — First Production Deploy

Two independent halves, coordinated by one env var each way: Chibuikem
deploys the backend (this doc's §1), Emma deploys the frontend (§2) to
whatever host she picks — then each points at the other's real URL (§3).
Nothing here has happened yet as of this writing; this is the actual
"go live" step ROADMAP.md's Part 4 checklist doesn't itself cover.

## 1. Backend → Render

### What had to change first (already done, in this same pass)

- **`backend/app/services/genlayer_{rpc,write,deploy}.py` all shell out
  to `npx tsx scripts/genlayer-*.ts`** (no verified Python GenLayer SDK
  exists — see `genlayer_rpc.py`'s own docstring). That means the
  deployed backend isn't Python-only at runtime: it needs Node +
  this repo's root `node_modules` alongside `backend/`'s own deps.
  Render's native Python runtime has no Node, so **`Dockerfile.backend`**
  (repo root) is the deployable unit, not `backend/` in isolation —
  Python 3.13 base image (matches `.github/workflows/ci.yml`'s pin) +
  Node 22 via NodeSource, `npm ci --omit=dev` for the root deps, `pip
  install` for `backend/requirements.txt`, then `scripts/`, `contracts/`,
  `lib/`, `backend/` copied in.
- **`tsx` moved from `devDependencies` to `dependencies`** in the root
  `package.json` — it's invoked by every one of those subprocess calls
  in production, not just a local dev tool. Verified `npm ci --omit=dev`
  still installs it (and `genlayer-js`) after the move.
- **`Settings.database_url` now rewrites a bare `postgres://`/
  `postgresql://` scheme to `postgresql+asyncpg://`** (`backend/app/
  config.py`) — Render's managed Postgres hands you the former, but
  both `db.py`'s `create_async_engine` and `alembic/env.py` need the
  latter (SQLAlchemy picks a DBAPI driver from the URL scheme alone, and
  the un-suffixed scheme resolves to sync `psycopg2`, which isn't even
  installed here). Covered by `backend/tests/test_config.py`; full suite
  (314/314) still passes.
- **`render.yaml`** (repo root) — the actual Blueprint. Provisions a free
  Postgres instance and the web service together, and wires `DATABASE_URL`
  from the former to the latter automatically. `alembic upgrade head`
  runs from `Dockerfile.backend`'s own `CMD` on every boot, not as a
  `preDeployCommand` — Render's free tier doesn't support
  `preDeployCommand` at all (confirmed live: "pre-deploy command is not
  supported for free tier services"). Idempotent, and harmless at the
  single instance the free plan gives you; see the Dockerfile's own
  comment on moving it back once/if this goes multi-instance.

### Steps

1. Render dashboard → **New** → **Blueprint** → connect the
   `ComputerOracle/Nuance` GitHub repo. Render reads `render.yaml` off
   the branch you pick and shows you every resource it's about to
   create before you confirm anything.
2. It'll prompt for every `sync: false` var in `render.yaml` — paste
   these straight from your local `backend/.env`, don't retype them:
   `GENLAYER_PRIVATE_KEY`, `GEMINI_API_KEY`, `GOVERNANCE_GEMINI_API_KEY`,
   `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `TWITTERAPI_IO_KEY`,
   `TWITTER_BEARER_TOKEN`. `SENTRY_DSN` can stay blank for now (it's a
   true no-op unset — `app/observability.py::init_sentry`). For
   `CORS_ORIGINS`, enter `http://localhost:3000` for now — you'll come
   back and add Emma's real frontend URL once it exists (§3). The six
   `*_CONTRACT_ADDRESS` vars and `JWT_SECRET` need no input — the first
   are literal values already in `render.yaml` (they're public on-chain
   addresses, ROADMAP.md §4.4's table), the second is Render-generated.
3. First deploy will be slow-ish (a few minutes) — it's building Node +
   Python + both dependency trees from scratch, not a cached buildpack.
   Watch the boot log for the `alembic upgrade head` line specifically:
   it running clean against a brand-new Postgres is the real first proof
   this works, not just "the container started."
4. Verify against the real URL Render gives you
   (`https://nuance-backend-XXXX.onrender.com` or your chosen name):
   ```bash
   curl https://<your-service>.onrender.com/health
   # {"status":"ok"}
   curl https://<your-service>.onrender.com/openapi.json | head -c 200
   # confirms the full API surface actually came up, not just /health
   ```

### Known free-tier trade-offs (fine for now, not fine forever)

- **The free Postgres instance expires 30 days after creation**, with a
  14-day grace period to upgrade before Render deletes it (and its
  data) outright. This isn't a maybe — put a reminder somewhere, or
  upgrade the `nuance-db` plan in `render.yaml` before day 30 if this
  deploy is meant to stick around.
- **The free web service spins down after ~15 minutes idle** and takes
  a real cold-start hit (10s+) on the next request. Fine for a demo
  link; not what you want for a launch anyone's actually depending on —
  bump `plan` on the `nuance-backend` service when that matters.
- **`REDIS_URL` is deliberately left unset.** The consensus WebSocket
  channel degrades to plain per-connection DB polling without it (same
  shape as every other optional integration in this app) — a real
  tradeoff, not a bug, until multi-instance fan-out actually matters.

## 2. Frontend → Emma

Nothing here needs Render specifically — the frontend (repo root:
`app/`, `components/`, `lib/`) is a standard Next.js 16 app, and
[Next.js's own deploy guide](node_modules/next/dist/docs/01-app/01-getting-started/17-deploying.md)
lists Vercel as a verified adapter (zero-config for this repo — it
already builds clean: `npm run build` passes, 5 static routes). Render,
Netlify, and Cloudflare are also real options if there's a reason to
prefer one; only Vercel and Bun currently run the full adapter
compatibility suite.

**Whichever host, two things have to be true before the first deploy:**

1. **Env vars, set before the build, not after.** `NEXT_PUBLIC_*` vars
   get inlined into the JS bundle at `next build` time — changing them
   post-deploy does nothing until the next rebuild. Set on the host
   (Vercel: Project Settings → Environment Variables) before triggering
   the first build:
   - `NEXT_PUBLIC_API_URL` — the real Render backend URL from §1 (no
     trailing slash), e.g. `https://nuance-backend-XXXX.onrender.com`.
   - The six `NEXT_PUBLIC_*_CONTRACT_ADDRESS` vars — copy verbatim from
     **ROADMAP.md §4.4's table**, not from a local `.env.local`: this
     pass found this repo's own `.env.local` had `NEXT_PUBLIC_DISPUTE_
     COURT_CONTRACT_ADDRESS` set to a stale, wrong address (not the one
     `backend/.env`/ROADMAP.md actually use) — fixed locally, but it's
     the kind of drift a second machine's `.env.local` (gitignored, so
     never synced) can just as easily have. Same six values `render.yaml`
     sets on the backend side.
2. **If the host isn't Vercel/Bun** (Docker, a plain Node server,
   self-hosted): add `output: "standalone"` to `next.config.ts` first —
   [the self-hosting guide](node_modules/next/dist/docs/01-app/02-guides/self-hosting.md)
   covers what that changes about the build output. Not needed for
   Vercel, which handles this itself.

**One real gap, not solved here:** `CORS_ORIGINS` (§1) is an exact-match
origin list, not a wildcard — if the host is Vercel, every preview
deployment gets its own random subdomain that won't be in that list.
Fine for testing against the production domain; preview-deploy API
calls will 403 on CORS until someone either adds `allow_origin_regex`
for `*.vercel.app` to `app/main.py`'s `CORSMiddleware`, or the workflow
just doesn't rely on preview URLs hitting the real backend.

## 3. The handoff, both directions

- Once §1's backend URL is real: Emma sets `NEXT_PUBLIC_API_URL` to it
  (§2) before her first build.
- Once §2's frontend URL is real: Chibuikem adds it to `CORS_ORIGINS` on
  the Render service (dashboard → nuance-backend → Environment) —
  comma-separated, no spaces, e.g.
  `http://localhost:3000,https://nuance.vercel.app`. This restarts the
  service but doesn't rebuild it.

## Also worth knowing before either of you touches this

`backend/nuance.db` is currently a **tracked file in git**
(`git ls-files` confirms it), despite `*.db` being in `backend/
.gitignore` — it was evidently force-added before that rule existed, and
it's the file `git status` is showing as modified right now. It plays no
role in this deploy (Render uses the real Postgres instance §1
provisions, not this file) but every future local commit will keep
picking up whatever dev data happens to be in it unless it's untracked:
`git rm --cached backend/nuance.db` (keeps the file on disk, just stops
tracking it going forward) — not done here since it touches shared repo
history, worth doing deliberately rather than as a side effect of an
unrelated commit.
