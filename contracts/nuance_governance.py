# { "Depends": "py-genlayer:babwp9t37jw9g4j2bccgn14g6x7x9s1f7dsmh7emvz735pz4zxa0" }

# Nuance Governance — Production Upgradable Intelligent Contract
# Grounded in official GenLayer documentation (docs.genlayer.com/developers/intelligent-contracts/)
# Features:
# 1. External EOA Transfer Interface (_Recipient) for native GEN transfers
# 2. Native upgradability via gl.storage.Root.get().upgraders
# 3. Direct receive fallback (__receive__)
# 4. Master Treasury rescue (emergency_withdraw)
# 5. Staked GEN voting with unvote/retract refund via _Recipient
# 6. Single-TreeMap polymorphic architecture compliant with GenVM memory layout

import genlayer as gl
from genlayer.types import *
from genlayer.storage import TreeMap, allow as allow_storage
from dataclasses import dataclass

KIND_PROPOSAL = "proposal"
KIND_VOTE = "vote"

CHOICE_NONE = ""
CHOICE_FOR = "for"
CHOICE_AGAINST = "against"
CHOICE_ABSTAIN = "abstain"


# --- External EOA Transfer Interface -----------------------------------
@gl.evm.contract_interface
class _Recipient:
    class View:
        pass
    class Write:
        pass


@allow_storage
@dataclass
class Record:
    """One polymorphic shape backing both proposals and vote records."""
    kind: str  # KIND_PROPOSAL | KIND_VOTE
    proposal_id: u256
    title: str
    description: str
    category: str
    proposer: Address
    status: str
    end_time: str
    quorum_threshold: u256
    pass_threshold: u256
    total_for: u256
    total_against: u256
    total_abstain: u256
    stake: u256


