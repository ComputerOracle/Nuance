"use client";

import { useEffect, useState } from "react";
import {
  agentDirectoryContractAddress,
  disputeCourtContractAddress,
  governanceContractAddress,
  validatorsContractAddress,
} from "@/lib/chain-config";
import { GENLAYER_BRADBURY, blockExplorerAddressUrl } from "@/components/app/genlayer-chain";

// Same fallback lib/api.ts and every use-*-polling hook already use —
// duplicated rather than imported (matching this codebase's own
// established convention for this one-line computation, e.g. use-
// consensus-polling.ts's own local apiBase()) rather than centralized.
function apiBase(): string {
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8010";
}

const HTTP_METHODS = ["get", "post", "put", "patch", "delete"] as const;
type HttpMethod = (typeof HTTP_METHODS)[number];

interface OpenApiOperation {
  summary?: string;
  description?: string;
  tags?: string[];
  deprecated?: boolean;
}

interface OpenApiSpec {
  info: { title: string; version: string; description?: string };
  paths: Record<string, Partial<Record<HttpMethod, OpenApiOperation>>>;
}

interface Endpoint {
  method: HttpMethod;
  path: string;
  summary: string;
  deprecated: boolean;
}

// bg-*/12 pairs with each method's own *-text token, matching how the
// rest of this app pairs a status color's fill with its text variant
// (StatusBadge, ChainStatusBadge, ...) — except warn, which globals.css
// only defines a --color-warn-text for (no plain --color-warn fill), so
// PUT/PATCH fall back to the neutral chip-hover fill instead of a
// non-existent bg-warn utility.
const METHOD_COLOR: Record<HttpMethod, string> = {
  get: "text-positive-text bg-positive/12",
  post: "text-review-text bg-review/14",
  put: "text-warn-text bg-chip-hover",
  patch: "text-warn-text bg-chip-hover",
  delete: "text-negative-text bg-negative/12",
};

/**
 * ROADMAP.md Part 4's Public docs site — "versioned API reference,
 * contract addresses per network." Fetches this deployment's own
 * `/openapi.json` (FastAPI generates it automatically, no extra backend
 * code needed) rather than a hand-written endpoint table that could
 * silently drift from the real API — the same "verify against the real
 * installed thing" instinct AGENTS.md asks of every doc lookup in this
 * repo applies to this repo's OWN docs too.
 */
