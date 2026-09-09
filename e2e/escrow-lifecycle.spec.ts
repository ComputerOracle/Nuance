import { test, expect } from "@playwright/test";
import { installMockWallet } from "./mock-wallet";

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

const DUMMY_COUNTERPARTY = "0x000000000000000000000000000000000000e2e2"; // 40 hex chars, verified via node -e

test("create escrow, submit deliverable, consensus resolves, release payment", async ({ page }) => {
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
  await page.getByPlaceholder(/^0/).fill(DUMMY_COUNTERPARTY);
  await page.getByPlaceholder("1500").fill("250");
  await page
    .getByPlaceholder(/Site matches Figma spec/)
    .fill("Page matches the spec, loads fast, and is responsive.");
  await page.getByRole("button", { name: "Create Escrow" }).click();

  // submitCreate navigates straight to the new escrow's detail view.
  await expect(page.getByText("E2E Landing Page Redesign")).toBeVisible();

  // --- Submit deliverable -----------------------------------------------
  await page
    .getByPlaceholder("Paste deliverable URL, PR link, or describe the completed work for AI review…")
    .fill(DELIVERABLE_TEXT);
  await page.getByRole("button", { name: "Submit for AI Review" }).click();

  // --- Watch consensus resolve -------------------------------------------
  // Real backend consensus (MIN_DELIBERATION_SECONDS = 1.5s) delivered over
  // the real WS/SSE/polling channel (use-consensus-polling.ts) — generous
  // timeout for CI variance, not because this is normally slow.
  const releaseButton = page.getByRole("button", { name: "Release Payment" });
  await expect(releaseButton).toBeVisible({ timeout: 20_000 });

  // Heuristic verdict text should be visible too — not just the button.
  // .first(): the same reasoning can legitimately appear twice once a
  // full data reload has happened (the live consensus panel AND the
  // milestone's own persisted `reasoning` field) — this only needs to
  // confirm the text showed up somewhere, not police duplication.
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