class NuanceGovernance(gl.contract.Contract):
    entries: TreeMap[u256, Record]
    proposal_count: u256
    admin: Address
    treasury: Address

    def __init__(self):
        self.proposal_count = u256(0)
        self.admin = gl.message.sender_address
        self.treasury = Address("0x41648dE45Cc4D0172beCd4Db0A0A0b459C383705")

        # Register admin & treasury as authorized upgraders in Root Slot
        root = gl.storage.Root.get()
        upgraders = root.upgraders.get()
        upgraders.append(gl.message.sender_address)
        if gl.message.sender_address != self.treasury:
            upgraders.append(self.treasury)

    # --- Direct Receive Fallback -----------------------------------------

    @gl.public.write.payable
    def __receive__(self) -> None:
        """Accepts direct GEN transfers so incoming funds are safely stored."""
        pass

    # --- Native Upgradability --------------------------------------------

    @gl.public.write
    def upgrade(self, new_code: bytes) -> None:
        """Upgrades contract code in-place. Authorized for admin or treasury."""
        if gl.message.sender_address not in (self.admin, self.treasury):
            raise gl.vm.UserError("Unauthorized: Only admin or treasury can upgrade.")
        root = gl.storage.Root.get()
        code = root.code.get()
        code.truncate()
        code.extend(new_code)

    # --- Master Treasury Rescue ------------------------------------------

    @gl.public.write
    def emergency_withdraw(self, amount: u256 = u256(0), to_address: str = "") -> None:
        """Emergency sweep of native GEN back to Master Treasury or specified address."""
        if gl.message.sender_address not in (self.admin, self.treasury):
            raise gl.vm.UserError("Unauthorized: Only admin or treasury can execute emergency withdraw.")

        recipient = Address(to_address) if to_address else self.treasury
        current_balance = self.balance
        withdraw_amount = current_balance if amount == 0 else amount
        if withdraw_amount > current_balance:
            withdraw_amount = current_balance
        if withdraw_amount > 0:
            _Recipient(recipient).emit_transfer(value=u256(withdraw_amount))

    # --- Internal Helpers ------------------------------------------------

    def _vote_key(self, proposal_id: u256, voter: Address) -> u256:
        return (proposal_id << 160) | int(voter.as_hex, 16)

    def _get_proposal(self, proposal_id: u256) -> Record:
        if proposal_id not in self.entries:
            raise gl.vm.UserError("No such proposal.")
        entry = self.entries[proposal_id]
        if entry.kind != KIND_PROPOSAL:
            raise gl.vm.UserError("No such proposal.")
        return entry

    # --- Proposals & Voting ----------------------------------------------

    @gl.public.write
    def create_proposal(
        self,
        title: str,
        description: str,
        category: str,
        end_time: str,
        quorum_threshold: u256,
        pass_threshold: u256,
    ) -> u256:
        if not title:
            raise gl.vm.UserError("title can't be blank.")
        if pass_threshold > 100:
            raise gl.vm.UserError("pass_threshold must be between 0 and 100.")

        proposal_id = self.proposal_count
        self.entries[proposal_id] = Record(
            kind=KIND_PROPOSAL,
            proposal_id=proposal_id,
            title=title,
            description=description,
            category=category,
            proposer=gl.message.sender_address,
            status="active",
            end_time=end_time,
            quorum_threshold=quorum_threshold,
            pass_threshold=pass_threshold,
            total_for=0,
            total_against=0,
            total_abstain=0,
            stake=0,
        )
        self.proposal_count += 1
        return proposal_id

    @gl.public.write.payable
    def cast_vote(self, proposal_id: u256, choice: str) -> None:
        proposal = self._get_proposal(proposal_id)
        if proposal.status != "active":
            raise gl.vm.UserError(f"Proposal is '{proposal.status}', not open for voting.")

        choice_norm = choice.strip().lower()
        if choice_norm not in (CHOICE_FOR, CHOICE_AGAINST, CHOICE_ABSTAIN):
            raise gl.vm.UserError("choice must be 'for', 'against', or 'abstain'.")
        if gl.message.value <= 0:
            raise gl.vm.UserError("A vote must stake a nonzero amount of GEN.")

        voter = gl.message.sender_address
        key = self._vote_key(proposal_id, voter)
        if key in self.entries and self.entries[key].status != CHOICE_NONE:
            raise gl.vm.UserError("You already have an active vote on this proposal — call retract_vote first.")

        stake = gl.message.value
        self.entries[key] = Record(
            kind=KIND_VOTE,
            proposal_id=proposal_id,
            title="",
            description="",
            category="",
            proposer=voter,
            status=choice_norm,
            end_time="",
            quorum_threshold=0,
            pass_threshold=0,
            total_for=0,
            total_against=0,
            total_abstain=0,
            stake=stake,
        )

        if choice_norm == CHOICE_FOR:
            proposal.total_for += stake
        elif choice_norm == CHOICE_AGAINST:
            proposal.total_against += stake
        elif choice_norm == CHOICE_ABSTAIN:
            proposal.total_abstain += stake

    @gl.public.write
    def retract_vote(self, proposal_id: u256) -> None:
        proposal = self._get_proposal(proposal_id)
        voter = gl.message.sender_address
        key = self._vote_key(proposal_id, voter)
        if key not in self.entries or self.entries[key].status == CHOICE_NONE:
            raise gl.vm.UserError("You have no active vote on this proposal.")

        record = self.entries[key]
        choice = record.status
        stake = record.stake

        if choice == CHOICE_FOR:
            proposal.total_for -= stake
        elif choice == CHOICE_AGAINST:
            proposal.total_against -= stake
        elif choice == CHOICE_ABSTAIN:
            proposal.total_abstain -= stake

        record.status = CHOICE_NONE
        record.stake = 0

        _Recipient(voter).emit_transfer(value=u256(stake))

    @gl.public.write
    def finalize_proposal(self, proposal_id: u256) -> None:
        proposal = self._get_proposal(proposal_id)
        if proposal.status != "active":
            raise gl.vm.UserError(f"Already finalized as '{proposal.status}'.")

        turnout = proposal.total_for + proposal.total_against + proposal.total_abstain
        quorum_met = turnout >= proposal.quorum_threshold

        decided = proposal.total_for + proposal.total_against
        passed = quorum_met and decided > 0 and (proposal.total_for * 100 >= proposal.pass_threshold * decided)

        proposal.status = "passed" if passed else "rejected"

    # --- Views ----------------------------------------------------------

    @gl.public.view
    def get_proposal(self, proposal_id: u256) -> dict:
        p = self._get_proposal(proposal_id)
        return {
            "proposal_id": p.proposal_id,
            "title": p.title,
            "description": p.description,
            "category": p.category,
            "proposer": p.proposer.as_hex,
            "status": p.status,
            "end_time": p.end_time,
            "quorum_threshold": p.quorum_threshold,
            "pass_threshold": p.pass_threshold,
            "total_for": p.total_for,
            "total_against": p.total_against,
            "total_abstain": p.total_abstain,
        }

    @gl.public.view
    def get_proposal_count(self) -> u256:
        return self.proposal_count

    @gl.public.view
    def get_vote(self, proposal_id: u256, voter: str) -> str:
        key = self._vote_key(proposal_id, Address(voter))
        if key not in self.entries:
            return "none"
        status = self.entries[key].status
        return status if status != CHOICE_NONE else "none"

    @gl.public.view
    def get_vote_stake(self, proposal_id: u256, voter: str) -> u256:
        key = self._vote_key(proposal_id, Address(voter))
        if key not in self.entries:
            return 0
        return self.entries[key].stake

    @gl.public.view
    def get_governance_info(self) -> dict:
        return {
            "admin": self.admin.as_hex,
            "treasury": self.treasury.as_hex,
            "proposal_count": self.proposal_count,
        }