export function DocsContent() {
  const [spec, setSpec] = useState<OpenApiSpec | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${apiBase()}/openapi.json`);
        if (!res.ok) throw new Error(`Backend returned ${res.status}`);
        const data = (await res.json()) as OpenApiSpec;
        if (!cancelled) setSpec(data);
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? `Couldn't reach the backend to load the live API reference: ${err.message}`
              : "Couldn't reach the backend to load the live API reference."
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const groups = groupByTag(spec);

  return (
    <main className="mx-auto max-w-[900px] px-8 py-14">
      <div className="mb-2 font-display text-[34px] font-bold">Nuance Developer Docs</div>
      <p className="mb-10 max-w-[640px] text-[15px] leading-relaxed text-fg-dim-2">
        The REST API AI-validator-consensus agreements are built on, and the deployed contract
        addresses backing them on GenLayer Bradbury testnet. The API reference below is generated
        live from this deployment&rsquo;s own OpenAPI schema — never hand-maintained, so it can&rsquo;t
        drift from what the API actually does.
      </p>

      <ContractAddresses />

      <div className="mb-4 mt-12 flex items-baseline justify-between gap-4">
        <div className="font-display text-xl font-bold">API Reference</div>
        {spec && (
          <div className="font-brand-mono text-xs text-fg-meta">
            {spec.info.title} · v{spec.info.version}
          </div>
        )}
      </div>

      {loading ? (
        <div className="rounded-[14px] border border-border-1 bg-surface-1 p-6 text-center text-sm text-fg-meta">
          Loading live API reference from {apiBase()}…
        </div>
      ) : error ? (
        <div className="rounded-[14px] border border-negative/30 bg-negative/10 p-4 text-sm text-negative-text">
          {error} Make sure the backend is reachable at{" "}
          <code className="font-brand-mono">{apiBase()}</code>, or set{" "}
          <code className="font-brand-mono">NEXT_PUBLIC_API_URL</code> to point at one that is.
        </div>
      ) : (
        <div className="flex flex-col gap-8">
          {groups.map(([tag, endpoints]) => (
            <div key={tag}>
              <div className="mb-2.5 text-sm font-semibold uppercase tracking-wide text-fg-meta">
                {tag}
              </div>
              <div className="flex flex-col gap-1.5">
                {endpoints.map((e) => (
                  <div
                    key={`${e.method}-${e.path}`}
                    className="flex items-start gap-3 rounded-[10px] border border-border-1 bg-surface-1 px-3.5 py-2.5"
                  >
                    <span
                      className={`shrink-0 rounded px-1.5 py-0.5 font-brand-mono text-[11px] font-bold uppercase ${METHOD_COLOR[e.method]}`}
                    >
                      {e.method}
                    </span>
                    <div className="min-w-0">
                      <div className="font-brand-mono text-[13px] text-fg-bright">
                        {e.path}
                        {e.deprecated && (
                          <span className="ml-2 rounded bg-chip-hover px-1 py-0.2 text-[10px] font-sans uppercase text-fg-meta">
                            Deprecated
                          </span>
                        )}
                      </div>
                      {e.summary && <div className="mt-0.5 text-xs text-fg-meta">{e.summary}</div>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}

function groupByTag(spec: OpenApiSpec | null): [string, Endpoint[]][] {
  if (!spec) return [];
  const byTag = new Map<string, Endpoint[]>();

  for (const [path, methods] of Object.entries(spec.paths)) {
    for (const method of HTTP_METHODS) {
      const op = methods[method];
      if (!op) continue;
      const tags = op.tags && op.tags.length > 0 ? op.tags : ["other"];
      const endpoint: Endpoint = {
        method,
        path,
        summary: op.summary || op.description?.split("\n")[0] || "",
        deprecated: Boolean(op.deprecated),
      };
      for (const tag of tags) {
        const list = byTag.get(tag) ?? [];
        list.push(endpoint);
        byTag.set(tag, list);
      }
    }
  }

  return Array.from(byTag.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([tag, endpoints]) => [
      tag,
      endpoints.sort((a, b) => a.path.localeCompare(b.path) || a.method.localeCompare(b.method)),
    ]);
}

function AddressRow({
  contract,
  address,
  note,
}: {
  contract: string;
  address: `0x${string}` | null;
  note: string;
}) {
  return (
    <tr className="border-b border-border-1 last:border-0">
      <td className="py-2.5 pr-4 text-sm font-semibold">{contract}</td>
      <td className="py-2.5 pr-4 font-brand-mono text-[13px]">
        {address ? (
          <a
            href={blockExplorerAddressUrl(address)}
            target="_blank"
            rel="noopener noreferrer"
            className="text-fg-bright underline underline-offset-2 hover:text-fg"
          >
            {address}
          </a>
        ) : (
          <span className="text-fg-faint-2">Not configured in this deployment</span>
        )}
      </td>
      <td className="py-2.5 text-xs text-fg-meta">{note}</td>
    </tr>
  );
}

/**
 * Only NuanceDisputeCourt and NuanceGovernance get a real address row —
 * both are genuine shared registries (ROADMAP.md 4.4.1's own account of
 * which of the six deployed contracts are load-bearing singletons vs.
 * per-agreement instances). NuanceEscrow/NuancePredictionMarket are
 * deployed fresh per escrow/market — there is no single canonical
 * address for either to list here, and showing one would misrepresent
 * how the app actually works. NuanceValidators/NuanceAgentDirectory are
 * deployed but not yet load-bearing (routers/validators.py, routers/
 * agents.py compute those directories from ConsensusJob history, not by
 * reading these contracts) — labeled as such rather than presented like
 * the other two.
 */
function ContractAddresses() {
  return (
    <div>
      <div className="mb-2.5 text-sm font-semibold uppercase tracking-wide text-fg-meta">
        Contract Addresses — {GENLAYER_BRADBURY.chainName}
      </div>
      <div className="overflow-x-auto rounded-[14px] border border-border-1 bg-surface-1 px-4">
        <table className="w-full min-w-[560px] text-left">
          <thead>
            <tr className="border-b border-border-1 text-[11px] uppercase tracking-wide text-fg-meta">
              <th className="py-2.5 pr-4 font-medium">Contract</th>
              <th className="py-2.5 pr-4 font-medium">Address</th>
              <th className="py-2.5 font-medium">Role</th>
            </tr>
          </thead>
          <tbody>
            <AddressRow
              contract="NuanceDisputeCourt"
              address={disputeCourtContractAddress()}
              note="Shared registry — every dispute filed on-chain goes through this one instance."
            />
            <AddressRow
              contract="NuanceGovernance"
              address={governanceContractAddress()}
              note="Shared registry — proposals and votes."
            />
            <AddressRow
              contract="NuanceValidators"
              address={validatorsContractAddress()}
              note="Deployed, not yet load-bearing — the real validator directory (GET /validators) is computed from consensus history, not read from this contract."
            />
            <AddressRow
              contract="NuanceAgentDirectory"
              address={agentDirectoryContractAddress()}
              note="Deployed, not yet load-bearing — same caveat as NuanceValidators (GET /agents)."
            />
          </tbody>
        </table>
      </div>
      <p className="mt-2.5 text-xs leading-relaxed text-fg-meta">
        <strong className="text-fg-dim-2">NuanceEscrow</strong> and{" "}
        <strong className="text-fg-dim-2">NuancePredictionMarket</strong> aren&rsquo;t listed here —
        each escrow and prediction market gets its own freshly-deployed contract instance rather
        than sharing one address; look up a specific one&rsquo;s address via{" "}
        <code className="font-brand-mono">GET /escrows/&#123;id&#125;</code> or{" "}
        <code className="font-brand-mono">GET /predictions/&#123;id&#125;</code>&rsquo;s own{" "}
        <code className="font-brand-mono">contract_address</code> field.
      </p>
    </div>
  );
}
