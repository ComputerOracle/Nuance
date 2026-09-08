# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

# ACTUAL ROOT CAUSE (found 2026-09-06 via GenLayer Studio bisection, not
# guessed): GenVM's runner-comment parser treats the Depends line plus any
# *immediately following, contiguous* "#" comment lines as one block, and
# it can only contain that single JSON directive. A long doc comment
# placed directly under Depends (no blank line) breaks parsing on every
# contract, regardless of hash or contract body — confirmed by bisecting
# a minimal contract on Studio down to this exact rule. The blank line
# above this paragraph is the actual fix. Two prior "fixes" turned out to
# be red herrings that happened to correlate with real deploy attempts:
# switching the Depends hash (round 1) and TreeMap[K,V]() -> TreeMap()
# (round 3, still correct Python hygiene — GenericAlias really isn't
# callable — but not what was blocking deployment here, confirmed by a
# controlled 2x2 test isolating hash vs. TreeMap style).
#
# Nuance Dispute Court — Part 2, Step 2 (1 of 2).
#
# Architecture note: unlike NuanceEscrow (one contract instance deployed
# per escrow agreement), this is a single SHARED REGISTRY — one Dispute
# Court contract for the whole app, holding many disputes keyed by
# dispute_id. That's the more natural reading of the spec (it lists
# "dispute ID" as a field a single dispute record needs, which only makes
# sense if many disputes share one contract), it mirrors backend/app/
# models/core.py's Dispute table today (many rows, one table), and it
# avoids paying GenVM deployment cost for every single dispute the way a
# real court hears many cases rather than being rebuilt per case.
#
# Sources & confidence: identical citation list to nuance_escrow.py's own
# header (football_bets.py, the first-contract + prediction-market docs
# examples, the equivalence-principle page) — not re-quoted here, see that
# file. This contract intentionally never calls emit_transfer/moves funds
# — it only produces a ruling. Whatever acts on that ruling (the Escrow
# contract, or an off-chain relayer once Step 3/4 exist) is a separate
# concern, kept separate on purpose rather than have the court double as
# a payer.

from genlayer import *
from dataclasses import dataclass


@allow_storage
@dataclass
class Dispute:
    dispute_id: u256
    escrow_address: Address
    claimant: Address
    respondent: Address
    claim_statement: str
    evidence_url: str
    # "open" | "resolved" | "dismissed". The spec named these three states
    # but not what drives dismissed vs. resolved — this file's own
    # interpretation, flagged for review: "dismissed" is the claimant
    # withdrawing their own claim before adjudication (dismiss_dispute);
    # "resolved" covers either ruling direction once adjudicate_dispute
    # has actually run.
    status: str
    # "" until resolved, then exactly "favor_claimant" | "favor_respondent"
    ruling: str
    reasoning: str


