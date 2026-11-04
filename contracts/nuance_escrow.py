# { "Depends": "py-genlayer:babwp9t37jw9g4j2bccgn14g6x7x9s1f7dsmh7emvz735pz4zxa0" }

# Nuance Escrow — Production Upgradable Intelligent Contract
# Grounded in official GenLayer documentation (docs.genlayer.com/developers/intelligent-contracts/)
# Features:
# 1. External EOA Transfer Interface (_Recipient) for native GEN transfers
# 2. Native upgradability via gl.storage.Root.get().upgraders
# 3. Direct receive fallback (__receive__)
# 4. Master Treasury rescue (emergency_withdraw) & emergency_refund escape hatch
# 5. Milestone evaluation by independent GenVM AI consensus
# 6. Counterparty milestone payout & creator cancellation refund
# 7. Cross-contract dispute ruling enforcement (execute_court_ruling / enforce_court_ruling)

import genlayer as gl
from genlayer.types import *
from genlayer.storage import TreeMap, allow as allow_storage
from dataclasses import dataclass


# --- External EOA Transfer Interface -----------------------------------
@gl.evm.contract_interface
class _Recipient:
    class View:
        pass
    class Write:
        pass


# --- Persistent Types --------------------------------------------------

@allow_storage
@dataclass
class Milestone:
    name: str
    amount: u256
    criteria: str
    # "pending" | "in_review" | "approved" | "disputed" | "released" | "settled"
    status: str
    released: bool
    deliverable_text: str
    deliverable_url: str
    reasoning: str


# --- Contract -----------------------------------------------------------

