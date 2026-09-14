# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

# IMPORTANT: keep a blank line between the Depends line above and any
# comment block below it — a comment placed directly under Depends with
# no blank line breaks GenVM's runner-comment parser on every contract,
# independent of the hash (found 2026-09-06 via GenLayer Studio bisection;
# see nuance_dispute_court.py's header).
#
# Nuance Escrow — Part 2, Step 1. On-chain replacement for backend/app/
# services/consensus.py's MILESTONE path: the "was this deliverable good
# enough" judgment happens inside GenVM, decided by an independent
# validator committee via the equivalence principle, not by our backend.
#
# TRIMMED 2026-09-14 — this file's size (raw source bytes = the deploy
# payload; GenVM deploys the .py file's literal bytes, no build/minify
# step) had grown past whatever gas cap Bradbury enforces per deploy tx —
# every escrow created after this file's prior edit failed to deploy with
# "gas limit too high" (confirmed: nuance_prediction_market.py, deployed
# repeatedly in the same window at ~12KB, kept working fine; this file was
# ~20.7KB). The verbose research/incident narratives below were condensed
# to the load-bearing facts only — no logic below this header changed.
# Keep future comments here reasonably tight for the same reason; this
# contract gets deployed fresh once per escrow, unlike a bootstrap-once
# shared registry, so its size directly gates every new escrow's ability
# to go on-chain at all.

from genlayer import *
from dataclasses import dataclass


# --- Persistent types -------------------------------------------------


@allow_storage
@dataclass
class Milestone:
    name: str
    amount: u256
    criteria: str
    # "pending" | "in_review" | "approved" | "disputed" — this contract's
    # own business status, not GenVM's transaction-level status. Mirrors
    # backend/app/enums.py's StatusKey.
    status: str
    released: bool
    deliverable_text: str
    deliverable_url: str
    reasoning: str


# --- Contract -----------------------------------------------------------


