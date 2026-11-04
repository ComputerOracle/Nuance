# { "Depends": "py-genlayer:babwp9t37jw9g4j2bccgn14g6x7x9s1f7dsmh7emvz735pz4zxa0" }

# Nuance Prediction Market — Production Upgradable Intelligent Contract
# Grounded in official GenLayer documentation (docs.genlayer.com/developers/intelligent-contracts/)
# Features:
# 1. External EOA Transfer Interface (_Recipient) for native GEN transfers
# 2. Native upgradability via gl.storage.Root.get().upgraders
# 3. Direct receive fallback (__receive__)
# 4. Master Treasury rescue (emergency_withdraw)
# 5. Non-deterministic web fetch and LLM market resolution via GenVM consensus
# 6. Pari-mutuel winner payouts and market cancellation refunds via _Recipient

import genlayer as gl
from genlayer.types import *
from genlayer.storage import TreeMap, allow as allow_storage


# --- External EOA Transfer Interface -----------------------------------
@gl.evm.contract_interface
class _Recipient:
    class View:
        pass
    class Write:
        pass


# --- Contract -----------------------------------------------------------

class NuancePredictionMarket(gl.contract.Contract):
    question: str
    resolution_url: str
    resolution_criteria: str
    cutoff_time: str
    total_yes_stake: u256
    total_no_stake: u256
    # "OPEN" | "RESOLVED" | "CANCELLED"
    state: str
    # "" until resolved, then "YES" | "NO"
    winning_outcome: str
    admin: Address
    treasury: Address
    stakes_yes: TreeMap[Address, u256]
    stakes_no: TreeMap[Address, u256]
    claimed: TreeMap[Address, u256]

    def __init__(
        self,
        question: str,
        resolution_url: str,
        resolution_criteria: str,
        cutoff_time: str,
    ):
        self.question = question
        self.resolution_url = resolution_url
        self.resolution_criteria = resolution_criteria
        self.cutoff_time = cutoff_time
        self.total_yes_stake = u256(0)
        self.total_no_stake = u256(0)
        self.state = "OPEN"
        self.winning_outcome = ""
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

    # --- Market Betting --------------------------------------------------

    @gl.public.write.payable
    def bet(self, outcome: str) -> None:
        if self.state != "OPEN":
            raise gl.vm.UserError("This market is not open for betting.")
        side = outcome.strip().upper()
        if side not in ("YES", "NO"):
            raise gl.vm.UserError("outcome must be 'YES' or 'NO'.")
        if gl.message.value <= 0:
            raise gl.vm.UserError("Bet must include a nonzero stake.")

        sender = gl.message.sender_address
        if side == "YES":
            self.stakes_yes[sender] = self.stakes_yes.get(sender, 0) + gl.message.value
            self.total_yes_stake += gl.message.value
        else:
            self.stakes_no[sender] = self.stakes_no.get(sender, 0) + gl.message.value
            self.total_no_stake += gl.message.value

    # --- AI Market Resolution --------------------------------------------

    @gl.public.write
    def resolve_market(self) -> None:
        if self.state != "OPEN":
            raise gl.vm.UserError(f"Market cannot be resolved in '{self.state}' state.")

        question = self.question
        criteria = self.resolution_criteria
        cutoff_time = self.cutoff_time
        resolution_url = self.resolution_url

        def leader_fn() -> dict:
            try:
                response = gl.nondet.web.get(resolution_url)
                web_data = response.body.decode("utf-8", errors="replace")[:4000]
            except Exception as exc:
                web_data = f"(Resolution source URL was unreachable or timed out: {exc})"

            prompt = f"""You are resolving a binary prediction market.

Question: {question}
Resolution criteria: {criteria}
Cutoff / expected resolution time: {cutoff_time}

Source page content:
{web_data}

Decide whether the question resolves YES or NO based on the source content above. If the source doesn't yet contain enough information to resolve it, set "resolved" to false.
Respond in strict JSON:
{{
    "resolved": bool,
    "outcome": "YES" | "NO",
    "confidence": int,
    "reasoning": str
}}
It is mandatory that you respond only using the JSON format above, nothing else."""
            return gl.nondet.exec_prompt(prompt, response_format="json")

        def validator_fn(leader_result) -> bool:
            if not isinstance(leader_result, gl.vm.Return):
                return False
            own = leader_fn()
            leader_data = leader_result.calldata
            return bool(own.get("resolved")) == bool(leader_data.get("resolved")) and str(
                own.get("outcome", "")
            ).strip().upper() == str(leader_data.get("outcome", "")).strip().upper()

        verdict = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)

        if not bool(verdict.get("resolved")):
            raise gl.vm.UserError("Not resolvable yet: " + str(verdict.get("reasoning", "")))

        self.state = "RESOLVED"
        self.winning_outcome = str(verdict.get("outcome", "")).strip().upper()

    # --- Cancellation Safety ---------------------------------------------

    @gl.public.write
    def cancel_market(self, reason: str = "") -> None:
        """Allows admin or treasury to cancel market if unresolvable, enabling 100% refund of stakes."""
        if gl.message.sender_address not in (self.admin, self.treasury):
            raise gl.vm.UserError("Unauthorized: Only admin or treasury can cancel the market.")
        if self.state == "RESOLVED":
            raise gl.vm.UserError("Cannot cancel an already resolved market.")
        self.state = "CANCELLED"

    # --- Payouts & Claims ------------------------------------------------

    @gl.public.write
    def claim_winnings(self) -> None:
        """Claim payouts for winning bets or refunds if market was cancelled."""
        if self.state not in ("RESOLVED", "CANCELLED"):
            raise gl.vm.UserError("This market is neither resolved nor cancelled.")

        sender = gl.message.sender_address
        if self.claimed.get(sender, 0) != 0:
            raise gl.vm.UserError("Already claimed.")

        if self.state == "CANCELLED":
            # 100% refund of all stakes placed by this user
            refund_payout = self.stakes_yes.get(sender, 0) + self.stakes_no.get(sender, 0)
            if refund_payout == 0:
                raise gl.vm.UserError("No stake to refund.")
            self.claimed[sender] = 1
            _Recipient(sender).emit_transfer(value=u256(refund_payout))
            return

        # RESOLVED state: Pari-mutuel payout distribution
        won_yes = self.winning_outcome == "YES"
        winning_pool = self.total_yes_stake if won_yes else self.total_no_stake
        losing_pool = self.total_no_stake if won_yes else self.total_yes_stake

        if winning_pool == 0:
            # 100% of bets were placed on the losing side: return stakes to participants
            refund_stake = (self.stakes_no if won_yes else self.stakes_yes).get(sender, 0)
            if refund_stake == 0:
                raise gl.vm.UserError("No stake to refund.")
            self.claimed[sender] = 1
            _Recipient(sender).emit_transfer(value=u256(refund_stake))
            return

        my_stake = (self.stakes_yes if won_yes else self.stakes_no).get(sender, 0)
        if my_stake == 0:
            raise gl.vm.UserError("No winning stake to claim.")

        payout = my_stake
        if winning_pool > 0 and losing_pool > 0:
            payout += (my_stake * losing_pool) // winning_pool

        self.claimed[sender] = 1
        _Recipient(sender).emit_transfer(value=u256(payout))

    # --- Views ----------------------------------------------------------

    @gl.public.view
    def get_market(self) -> dict:
        return {
            "question": self.question,
            "resolution_url": self.resolution_url,
            "resolution_criteria": self.resolution_criteria,
            "cutoff_time": self.cutoff_time,
            "total_yes_stake": self.total_yes_stake,
            "total_no_stake": self.total_no_stake,
            "state": self.state,
            "winning_outcome": self.winning_outcome,
            "admin": self.admin.as_hex,
            "treasury": self.treasury.as_hex,
        }

    @gl.public.view
    def get_my_stake(self, address: str) -> dict:
        addr = Address(address)
        return {
            "yes": self.stakes_yes.get(addr, 0),
            "no": self.stakes_no.get(addr, 0),
            "claimed": bool(self.claimed.get(addr, 0)),
        }