class NuanceEscrow(gl.contract.Contract):
    creator: Address
    counterparty: Address
    court_contract: Address
    admin: Address
    treasury: Address
    funded_amount: u256
    milestones: TreeMap[u256, Milestone]
    milestone_count: u256
    # "active" | "cancelled" | "settled" | "emergency_refunded"
    status: str

    def __init__(
        self,
        creator: str,
        counterparty: str,
        milestone_name: str,
        milestone_amount: u256,
        milestone_criteria: str,
        court_contract: str = "",
    ):
        self.creator = Address(creator)
        self.counterparty = Address(counterparty)
        self.court_contract = Address(court_contract) if court_contract else Address("0x0000000000000000000000000000000000000000")
        self.admin = gl.message.sender_address
        self.treasury = Address("0x41648dE45Cc4D0172beCd4Db0A0A0b459C383705")
        self.funded_amount = u256(0)
        self.milestone_count = u256(0)
        self.status = "active"

        # Register admin & treasury as authorized upgraders in Root Slot
        root = gl.storage.Root.get()
        upgraders = root.upgraders.get()
        upgraders.append(gl.message.sender_address)
        if gl.message.sender_address != self.treasury:
            upgraders.append(self.treasury)

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
        self.milestone_count = self.milestone_count + u256(1)
        return index

    # --- Native Upgradability & Fallback --------------------------------

    @gl.public.write.payable
    def __receive__(self) -> None:
        """Accepts direct native GEN transfers to the contract balance without reverting."""
        pass

    @gl.public.write
    def upgrade(self, new_code: bytes) -> None:
        """Replaces contract code in place if sender is registered in root.upgraders."""
        root = gl.storage.Root.get()
        code = root.code.get()
        code.truncate()
        code.extend(new_code)

    # --- Master Treasury Rescue & Emergency Escape Hatch ----------------

    @gl.public.write
    def emergency_refund(self, recipient_override: str = "") -> None:
        """Escape hatch to immediately rescue/refund funds if stuck."""
        if gl.message.sender_address not in (self.admin, self.creator, self.treasury):
            raise gl.vm.UserError("Unauthorized: Only admin or creator can invoke emergency refund.")
        if self.funded_amount <= 0:
            raise gl.vm.UserError("No funded amount to refund.")
        refund_target = Address(recipient_override) if recipient_override else self.creator
        amount = self.funded_amount
        self.funded_amount = u256(0)
        self.status = "emergency_refunded"
        _Recipient(refund_target).emit_transfer(value=u256(amount))

    @gl.public.write
    def emergency_withdraw(self, amount: u256 = u256(0), to_address: str = "") -> None:
        """Sweeps funds to the Master Treasury or designated address in an emergency."""
        if gl.message.sender_address not in (self.treasury, self.admin):
            raise gl.vm.UserError("Only treasury or admin can invoke emergency withdraw.")
        target = Address(to_address) if to_address else self.treasury
        withdraw_amount = amount if amount > 0 else self.balance
        if withdraw_amount > self.balance:
            withdraw_amount = self.balance
        if withdraw_amount <= 0:
            raise gl.vm.UserError("No balance to withdraw.")
        if withdraw_amount > self.funded_amount:
            self.funded_amount = u256(0)
        else:
            self.funded_amount -= withdraw_amount
        _Recipient(target).emit_transfer(value=u256(withdraw_amount))

    # --- Configuration --------------------------------------------------

    @gl.public.write
    def set_court_contract(self, court_contract: str) -> None:
        if gl.message.sender_address not in (self.creator, self.admin, self.treasury):
            raise gl.vm.UserError("Only creator, admin, or treasury can set the court contract.")
        self.court_contract = Address(court_contract)

    @gl.public.write
    def add_milestone(self, name: str, amount: u256, criteria: str) -> u256:
        if gl.message.sender_address not in (self.creator, self.admin):
            raise gl.vm.UserError("Only the escrow creator or admin can add a milestone.")
        if self.status != "active":
            raise gl.vm.UserError(f"Escrow is '{self.status}' — cannot add a milestone.")
        return self._add_milestone(name, amount, criteria)

    # --- Deposit / Funding ----------------------------------------------

    @gl.public.write.payable
    def fund_escrow(self) -> None:
        """Safely credits attached GEN after sender validation."""
        if gl.message.sender_address not in (self.creator, self.admin, self.treasury):
            raise gl.vm.UserError("Only the escrow creator, admin, or treasury can fund this escrow.")
        if self.status != "active":
            raise gl.vm.UserError(f"Escrow is '{self.status}' — cannot fund it.")
        self.funded_amount = self.funded_amount + gl.message.value


    # --- Deliverable submission + AI Validator Consensus ----------------

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

        def leader_fn() -> dict:
            proof_context = "No linked proof URL was submitted."
            if deliverable_url:
                try:
                    response = gl.nondet.web.get(deliverable_url)
                    proof_context = response.body.decode("utf-8", errors="replace")[:4000]
                except Exception as exc:
                    proof_context = f"(Proof URL was unreachable or timed out: {exc})"

            prompt = f"""You are an impartial reviewer adjudicating a milestone deliverable for an escrow agreement between two independent parties.

Agreed criteria:
{criteria}

Submitted deliverable text:
{deliverable_text}

Linked proof/evidence page content:
{proof_context}

Decide whether the deliverable satisfies the agreed criteria. Respond in strict JSON:
{{
    "verdict": "APPROVE" or "REJECT",
    "reasoning": "Clear explanation of the decision"
}}
It is mandatory that you respond only using the JSON format above, nothing else."""
            return gl.nondet.exec_prompt(prompt, response_format="json")

        def validator_fn(leader_result) -> bool:
            if not isinstance(leader_result, gl.vm.Return):
                return False
            own = leader_fn()
            leader_data = leader_result.calldata
            own_verdict = str(own.get("verdict", "")).strip().upper()
            leader_verdict = str(leader_data.get("verdict", "")).strip().upper()
            return own_verdict == leader_verdict and own_verdict in ("APPROVE", "REJECT")

        verdict = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)
        normalized_verdict = str(verdict.get("verdict", "")).strip().upper()

        if normalized_verdict == "APPROVE":
            milestone.status = "approved"
        else:
            milestone.status = "disputed"
        milestone.reasoning = str(verdict.get("reasoning", ""))

    # --- Payout to Counterparty -----------------------------------------

    @gl.public.write
    def release_milestone(self, milestone_index: u256) -> None:
        """Releases milestone payout to counterparty. Callable by creator, counterparty, admin, or treasury."""
        if gl.message.sender_address not in (self.creator, self.counterparty, self.admin, self.treasury):
            raise gl.vm.UserError("Only creator, counterparty, admin, or treasury can release milestone funds.")
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

        payout = milestone.amount
        milestone.released = True
        milestone.status = "released"
        self.funded_amount -= payout
        _Recipient(self.counterparty).emit_transfer(value=u256(payout))

    # --- Refund to Creator (Cancellation) -------------------------------

    @gl.public.write
    def cancel_escrow(self) -> None:
        """Refunds unreleased funds to creator while no milestone is approved or released."""
        if gl.message.sender_address not in (self.creator, self.admin, self.treasury):
            raise gl.vm.UserError("Only the escrow creator, admin, or treasury can cancel this escrow.")
        if self.status != "active":
            raise gl.vm.UserError(f"Escrow is already '{self.status}'.")

        i: u256 = 0
        while i < self.milestone_count:
            m_status = self.milestones[i].status
            if m_status in ("approved", "released", "settled"):
                raise gl.vm.UserError(
                    "Cannot cancel — at least one milestone has already been approved, released, or settled. "
                    "Use release_milestone to pay it out, or file a dispute instead."
                )
            i += 1

        self.status = "cancelled"
        refund_amount = self.funded_amount
        self.funded_amount = 0
        if refund_amount > 0:
            _Recipient(self.creator).emit_transfer(value=u256(refund_amount))

    # --- Dispute Settlement (Cross-Contract / Admin) ---------------------

    @gl.public.write
    def execute_court_ruling(self, dispute_id: u256, milestone_index: u256 = u256(0)) -> None:
        """Inspects court ruling and executes milestone release or refund accordingly."""
        if gl.message.sender_address not in (self.creator, self.counterparty, self.admin, self.treasury):
            raise gl.vm.UserError("Unauthorized to execute court ruling.")
        zero_addr = Address("0x0000000000000000000000000000000000000000")
        if self.court_contract == zero_addr:
            raise gl.vm.UserError("Dispute court contract address is not configured.")

        court = gl.get_contract_at(self.court_contract)
        dispute_data = court.get_dispute(dispute_id)
        ruling = str(dispute_data.get("ruling", ""))
        if ruling not in ("favor_respondent", "favor_claimant"):
            raise gl.vm.UserError(f"Dispute {dispute_id} is not resolved yet (ruling: '{ruling}').")

        if ruling == "favor_respondent":
            self.enforce_court_ruling(milestone_index, u256(10000))
        else:
            self.enforce_court_ruling(milestone_index, u256(0))

    @gl.public.write
    def enforce_court_ruling(
        self, milestone_index: u256, counterparty_share_bps: u256
    ) -> None:
        """Enforces a dispute court ruling by dividing milestone collateral according to share bps (0-10000)."""
        allowed_senders = [self.admin, self.treasury]
        zero_addr = Address("0x0000000000000000000000000000000000000000")
        if self.court_contract != zero_addr:
            allowed_senders.append(self.court_contract)

        if gl.message.sender_address not in allowed_senders:
            raise gl.vm.UserError("Unauthorized: Only dispute court, admin, or treasury can enforce ruling.")

        if milestone_index not in self.milestones:
            raise gl.vm.UserError("No such milestone.")
        milestone = self.milestones[milestone_index]
        if milestone.released:
            raise gl.vm.UserError("Milestone has already been released.")
        if counterparty_share_bps > 10000:
            raise gl.vm.UserError("counterparty_share_bps must be between 0 and 10000.")

        settle_amount = milestone.amount
        if settle_amount > self.funded_amount:
            settle_amount = self.funded_amount
        if settle_amount <= 0:
            raise gl.vm.UserError("No funded amount to settle.")

        milestone.released = True
        milestone.status = "settled"
        self.funded_amount -= settle_amount

        counterparty_payout = (settle_amount * counterparty_share_bps) // 10000
        creator_payout = settle_amount - counterparty_payout

        if counterparty_payout > 0:
            _Recipient(self.counterparty).emit_transfer(value=u256(counterparty_payout))
        if creator_payout > 0:
            _Recipient(self.creator).emit_transfer(value=u256(creator_payout))

    # --- Views ----------------------------------------------------------

    @gl.public.view
    def get_escrow(self) -> dict:
        return {
            "creator": self.creator.as_hex,
            "counterparty": self.counterparty.as_hex,
            "court_contract": self.court_contract.as_hex,
            "admin": self.admin.as_hex,
            "treasury": self.treasury.as_hex,
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
