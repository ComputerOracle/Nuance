from enum import StrEnum

class VoteChoice(StrEnum):
    ABSTAIN = "abstain"
    AGAINST = "against"
    FOR = "for"

    def __str__(self) -> str:
        return str(self.value)
