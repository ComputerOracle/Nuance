# Nuance SDKs

TypeScript and Python clients for the Nuance API, both generated from one
OpenAPI spec (`openapi.json`, exported from the live FastAPI app — see
`../backend/scripts/export_openapi.py`). ROADMAP.md Part 4 §6.1/§6.3.

```
sdk/
  openapi.json                 <- single source of truth, regenerate via generate.sh
  generate.sh                  <- regenerates openapi.json + both clients below
  typescript/                  <- @nuance/sdk (npm)
  python/nuance-client/        <- nuance-client (PyPI-shaped, not yet published)
```

Regenerate both after any backend route/schema change:

```bash
./generate.sh
```

## Why generated, not hand-written

The backend already fully describes its own request/response shapes via
Pydantic schemas (`backend/app/schemas/`); FastAPI turns those into an
OpenAPI document for free. Hand-maintaining two more copies of the same
types in TypeScript and Python (on top of the frontend's own
`lib/api.ts`) would just be a third place for those shapes to drift out of
sync. Generating both clients from the one spec means a backend schema
change surfaces as a diff in `sdk/` the next time `generate.sh` runs,
rather than a silent runtime mismatch an external integrator hits first.

## Two credential shapes, one precedence

Both clients expose the same two credentials, matching
`backend/app/dependencies.py::require_user_with_scope`'s own precedence
(X-Api-Key checked first, exclusively, if present; JWT bearer otherwise):

- **`apiKey` / `api_key`** — a key from `POST /auth/api-keys`
  (`ApiKeyIssueResponse.key`, shown once at creation), for non-browser/
  agent callers (ROADMAP.md §6.1). Scoped to one or more of
  `escrow:create`, `bet:place`, `evidence:submit`, `vote:cast` — the write
  routes opened to agents; everything else (dispute enforcement, escrow
  release, governance finalize, ...) stays JWT-only.
- **`accessToken` / `access_token`** — the wallet-signature JWT from
  `POST /auth/verify`, for a full browser-equivalent session.

### TypeScript

```ts
import { createNuanceClient } from "@nuance/sdk";

const nuance = createNuanceClient({
  baseUrl: "https://api.nuance.example",
  apiKey: "nuance_live_<id>_<secret>",
});

const escrow = await nuance.createEscrowEscrowsPost({
  body: { counterparty_address: "0x...", title: "...", asset_symbol: "USDC", /* ... */ },
});
```

See `typescript/README.md` for install/build instructions and
`typescript/src/client.ts` for the full `createNuanceClient` doc comment.

### Python

```python
from nuance_client.convenience import create_nuance_client
from nuance_client.api.escrows import create_escrow_escrows_post
from nuance_client.models import EscrowCreate

client = create_nuance_client("https://api.nuance.example", api_key="nuance_live_<id>_<secret>")

resp = create_escrow_escrows_post.sync(
    client=client,
    body=EscrowCreate(counterparty_address="0x...", title="...", asset_symbol="USDC"),
)
```

See `python/nuance-client/README.md` (generator-authored — install/usage
basics) and `python/nuance-client/nuance_client/convenience.py` for the
`create_nuance_client` doc comment.

## Multi-asset escrows (ROADMAP.md §6.2)

`EscrowCreate.asset_symbol` (default `"GEN"`) picks the settlement asset by
symbol — see `AssetRead` in either generated client's models for the full
shape (`symbol`, `decimals`, `contract_address`, `is_native`). Amounts on
the wire are still plain decimal strings; it's `asset.decimals` that says
how to interpret them (GEN: 18, USDC: 6) rather than every amount being
assumed 2-decimal USD.

## Toolchain

- TypeScript: [`@hey-api/openapi-ts`](https://heyapi.dev/) — generates
  typed request functions + a `client-fetch` runtime.
- Python: [`openapi-python-client`](https://github.com/openapi-generators/openapi-python-client)
  — generates a `Client`/`AuthenticatedClient` pair (httpx-based, sync +
  async) plus one function per operation.

Neither is hand-modified inside `generated/` (TS) or the bulk of
`nuance_client/` (Python, everything but `convenience.py`) — treat those
as build output. `generate.sh` overwrites them from `openapi.json` every
run; hand-written glue lives only in `typescript/src/client.ts` and
`python/nuance-client/nuance_client/convenience.py`, which the generator
never touches.
