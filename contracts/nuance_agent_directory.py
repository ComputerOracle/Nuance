# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

# Nuance Agent Directory — on-chain replacement for backend/app/routers/
# agents.py's GET /agents. Not part of ROADMAP.md's original Part 2
# target layout — added 2026-09-06 on direct request, same as
# nuance_governance.py/nuance_validators.py; see nuance_validators.py's
# header for the fuller reasoning on why this needs a real write method
# (record_result) rather than being purely read-only the way the backend
# version is: a contract has to be written into by something to have
# state to read back. The real caller in a fully on-chain future is
# NuanceEscrow (a milestone's counterparty) or NuanceDisputeCourt (a
# dispute's claimant) reporting their own outcome via a cross-contract
# call right after consensus resolves — not wired up here; this is a
# bootstrap instance (ROADMAP.md 4.4.1), same as the other three.
#
# Applying everything nuance_governance.py's three failed deploys found
# (ROADMAP.md 4.4.2): exactly ONE TreeMap shape in this contract
# (TreeMap[Address, AgentStats] — the same proven shape family as
# nuance_prediction_market.py's stakes_yes/stakes_no, just with a
# dataclass value instead of a bare u256), correct Depends hash, bare
# TreeMap() in __init__, no bool as a TreeMap value.
#
# category mirrors routers/agents.py's own logic: "Milestone Delivery"
# for an escrow counterparty's outcome, "Dispute Claimant" for a dispute
# claimant's — whichever this address most recently reported, same
# "keeps whichever it touched most recently" tradeoff that file's own
# comment already accepts for a wallet with a genuine dual history.

from genlayer import *
from dataclasses import dataclass


@allow_storage
@dataclass
class AgentStats:
    category: str
    cases_judged: u256
    wins: u256


class NuanceAgentDirectory(gl.Contract):
    agents: TreeMap[Address, AgentStats]

    def __init__(self):
        self.agents = TreeMap()

    @gl.public.write
    def record_result(self, agent: str, category: str, won: bool) -> None:
        addr = Address(agent)
        if addr in self.agents:
            stats = self.agents[addr]
            stats.cases_judged += 1
            if won:
                stats.wins += 1
            stats.category = category
        else:
            self.agents[addr] = AgentStats(
                category=category,
                cases_judged=1,
                wins=(1 if won else 0),
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