class NuanceEscrow(gl.Contract):
    creator: Address
    counterparty: Address
    funded_amount: u256
    milestones: TreeMap[u256, Milestone]
    milestone_count: u256
    # "active" | "cancelled" — escrow-level, distinct from any individual
    # Milestone.status. See cancel_escrow for what it does/doesn't guard.
    status: str

    def __init__(
        self,
        creator: str,
        counterparty: str,
        milestone_name: str,
        milestone_amount: u256,
        milestone_criteria: str,
    ):
        # One milestone at creation, mirroring the off-chain create_escrow
        # (routers/escrows.py); use add_milestone for more.
        # `milestones` must be bare TreeMap(), not TreeMap[u256, Milestone]()
        # — the subscripted form is a real runtime TypeError in GenVM.
        # `creator` is a real constructor arg, NOT gl.message.sender_address
        # — every deploy here is backend-signed (services/genlayer_deploy.py
        # uses this app's own key, never the real creator's wallet), so
        # defaulting to the sender used to permanently brick every
        # creator-gated method against real users (real fund loss on live
        # Bradbury, 2026-09-08 — GenVM does not refund a payable call's
        # value just because the method then raises; see fund_escrow).
        self.creator = Address(creator)
        self.counterparty = Address(counterparty)
        self.funded_amount = 0
        self.milestones = TreeMap()
        self.milestone_count = 0
        self.status = "active"
        self._add_milestone(milestone_name, milestone_amount, milestone_criteria)

    def _add_milestone(self, name: str, amount: u256, criteria: str) -> u256:
        index = self.milestone_count
        self.milestones[index] = Milestone(
            name=name,
            amount=amount,
            criteria=criteria,
            status="pending",
            released=False,
            deliverable_text="",
            deliverable_url="",
            reasoning="",
        )
        self.milestone_count += 1
        return index

    @gl.public.write
    def add_milestone(self, name: str, amount: u256, criteria: str) -> u256:
        if gl.message.sender_address != self.creator:
            raise gl.vm.UserError("Only the escrow creator can add a milestone.")
        if self.status != "active":
            raise gl.vm.UserError(f"Escrow is '{self.status}' — cannot add a milestone.")
        return self._add_milestone(name, amount, criteria)

    # --- Funding ------------------------------------------------------
    # The sender check below runs AFTER gl.message.value has already
    # arrived — GenVM does not refund a payable call's attached value just
    # because the method body then raises, so a wrong sender's GEN
    # transfers in regardless (no withdrawal function exists here). Keep
    # any future creator-gated payable method's sender check first anyway.

    @gl.public.write.payable
    def fund_escrow(self) -> None:
        if gl.message.sender_address != self.creator:
            raise gl.vm.UserError("Only the escrow creator can fund this escrow.")
        if self.status != "active":
            raise gl.vm.UserError(f"Escrow is '{self.status}' — cannot fund it.")
        self.funded_amount += gl.message.value

    # --- Deliverable submission + AI-validator consensus ----------------

    @gl.public.write
    def submit_deliverable(
        self, milestone_index: u256, deliverable_text: str, deliverable_url: str = ""
    ) -> None:
        if gl.message.sender_address != self.counterparty:
            raise gl.vm.UserError("Only the escrow counterparty can submit a deliverable.")
        if self.status != "active":
            raise gl.vm.UserError(f"Escrow is '{self.status}' — cannot submit a deliverable.")
        if milestone_index not in self.milestones:
            raise gl.vm.UserError("No such milestone.")

        milestone = self.milestones[milestone_index]
        if milestone.status not in ("pending", "disputed"):
            raise gl.vm.UserError(f"Milestone is '{milestone.status}', not open for submission.")

        milestone.deliverable_text = deliverable_text
        milestone.deliverable_url = deliverable_url
        criteria = milestone.criteria

        # Nondet blocks can't nest, so the web fetch + LLM call both live
        # inside the one leader_fn.
        def leader_fn() -> dict:
            # gl.nondet.web.get(), not .render() — render() reliably
            # produced LEADER_TIMEOUT on live Bradbury (confirmed
            # 2026-09-08). Wrapped in try/except and truncated to 3000
            # chars: an unreachable URL gets an honest note instead of
            # hanging the nondet block, and a huge page can't blow the
            # LLM's context budget.
            proof_context = "No linked proof URL was submitted."
            if deliverable_url:
                try:
                    response = gl.nondet.web.get(deliverable_url)
                    proof_context = response.body.decode("utf-8", errors="replace")[:3000]
                except Exception as exc:
                    proof_context = f"(Proof URL was unreachable or timed out: {exc})"

            prompt = f"""You are an impartial reviewer adjudicating a milestone
deliverable for an escrow agreement between two independent parties.

Agreed criteria:
{criteria}

Submitted deliverable text:
{deliverable_text}

Linked proof/evidence page content:
{proof_context}

Decide whether the deliverable satisfies the agreed criteria. Respond in
JSON:
{{
    "approved": bool,
    "confidence": int,
    "reasoning": str
}}
It is mandatory that you respond only using the JSON format above, nothing
else. Don't include any other words or characters, your output must be
perfectly parsable by a JSON parser without errors."""
            return gl.nondet.exec_prompt(prompt, response_format="json")

        # Partial-field-matching equivalence principle: every validator
        # independently re-runs leader_fn and only has to agree with the
        # leader on `approved`, not on the prose `reasoning`/`confidence`,
        # which are legitimately allowed to differ between independent LLM
        # calls asking the same qualitative question.
        def validator_fn(leader_result) -> bool:
            if not isinstance(leader_result, gl.vm.Return):
                return False
            own = leader_fn()
            leader_data = leader_result.calldata
            return bool(own["approved"]) == bool(leader_data["approved"])

        verdict = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)

        milestone.status = "approved" if bool(verdict["approved"]) else "disputed"
        milestone.reasoning = str(verdict.get("reasoning", ""))

    # --- Release ----------------------------------------------------------

    @gl.public.write
    def release_milestone(self, milestone_index: u256) -> None:
        if gl.message.sender_address != self.creator:
            raise gl.vm.UserError("Only the escrow creator can release milestone funds.")
        if self.status != "active":
            raise gl.vm.UserError(f"Escrow is '{self.status}' — cannot release funds.")
        if milestone_index not in self.milestones:
            raise gl.vm.UserError("No such milestone.")

        milestone = self.milestones[milestone_index]
        if milestone.status != "approved":
            raise gl.vm.UserError("This milestone has not been approved by consensus.")
        if milestone.released:
            raise gl.vm.UserError("This milestone has already been released.")
        if milestone.amount > self.funded_amount:
            raise gl.vm.UserError("Escrow is not funded for this milestone's amount.")

        milestone.released = True
        self.funded_amount -= milestone.amount
        recipient = gl.get_contract_at(self.counterparty)
        recipient.emit_transfer(value=u256(milestone.amount), on="finalized")

    # --- Cancellation / refund --------------------------------------------

    @gl.public.write
    def cancel_escrow(self) -> None:
        # Refund path for GEN otherwise stuck forever (a counterparty who
        # vanishes, a milestone nobody ever approves). Creator-only.
        # Allowed only while no milestone has ever been approved — once
        # one has, the counterparty has a legitimate claim on at least
        # that milestone's share; NuanceDisputeCourt handles it past that
        # point, not a unilateral creator cancellation.
        # NOT enforced here (flagged rather than faked): a "milestone
        # deadline has passed" gate — GenVM has no documented on-chain
        # clock/timestamp primitive to check a deadline against.
        if gl.message.sender_address != self.creator:
            raise gl.vm.UserError("Only the escrow creator can cancel this escrow.")
        if self.status != "active":
            raise gl.vm.UserError(f"Escrow is already '{self.status}'.")

        # u256 loop via while/+=, not range()/int() — the only integer
        # looping pattern proven to work on live GenVM for a u256 storage
        # value.
        i: u256 = 0
        while i < self.milestone_count:
            if self.milestones[i].status == "approved":
                raise gl.vm.UserError(
                    "Cannot cancel — at least one milestone has already been approved. "
                    "Use release_milestone to pay it out, or file a dispute instead."
                )
            i += 1

        self.status = "cancelled"
        refund_amount = self.funded_amount
        self.funded_amount = 0
        if refund_amount > 0:
            recipient = gl.get_contract_at(self.creator)
            recipient.emit_transfer(value=u256(refund_amount), on="finalized")

    # --- Views ------------------------------------------------------------

    @gl.public.view
    def get_escrow(self) -> dict:
        return {
            "creator": self.creator.as_hex,
            "counterparty": self.counterparty.as_hex,
            "funded_amount": self.funded_amount,
            "milestone_count": self.milestone_count,
            "status": self.status,
        }

    @gl.public.view
    def get_milestone(self, milestone_index: u256) -> dict:
        if milestone_index not in self.milestones:
            raise gl.vm.UserError("No such milestone.")
        m = self.milestones[milestone_index]
        return {
            "name": m.name,
            "amount": m.amount,
            "criteria": m.criteria,
            "status": m.status,
            "released": m.released,
            "deliverable_text": m.deliverable_text,
            "deliverable_url": m.deliverable_url,
            "reasoning": m.reasoning,
        }
