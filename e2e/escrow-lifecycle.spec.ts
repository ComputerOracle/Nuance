import { test, expect } from "@playwright/test";
import { generatePrivateKey, privateKeyToAccount } from "viem/accounts";
import { installMockWallet } from "./mock-wallet";
import { BACKEND_PORT } from "./ports";

// ROADMAP.md Part 3 5.3's E2E row: "Full escrow lifecycle: connect a
// mocked injected wallet -> create escrow -> submit deliverable -> watch
// consensus resolve -> release funds." Runs against the REAL app —
// playwright.config.ts's two webServer entries are the actual Next.js
// frontend and the actual FastAPI backend, on a throwaway SQLite db, with
// auto-deploy disabled (see that file's own comments) so this exercises
// the legacy off-chain path: no real GenVM contract, no real payable
// transaction, no wallet signature beyond the one-time SIWE-style login.
//
// Consensus is judged by services/consensus.py's deterministic offline
// heuristic (no LLM provider keys configured for this run) — a real,
// working, non-mocked consensus job, just not a billed LLM call. Its
// verdict is entirely keyword-driven (_HEURISTIC_POSITIVE_SIGNALS/
// _HEURISTIC_NEGATIVE_SIGNALS in that file): the deliverable text below
// is written specifically to land a guaranteed, reproducible APPROVE.
const DELIVERABLE_TEXT =
  "The landing page redesign is completed and delivered. All requirements " +
  "have been verified against the spec, documented in the attached PR, " +
  "and confirmed working on mobile.";

const BACKEND_URL = `http://localhost:${BACKEND_PORT}`;

// A fresh, random, test-only keypair (mock-wallet.ts's own hardcoded
// Hardhat key plays the escrow's *creator* throughout this test, via the
// injected mock wallet) — generated at runtime rather than another
// hardcoded constant specifically so there's no "did this get transcribed
// correctly" risk the way a copy-pasted well-known key would carry; a
// fresh key needs no real funds and no accuracy, only validity. Plays the
// escrow's *counterparty*, added 2026-09-12: routers/escrows.py::
// submit_deliverable now correctly rejects a submission from anyone but
// the real counterparty (a real authorization gap fixed the same day —
// see that endpoint's own docstring) — this test used to submit as the
// creator itself, which only ever "worked" because that check didn't
// exist yet. mock-wallet.ts's browser-injected mock can only ever
// represent ONE connected wallet at a time, so the counterparty's half of
// this flow goes straight to the backend via `request` (Playwright's own
// API context) rather than a second in-page wallet-switch — a real
// signature from a real (test-only, freshly generated) key either way,
// just not driven through the UI's own wallet-connect flow for a second
// identity.
const counterpartyAccount = privateKeyToAccount(generatePrivateKey());

async function loginAs(
  request: import("@playwright/test").APIRequestContext,
  account: ReturnType<typeof privateKeyToAccount>
): Promise<string> {
  const nonceResp = await request.post(`${BACKEND_URL}/auth/nonce`, {
    data: { wallet_address: account.address },
  });
  const { message } = await nonceResp.json();
  const signature = await account.signMessage({ message });
  const verifyResp = await request.post(`${BACKEND_URL}/auth/verify`, {
    data: { wallet_address: account.address, message, signature },
  });
  const { access_token: accessToken } = await verifyResp.json();
  return accessToken;
}

