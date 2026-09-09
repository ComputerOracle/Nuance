from enum import StrEnum

class ChainStatus(StrEnum):
    CANCELED = "canceled"
    DECIDED = "decided"
    FINALIZED = "finalized"
    LEGACY_OFFCHAIN = "legacy_offchain"
    PROCESSING = "processing"

    def __str__(self) -> str:
        return str(self.value)
