# { "Depends": "py-genlayer:babwp9t37jw9g4j2bccgn14g6x7x9s1f7dsmh7emvz735pz4zxa0" }

import genlayer as gl
from genlayer.types import *
from genlayer.storage import TreeMap, allow as allow_storage
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
    is_active: bool  # plain dataclass field
    last_active_at: str


class NuanceValidators(gl.contract.Contract):
    stats: TreeMap[u256, ValidatorStats]

    def __init__(self):
        self.stats[u256(VALIDATOR_ALPHA)] = ValidatorStats(
            name="Validator-Alpha", cases_judged=u256(0), matched=u256(0), is_active=False, last_active_at=""
        )
        self.stats[u256(VALIDATOR_BETA)] = ValidatorStats(
            name="Validator-Beta", cases_judged=u256(0), matched=u256(0), is_active=False, last_active_at=""
        )
        self.stats[u256(VALIDATOR_GAMMA)] = ValidatorStats(
            name="Validator-Gamma", cases_judged=u256(0), matched=u256(0), is_active=False, last_active_at=""
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
