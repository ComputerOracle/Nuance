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
            evidence_context = "No evidence URL was submitted."
            if evidence_url:
                evidence_context = gl.nondet.web.render(evidence_url, mode="text")

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