test("create escrow, submit deliverable, consensus resolves, release payment", async ({ page, request }) => {
  const address = await installMockWallet(page);
  await page.goto("/app");

  // --- Connect wallet ------------------------------------------------
  // .first(): the dashboard's empty-state card has its own "Connect
  // Wallet" button too, alongside the sidebar's (which renders first in
  // the DOM) — either opens the same WalletModal, so first() is fine.
  await page.getByRole("button", { name: "Connect Wallet" }).first().click();
  await page.getByText("MetaMask", { exact: true }).click();
  // The sidebar swaps "Connect Wallet" for the connected address once
  // use-wallet-connection.ts's connect() resolves (real personal_sign,
  // via the mock's Node-side viem signer, then a real POST /auth/verify).
  // formatAddress's own slice(0,6)+"..."+slice(-4) shape, matching
  // use-wallet-connection.ts exactly, not a loose text match — a real
  // "connected" signal, not just the label every wallet-box state shows.
  const shortAddress = `${address.slice(0, 6)}...${address.slice(-4)}`;
  await expect(page.getByText(shortAddress)).toBeVisible();
  await expect(page.getByRole("button", { name: "Connect Wallet" })).toHaveCount(0);

  // --- Create escrow ---------------------------------------------------
  await page.getByRole("button", { name: "+ New Escrow" }).click();
  await page.getByPlaceholder("e.g. Landing page redesign").fill("E2E Landing Page Redesign");
  await page.getByPlaceholder(/^0/).fill(counterpartyAccount.address);
  await page.getByPlaceholder("1500").fill("250");
  await page
    .getByPlaceholder(/Site matches Figma spec/)
    .fill("Page matches the spec, loads fast, and is responsive.");
  const createResponse = page.waitForResponse(
    (r) => r.url().endsWith("/escrows") && r.request().method() === "POST"
  );
  await page.getByRole("button", { name: "Create Escrow" }).click();
  const { id: escrowId } = await (await createResponse).json();

  // submitCreate navigates straight to the new escrow's detail view.
  await expect(page.getByText("E2E Landing Page Redesign")).toBeVisible();

  // --- Submit deliverable, as the real counterparty ------------------------
  // Straight to the backend, not through the UI's own textarea/button —
  // the wallet connected in-page throughout this test is the *creator*
  // (mock-wallet.ts's single mocked identity), and the creator submitting
  // its own deliverable is now correctly rejected (see this file's own
  // top-of-file note). A real second wallet, doing exactly what a real
  // counterparty using a different browser/wallet would.
  const counterpartyToken = await loginAs(request, counterpartyAccount);
  const deliverResp = await request.post(`${BACKEND_URL}/escrows/${escrowId}/deliverable`, {
    headers: { Authorization: `Bearer ${counterpartyToken}` },
    data: { text: DELIVERABLE_TEXT },
  });
  expect(deliverResp.ok()).toBe(true);
  const { consensus_job_id: consensusJobId } = await deliverResp.json();

  // --- Wait for consensus to resolve ---------------------------------------
  // Real backend consensus (MIN_DELIBERATION_SECONDS = 1.5s), polled
  // directly rather than watched live over the WS/SSE channel — this
  // browser session never submitted the deliverable itself (the raw API
  // call above did), so it has no live job id of its own to subscribe to.
  // Polling app.enums.ConsensusStage.DONE (3) the same way use-consensus-
  // polling.ts's own DB-polling fallback does.
  await expect
    .poll(
      async () => {
        const resp = await request.get(`${BACKEND_URL}/consensus/${consensusJobId}`);
        const body = await resp.json();
        return body.stage;
      },
      { timeout: 20_000 }
    )
    .toBe(3); // ConsensusStage.DONE

  // A fresh load picks up the persisted verdict via nuance-app.tsx's own
  // "verdict from a job this browser session never tracked live" fallback
  // (built 2026-09-08 for the identical "judged elsewhere" shape — see
  // that fix's own commit) — the exact same code path a real second
  // party's browser, or this same browser reopened later, would hit.
  // Reloading resets ALL client-side state, wallet connection included
  // (use-wallet-connection.ts has no silent-reconnect-on-mount — only the
  // JWT itself survives, in localStorage) — reconnect the same way the
  // top of this test did, which is also what re-triggers loadData() and
  // actually re-fetches escrows (there's no periodic background refetch
  // of the list, only on mount/on wallet-connect), then re-open the same
  // escrow from the now-refreshed dashboard (no per-escrow URL/route to
  // deep-link into instead).
  await page.reload();
  await page.getByRole("button", { name: "Connect Wallet" }).first().click();
  await page.getByText("MetaMask", { exact: true }).click();
  await expect(page.getByText(shortAddress)).toBeVisible();
  await page.getByText("E2E Landing Page Redesign").click();

  const releaseButton = page.getByRole("button", { name: "Release Payment" });
  await expect(releaseButton).toBeVisible({ timeout: 10_000 });

  // Heuristic verdict text should be visible too — not just the button.
  await expect(page.getByText(/Offline heuristic fallback/).first()).toBeVisible();

  // --- Release payment ----------------------------------------------------
  // Confirmed live (2026-09-08): releasePayment() (nuance-app.tsx) resets
  // activeEscrowJobId to null right after POST /escrows/{id}/release
  // succeeds, which resets useConsensusPolling's whole state back to
  // IDLE_STATE (verdict: null) — the ConsensusPanel's own "✓ Payment
  // already released." action text lives inside that verdict-driven
  // block, so it (and the whole verdict panel, including this button)
  // disappears along with it, replaced by the idle "Awaiting deliverable
  // submission…" panel. The actual, persistent confirmation is the
  // escrow's own StatusBadge (status.ts's STATUS_META.approved.label) —
  // that's what's asserted here, not the transient panel text.
  await releaseButton.click();
  await expect(releaseButton).toHaveCount(0);
  // .first(): StatusBadge renders this same "Approved" label for both the
  // escrow itself and its (only) milestone — either instance confirms
  // release succeeded, so this doesn't need to disambiguate between them.
  await expect(page.getByText("Approved", { exact: true }).first()).toBeVisible();
});
