# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

# Nuance Governance — on-chain replacement for backend/app/routers/
# governance.py's proposals + votes. Not part of ROADMAP.md's original
# Part 2 target layout (that only ever named Escrow/DisputeCourt/
# PredictionMarket) — added 2026-09-06 on direct request, after the other
# three were already live on Bradbury.
#
# THE REAL CONSTRAINT THIS FILE'S OWN FAILED DEPLOYS FOUND (empirical,
# confirmed 2026-09-06 via three live Bradbury attempts + debugTraceTransaction,
# not documented anywhere I could find): a single contract can only have
# ONE distinct TreeMap[K, V] type shape. Every field declared as a TreeMap
# must share the exact same (K, V) parameterization — a second, differently-
# shaped TreeMap field throws
# `AssertionError: Is right the same storage type? TreeMap <- TreeMap`
# the instant its bare `TreeMap()` is assigned in __init__, regardless of
# whether that second shape is independently fine in some other contract.
# This explains every TreeMap failure across this codebase, not just the
# TreeMap[Address, bool] one nuance_prediction_market.py's header found:
#   - nuance_prediction_market.py: TreeMap[Address, u256] x2 (same shape,
#     both fine) + TreeMap[Address, bool] (a SECOND shape — broke).
#   - This file, attempt 1: TreeMap[u256, Proposal] (fine, establishes the
#     shape) + TreeMap[u256, u256] (a second shape, primitive this time,
#     not a dataclass — still broke, same assertion).
#   - This file, attempt 2: TreeMap[u256, Proposal] + TreeMap[u256,
#     VoteRecord] — a second *dataclass*, structurally the closest
#     possible shape to the first (same key type, still a dataclass
#     value) — still broke. Confirms it's the literal type identity of
#     the (K, V) pair being compared, not "dataclass vs primitive" or any
#     coarser category.
#   - nuance_dispute_court.py / nuance_escrow.py: exactly one TreeMap
#     field each — nothing to conflict with, both fine.
#
# The fix here: exactly ONE TreeMap for the whole contract,
# TreeMap[u256, Record], where Record is a single polymorphic dataclass
# used for both proposals and vote records, disambiguated by `kind`.
# Proposals are keyed by their small sequential proposal_id; vote records
# are keyed by a bit-packed (proposal_id, voter_address) composite that's
# always astronomically larger than any real proposal_id, so the two
# families of keys can never collide in one shared TreeMap:
#     vote_key = (proposal_id << 160) | int(voter_address.as_hex, 16)
# A vote record repurposes `status` to hold the choice string ("for" |
# "against" | "abstain") and `proposer` to hold the voter's own address —
# odd field reuse, but the alternative (a second contract-wide type, or a
# second TreeMap) is exactly what's confirmed broken above.
#
# Two further departures from the backend's own semantics, both because
# there is no on-chain equivalent to lean on — flagged rather than faked:
#
# 1. Quorum here is an ABSOLUTE vote-count threshold (quorum_threshold
#    votes must be cast), not a percentage of "every wallet that's ever
#    signed in" the way routers/governance.py's _total_eligible_voters
#    computes it. There is no on-chain wallet registry for this contract
#    to count against — GenVM has no equivalent of the backend's Users
#    table. An absolute threshold is a legitimate, common on-chain
#    governance pattern in its own right, not a workaround pretending to
#    be the percentage version.
#
# 2. end_time is informational only, exactly like nuance_prediction_
#    market.py's cutoff_time — there is no documented on-chain clock
#    primitive (same gap that file's header already found and flagged).
#    finalize_proposal() cannot enforce "voting period has ended"
#    on-chain; it can only be called once by design (status flips off
#    "active" on first finalize), so at least it can't be re-finalized
#    into a different outcome by calling it twice.

from genlayer import *
from dataclasses import dataclass

KIND_PROPOSAL = "proposal"
KIND_VOTE = "vote"

CHOICE_NONE = ""
CHOICE_FOR = "for"
CHOICE_AGAINST = "against"
CHOICE_ABSTAIN = "abstain"


