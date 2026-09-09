from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast
import datetime






T = TypeVar("T", bound="DeliverableSubmissionRead")



@_attrs_define
class DeliverableSubmissionRead:
    """ 
        Attributes:
            id (int):
            milestone_id (int):
            submitted_at (datetime.datetime):
            text (str):
            wallet (str):
            consensus_job_id (int | None | Unset):
     """

    id: int
    milestone_id: int
    submitted_at: datetime.datetime
    text: str
    wallet: str
    consensus_job_id: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        id = self.id

        milestone_id = self.milestone_id

        submitted_at = self.submitted_at.isoformat()

        text = self.text

        wallet = self.wallet

        consensus_job_id: int | None | Unset
        if isinstance(self.consensus_job_id, Unset):
            consensus_job_id = UNSET
        else:
            consensus_job_id = self.consensus_job_id


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "id": id,
            "milestone_id": milestone_id,
            "submitted_at": submitted_at,
            "text": text,
            "wallet": wallet,
        })
        if consensus_job_id is not UNSET:
            field_dict["consensus_job_id"] = consensus_job_id

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        milestone_id = d.pop("milestone_id")

        submitted_at = datetime.datetime.fromisoformat(d.pop("submitted_at"))




        text = d.pop("text")

        wallet = d.pop("wallet")

        def _parse_consensus_job_id(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        consensus_job_id = _parse_consensus_job_id(d.pop("consensus_job_id", UNSET))


        deliverable_submission_read = cls(
            id=id,
            milestone_id=milestone_id,
            submitted_at=submitted_at,
            text=text,
            wallet=wallet,
            consensus_job_id=consensus_job_id,
        )


        deliverable_submission_read.additional_properties = d
        return deliverable_submission_read

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
