/**
 * Hand-written entry point around the generated client (src/generated/,
 * built by `npm run generate` from ../openapi.json — see openapi-ts.config.ts
 * and never edited directly, same convention Python's `nuance_client/client.py`
 * mirrors).
 *
 * The generator produces one function per operation plus a shared,
 * module-level `client` singleton (generated/client.gen.ts) that every one
 * of those functions defaults to when no `client` option is passed. Rather
 * than have every consumer import that singleton and call `.setConfig(...)`
 * themselves, `createNuanceClient` wraps that in a small factory: one call
 * configures the base URL and credentials, and the returned object bundles
 * every generated SDK function so a caller never touches src/generated/
 * directly.
 *
 * Two credential shapes, matching backend/app/dependencies.py's own
 * precedence (X-Api-Key checked first, exclusively, if present; JWT bearer
 * otherwise):
 *   - `apiKey`: for non-browser/agent callers (ROADMAP.md Part 4 6.1) — sent
 *     as a plain X-Api-Key header on every request, since that's a bare
 *     FastAPI `Header(...)` parameter on the handful of scoped write routes,
 *     not a registered OpenAPI security scheme (see that file's own
 *     docstring on why: it deliberately isn't a fastapi.security class).
 *   - `accessToken`: the wallet-signature JWT a browser session gets from
 *     POST /auth/verify — this ends up in Authorization: Bearer, and IS a
 *     registered `HTTPBearer` security scheme, so it's wired through the
 *     generated client's `auth` callback rather than a raw header.
 *
 * A caller needing both (e.g. an agent that also wants to call the
 * JWT-only-guarded routes, like /disputes/{id}/enforce) can pass both; each
 * request only ever sends the one its own generated function was built
 * with a `security` entry for.
 */
import { client as generatedClient } from "./generated/client.gen";
import * as sdk from "./generated/sdk.gen";

export * from "./generated/types.gen";
export type { Client } from "./generated/client";

export interface NuanceClientOptions {
  /** e.g. "https://api.nuance.example" or "http://localhost:8000" — no
   * trailing slash needed, matches every route in openapi.json starting
   * with "/". */
  baseUrl: string;
  /** Full key as returned once, at creation time, by
   * `POST /auth/api-keys` (ApiKeyIssueResponse.key) — "nuance_live_<id>_<secret>".
   * Never recoverable after that response; see backend/app/security.py's
   * generate_api_key docstring. */
  apiKey?: string;
  /** JWT from POST /auth/verify's `access_token` field. */
  accessToken?: string;
}

export type NuanceClient = typeof sdk;

/** Configures the shared generated client singleton and returns every
 * generated operation function bound to it. Safe to call more than once in
 * a process (e.g. one instance per tenant/base URL in a server context) —
 * each call only mutates config read at request time, not process-global
 * state beyond that singleton itself; for genuinely concurrent multi-tenant
 * use in one process, pass `client: createClient(createConfig(...))`
 * (from "./generated/client") as a per-call option to the individual sdk.*
 * functions instead of relying on this singleton. */
export function createNuanceClient(options: NuanceClientOptions): NuanceClient {
  generatedClient.setConfig({
    baseUrl: options.baseUrl,
    headers: options.apiKey ? { "X-Api-Key": options.apiKey } : undefined,
    auth: options.accessToken ? () => options.accessToken : undefined,
  });
  return sdk;
}