@allow_storage
@dataclass
class Record:
    """One polymorphic shape backing both proposals and vote records — see
    module header for why this file can't just use two differently-shaped
    TreeMap fields. `kind` says which of the two this entry actually is;
    the other fields are reused/ignored accordingly (see the field-level
    comments)."""

    kind: str  # KIND_PROPOSAL | KIND_VOTE
    proposal_id: u256  # the proposal this entry is about, either way
    title: str  # proposal only
    description: str  # proposal only
    category: str  # proposal only
    # proposal: the wallet that created it. vote: the wallet that cast it.
    proposer: Address
    # proposal: "active" | "passed" | "rejected".
    # vote: the choice itself — CHOICE_FOR | CHOICE_AGAINST | CHOICE_ABSTAIN.
    status: str
    end_time: str  # proposal only — informational, see module header
    quorum_threshold: u256  # proposal only — absolute vote count, see module header
    pass_threshold: u256  # proposal only — percentage (0-100) of decided votes
    total_for: u256  # proposal only
    total_against: u256  # proposal only
    total_abstain: u256  # proposal only


class NuanceGovernance(gl.Contract):
    entries: TreeMap[u256, Record]
    proposal_count: u256

    def __init__(self):
        self.entries = TreeMap()
        self.proposal_count = 0

    def _vote_key(self, proposal_id: u256, voter: Address) -> u256:
        # High 96 bits: proposal_id. Low 160 bits: the voter's raw address
        # value. Always > any real proposal_id (which starts at 0 and
        # counts up one at a time), so proposal keys and vote keys never
        # collide in the shared `entries` TreeMap.
        return (proposal_id << 160) | int(voter.as_hex, 16)

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
        )
        self.proposal_count += 1
        return proposal_id

    def _get_proposal(self, proposal_id: u256) -> Record:
        if proposal_id not in self.entries:
            raise gl.vm.UserError("No such proposal.")
        proposal = self.entries[proposal_id]
        if proposal.kind != KIND_PROPOSAL:
            raise gl.vm.UserError("No such proposal.")
        return proposal

    @gl.public.write
    def cast_vote(self, proposal_id: u256, choice: str) -> None:
        proposal = self._get_proposal(proposal_id)
        if proposal.status != "active":
            raise gl.vm.UserError(f"Voting is closed — proposal is '{proposal.status}'.")

        normalized = choice.strip().lower()
        if normalized not in (CHOICE_FOR, CHOICE_AGAINST, CHOICE_ABSTAIN):
            raise gl.vm.UserError("choice must be 'for', 'against', or 'abstain'.")

        voter = gl.message.sender_address
        key = self._vote_key(proposal_id, voter)
        previous = self.entries[key].status if key in self.entries else CHOICE_NONE

        # Back the previous choice's weight out before adding the new
        # one in — flip, not stack. Every wallet's ballot is weight 1,
        # same DEFAULT_VOTING_POWER placeholder routers/governance.py
        # uses until real GEN-stake-weighted voting exists.
        if previous == CHOICE_FOR:
            proposal.total_for -= 1
        elif previous == CHOICE_AGAINST:
            proposal.total_against -= 1
        elif previous == CHOICE_ABSTAIN:
            proposal.total_abstain -= 1

        if normalized == CHOICE_FOR:
            proposal.total_for += 1
        elif normalized == CHOICE_AGAINST:
            proposal.total_against += 1
        else:
            proposal.total_abstain += 1

        if key in self.entries:
            self.entries[key].status = normalized
        else:
            self.entries[key] = Record(
                kind=KIND_VOTE,
                proposal_id=proposal_id,
                title="",
                description="",
                category="",
                proposer=voter,
                status=normalized,
                end_time="",
                quorum_threshold=0,
                pass_threshold=0,
                total_for=0,
                total_against=0,
                total_abstain=0,
            )

    @gl.public.write
    def finalize_proposal(self, proposal_id: u256) -> None:
        """Idempotent by construction: status only ever leaves "active"
        once, here — a second call on an already-finalized proposal is a
        no-op error rather than a chance to flip the outcome by
        re-evaluating against changed votes (voting is closed anyway once
        this has run once). See module header on why the real
        "voting period has ended" time gate isn't enforced here."""
        proposal = self._get_proposal(proposal_id)
        if proposal.status != "active":
            raise gl.vm.UserError(f"Already finalized as '{proposal.status}'.")

        turnout = proposal.total_for + proposal.total_against + proposal.total_abstain
        quorum_met = turnout >= proposal.quorum_threshold

        decided = proposal.total_for + proposal.total_against
        # Integer cross-multiplication instead of division — avoids
        # float/Decimal entirely, which GenVM's storage/consensus layer
        # has no proven track record with in this codebase yet.
        passed = quorum_met and decided > 0 and (proposal.total_for * 100 >= proposal.pass_threshold * decided)

        proposal.status = "passed" if passed else "rejected"

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
        return self.entries[key].status
