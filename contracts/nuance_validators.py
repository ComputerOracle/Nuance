# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

# Nuance Validators — on-chain replacement for backend/app/routers/
# validators.py's GET /validators. Not part of ROADMAP.md's original
# Part 2 target layout — added 2026-09-06 on direct request, same as
# nuance_governance.py.
#
# Why this has a real write method, unlike the backend version: today,
# routers/validators.py computes accuracy by scanning every completed
# ConsensusJob's validator_results after the fact — a read-only
# aggregation over data that already exists elsewhere (predictions/
# disputes/escrows), with no state of its own. That doesn't translate to
# a contract: a GenVM contract has to be written into by *something* to
# have anything to read back. record_result() is that write — the
# natural on-chain equivalent of "a consensus job just completed, log
# what this validator persona voted and whether it matched." The real
# caller in a fully on-chain future would be NuanceEscrow/
# NuanceDisputeCourt themselves, right after run_nondet_unsafe resolves
# (a cross-contract call, gl.get_contract_at(this_address).record_result(
# ...)) — not wired up here; this deploy is the same kind of bootstrap
# instance nuance_escrow.py/nuance_prediction_market.py already are (see
# ROADMAP.md 4.4.1), proving the registry itself works and giving it a
# real address, not the full integration.
#
# Applying everything nuance_governance.py's three failed deploys found
# (see its header and ROADMAP.md 4.4.2): exactly ONE TreeMap shape in
# this contract (TreeMap[u256, ValidatorStats] — nothing else), correct
# Depends hash, bare TreeMap() in __init__, no bool as a TreeMap value.
#
# Validator identity: the three named personas from services/
# consensus.py's VALIDATOR_NAMES are fixed and known ahead of time (this
# app doesn't have dynamically-joining validator personas the way GenVM's
# own underlying validator *nodes* do), so they're seeded as ids 0/1/2 in
# __init__ rather than needing a separate name-registration write path
# (which would risk a second TreeMap shape for a name->id lookup — see
# ROADMAP.md 4.4.2's actual rule).

from genlayer import *
from dataclasses import dataclass

VALIDATOR_ALPHA = 0
VALIDATOR_BETA = 1
VALIDATOR_GAMMA = 2


@allow_storage
@dataclass
class ValidatorStats:
    name: str
    cases_judged: u256
    matched: u256  # times this validator's vote agreed with the final verdict
    is_active: bool  # plain dataclass field — proven fine (nuance_escrow.py's Milestone.released); the broken case is bool as a TreeMap *value*, not a dataclass field
    last_active_at: str  # informational only — no on-chain clock primitive, see nuance_prediction_market.py's header


class NuanceValidators(gl.Contract):
    stats: TreeMap[u256, ValidatorStats]

    def __init__(self):
        self.stats = TreeMap()
        self.stats[VALIDATOR_ALPHA] = ValidatorStats(
            name="Validator-Alpha", cases_judged=0, matched=0, is_active=False, last_active_at=""
        )
        self.stats[VALIDATOR_BETA] = ValidatorStats(
            name="Validator-Beta", cases_judged=0, matched=0, is_active=False, last_active_at=""
        )
        self.stats[VALIDATOR_GAMMA] = ValidatorStats(
            name="Validator-Gamma", cases_judged=0, matched=0, is_active=False, last_active_at=""
        )

    @gl.public.write
    def record_result(self, validator_id: u256, voted_approve: bool, verdict_approved: bool, timestamp: str) -> None:
        if validator_id not in self.stats:
            raise gl.vm.UserError("No such validator.")
        v = self.stats[validator_id]
        v.cases_judged += 1
        if voted_approve == verdict_approved:
            v.matched += 1
        v.is_active = True
        v.last_active_at = timestamp

    @gl.public.view
    def get_validator(self, validator_id: u256) -> dict:
        if validator_id not in self.stats:
            raise gl.vm.UserError("No such validator.")
        v = self.stats[validator_id]
        accuracy_pct = (v.matched * 100) // v.cases_judged if v.cases_judged > 0 else 0
        return {
            "name": v.name,
            "cases_judged": v.cases_judged,
            "accuracy_pct": accuracy_pct,
            "is_active": v.is_active,
            "last_active_at": v.last_active_at,
        }

    @gl.public.view
    def get_validator_count(self) -> u256:
        return 3