class NuanceDisputeCourt(gl.Contract):
    disputes: TreeMap[u256, Dispute]
    dispute_count: u256

    def __init__(self):
        """Correction (2026-09-06, third round): the previous fix
        (`TreeMap[u256, Dispute]()`) was itself the bug — a live deploy
        came back ACCEPTED at the consensus layer but
        txExecutionResultName: FINISHED_WITH_ERROR (all 5 validators
        voted DISAGREE), because subscripting a generic and then calling
        it (`SomeGeneric[X, Y]()`) produces a GenericAlias, which isn't
        callable in GenVM's Python runtime — a TypeError at execution
        time, not a type-checking issue. The bracket form stays on the
        class-level *annotation* above (that's just a type hint); the
        actual runtime instantiation is bare `TreeMap()`, exactly like
        official GenVM examples (football_bets.py, wizard-of-coin) use."""
        self.disputes = TreeMap()
        self.dispute_count = 0

    @gl.public.write
    def file_dispute(
        self,
        escrow_address: str,
        respondent: str,
        claim_statement: str,
        evidence_url: str = "",
    ) -> u256:
        """Not in the original spec (which only named adjudicate_dispute)
        — a dispute has to be created by something before it can be
        adjudicated. Added as the obvious, necessary completion, same
        reasoning as the prediction market's claim_winnings."""
        dispute_id = self.dispute_count
        self.disputes[dispute_id] = Dispute(
            dispute_id=dispute_id,
            escrow_address=Address(escrow_address),
            claimant=gl.message.sender_address,
            respondent=Address(respondent),
            claim_statement=claim_statement,
            evidence_url=evidence_url,
            status="open",
            ruling="",
            reasoning="",
        )
        self.dispute_count += 1
        return dispute_id

    @gl.public.write
    def add_evidence(self, dispute_id: u256, evidence_url: str) -> None:
        """Added 2026-09-08 — file_dispute only ever took one evidence_url,
        at filing time, with no way to add more afterward. That gap made
        the app's own "Submit Evidence" button quietly fall back to a
        completely different, off-chain code path (services/consensus.py)
        for ANY dispute past its initial filing, on-chain or not — found
        live: a dispute correctly filed on-chain got its ruling silently
        produced by that off-chain path's own emergency keyword-matching
        fallback instead of real GenVM validators, with nothing in the UI
        making the swap visible. This closes the actual gap rather than
        just hiding the app's own workaround for it.

        Either party (not just the claimant) may add evidence — mirrors
        the off-chain submit_evidence, which any dispute participant can
        use. Only while the dispute is still "open"; matches
        adjudicate_dispute's own guard, since evidence added after a
        ruling has nothing left to inform.

        Multiple URLs are stored newline-separated in the same
        evidence_url field, not a new TreeMap — this contract can only
        have ONE TreeMap shape at all (see nuance_governance.py's header
        for the fullest account of that constraint), so a second
        evidence-list field of any container type is off the table.
        adjudicate_dispute below is updated to fetch and concatenate
        every URL in the list, not just the first."""
        if dispute_id not in self.disputes:
            raise gl.vm.UserError("No such dispute.")
        dispute = self.disputes[dispute_id]
        if gl.message.sender_address not in (dispute.claimant, dispute.respondent):
            raise gl.vm.UserError("Only a party to this dispute can add evidence.")
        if dispute.status != "open":
            raise gl.vm.UserError(f"Dispute is '{dispute.status}', not open for evidence.")
        if not evidence_url:
            raise gl.vm.UserError("evidence_url can't be blank.")

        if dispute.evidence_url:
            dispute.evidence_url = dispute.evidence_url + "\n" + evidence_url
        else:
            dispute.evidence_url = evidence_url

    @gl.public.write
    def dismiss_dispute(self, dispute_id: u256) -> None:
        if dispute_id not in self.disputes:
            raise gl.vm.UserError("No such dispute.")
        dispute = self.disputes[dispute_id]
        if gl.message.sender_address != dispute.claimant:
            raise gl.vm.UserError("Only the claimant can withdraw their own dispute.")
        if dispute.status != "open":
            raise gl.vm.UserError(f"Dispute is '{dispute.status}', not open.")
        dispute.status = "dismissed"

    @gl.public.write
    def adjudicate_dispute(self, dispute_id: u256) -> None:
        if dispute_id not in self.disputes:
            raise gl.vm.UserError("No such dispute.")
        dispute = self.disputes[dispute_id]
        if dispute.status != "open":
            raise gl.vm.UserError(f"Dispute is '{dispute.status}', not open for adjudication.")

        claim_statement = dispute.claim_statement
        evidence_url = dispute.evidence_url
        claimant_hex = dispute.claimant.as_hex
        respondent_hex = dispute.respondent.as_hex

        # Nondet blocks can't nest, so the web fetch + LLM call both live
        # inside the one leader_fn — same reasoning as nuance_escrow.py's
        # submit_deliverable, following football_bets.py's own
        # _check_match/get_match_result closure pattern.
        def leader_fn() -> dict:
            # evidence_url may hold multiple newline-separated URLs now —
            # see add_evidence's own docstring for why (one string field,
            # not a new TreeMap). Only the most recently added URL is
            # fetched — see the CONFIRMED LIVE note below for why more
            # than one isn't attempted yet. Every submitted URL still
            # lives in dispute.evidence_url for anyone to review via
            # get_dispute; only what actually reaches the ruling is
            # capped.
            #
            # CONFIRMED LIVE (2026-09-08, two separate real failed
            # transactions): gl.nondet.web.render(url, mode="text") —
            # this function's original choice — reliably produced
            # LEADER_TIMEOUT (status 13) on live Bradbury, with or
            # without add_evidence's multi-URL change (one URL alone
            # timed out too; a no-fetch control case on the same deploy
            # completed cleanly, isolating render() itself, not URL
            # count, as the cause). docs.genlayer.com documents a
            # lighter gl.nondet.web.get(url) alongside render() — likely
            # avoiding whatever full-page-rendering work render() does
            # (evaluating a page as if headless-browsing it, going by
            # render()'s own mode options of html/screenshot) that a
            # plain HTTP GET doesn't need. Switched here on that
            # evidence, verified against a real redeploy before trusting
            # it (see this contract's deploy history) — not a guess.
            # Wrapped in try/except (a real gap this file had none of
            # before): if a fetch is ever genuinely unreachable or slow,
            # every validator gets an honest "unreachable" note instead
            # of the whole transaction hanging/timing out again.
            # Truncated to 3000 chars — the raw page's full text could
            # otherwise blow the LLM's own context budget, a separate
            # way to stall the same nondet block.
            evidence_context = "No evidence URL was submitted."
            if evidence_url:
                urls = [u.strip() for u in evidence_url.split("\n") if u.strip()]
                if urls:
                    latest_url = urls[-1]
                    try:
                        response = gl.nondet.web.get(latest_url)
                        page_text = response.body.decode("utf-8", errors="replace")[:3000]
                    except Exception as exc:
                        page_text = f"(Evidence URL was unreachable or timed out: {exc})"
                    note = (
                        f" (plus {len(urls) - 1} earlier URL(s) also on record — "
                        "not fetched here, see evidence_url via get_dispute)"
                        if len(urls) > 1
                        else ""
                    )
                    evidence_context = f"[{latest_url}]{note}\n{page_text}"

            prompt = f"""You are an impartial arbitrator on Nuance's Dispute
Court, ruling on a disagreement between two counterparties to an escrow
agreement.

Claimant: {claimant_hex}
Respondent: {respondent_hex}

Claimant's statement:
{claim_statement}

Submitted evidence page content:
{evidence_context}

Rule in favor of whichever party's position is actually supported by the
evidence above — do not default to favoring the claimant just because
they filed first. Respond in JSON:
{{
    "ruling": str,
    "confidence": int,
    "reasoning": str
}}
"ruling" must be exactly "favor_claimant" or "favor_respondent". It is
mandatory that you respond only using the JSON format above, nothing
else. Don't include any other words or characters, your output must be
perfectly parsable by a JSON parser without errors."""
            return gl.nondet.exec_prompt(prompt, response_format="json")

        # Partial-field matching (docs.genlayer.com's Equivalence
        # Principle page): every validator independently re-runs
        # leader_fn and only has to agree with the leader on the
        # categorical `ruling` value — not on `reasoning`/`confidence`,
        # which are free to differ between independent LLM calls asking
        # the same qualitative question.
        def validator_fn(leader_result) -> bool:
            if not isinstance(leader_result, gl.vm.Return):
                return False
            own = leader_fn()
            leader_data = leader_result.calldata
            return str(own["ruling"]) == str(leader_data["ruling"])

        verdict = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)

        dispute.status = "resolved"
        dispute.ruling = str(verdict["ruling"])
        dispute.reasoning = str(verdict.get("reasoning", ""))

    @gl.public.view
    def get_dispute(self, dispute_id: u256) -> dict:
        if dispute_id not in self.disputes:
            raise gl.vm.UserError("No such dispute.")
        d = self.disputes[dispute_id]
        return {
            "dispute_id": d.dispute_id,
            "escrow_address": d.escrow_address.as_hex,
            "claimant": d.claimant.as_hex,
            "respondent": d.respondent.as_hex,
            "claim_statement": d.claim_statement,
            "evidence_url": d.evidence_url,
            "status": d.status,
            "ruling": d.ruling,
            "reasoning": d.reasoning,
        }

    @gl.public.view
    def get_dispute_count(self) -> u256:
        return self.dispute_count
