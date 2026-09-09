from enum import StrEnum

class StatusKey(StrEnum):
    APPROVED = "approved"
    CANCELLED = "cancelled"
    DISPUTED = "disputed"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    PENDING = "pending"
    REJECTED = "rejected"

    def __str__(self) -> str:
        return str(self.value)
