from enum import StrEnum

class ProposalStatus(StrEnum):
    ACTIVE = "active"
    EXECUTED = "executed"
    PASSED = "passed"
    REJECTED = "rejected"

    def __str__(self) -> str:
        return str(self.value)
