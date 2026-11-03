# { "Depends": "py-genlayer:babwp9t37jw9g4j2bccgn14g6x7x9s1f7dsmh7emvz735pz4zxa0" }

import genlayer as gl
from genlayer.types import *
from genlayer.storage import TreeMap, allow as allow_storage
from dataclasses import dataclass


@allow_storage
@dataclass
class AgentStats:
    category: str
    cases_judged: u256
    wins: u256


class NuanceAgentDirectory(gl.contract.Contract):
    agents: TreeMap[Address, AgentStats]

    def __init__(self):
        pass

    @gl.public.write
    def record_result(self, agent: str, category: str, won: bool) -> None:
        addr = Address(agent)
        if addr in self.agents:
            stats = self.agents[addr]
            stats.cases_judged = stats.cases_judged + u256(1)
            if won:
                stats.wins = stats.wins + u256(1)
            stats.category = category
        else:
            self.agents[addr] = AgentStats(
                category=category,
                cases_judged=u256(1),
                wins=(u256(1) if won else u256(0)),
            )

    @gl.public.view
    def get_agent(self, agent: str) -> dict:
        addr = Address(agent)
        if addr not in self.agents:
            raise gl.vm.UserError("No such agent.")
        s = self.agents[addr]
        trust_score = (s.wins * 100) // s.cases_judged if s.cases_judged > 0 else 0
        return {
            "wallet_address": addr.as_hex,
            "category": s.category,
            "cases_judged": s.cases_judged,
            "trust_score": trust_score,
        }
