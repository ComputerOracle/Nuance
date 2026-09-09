from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast
import datetime






T = TypeVar("T", bound="DisputeEvidenceRead")



@_attrs_define
class DisputeEvidenceRead:
    """ 
        Attributes:
            created_at (datetime.datetime):
            description (str):
            dispute_id (int):
            id (int):
            submitter_address (str):
            consensus_job_id (int | None | Unset):
            link (None | str | Unset):
     """

    created_at: datetime.datetime
    description: str
    dispute_id: int
    id: int
    submitter_address: str
    consensus_job_id: int | None | Unset = UNSET
    link: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        created_at = self.created_at.isoformat()

        description = self.description

        dispute_id = self.dispute_id

        id = self.id

        submitter_address = self.submitter_address

        consensus_job_id: int | None | Unset
        if isinstance(self.consensus_job_id, Unset):
            consensus_job_id = UNSET
        else:
            consensus_job_id = self.consensus_job_id

        link: None | str | Unset
        if isinstance(self.link, Unset):
            link = UNSET
        else:
            link = self.link


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "created_at": created_at,
            "description": description,
            "dispute_id": dispute_id,
            "id": id,
            "submitter_address": submitter_address,
        })
        if consensus_job_id is not UNSET:
            field_dict["consensus_job_id"] = consensus_job_id
        if link is not UNSET:
            field_dict["link"] = link

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        created_at = datetime.datetime.fromisoformat(d.pop("created_at"))




        description = d.pop("description")

        dispute_id = d.pop("dispute_id")

        id = d.pop("id")

        submitter_address = d.pop("submitter_address")

        def _parse_consensus_job_id(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        consensus_job_id = _parse_consensus_job_id(d.pop("consensus_job_id", UNSET))


        def _parse_link(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        link = _parse_link(d.pop("link", UNSET))


        dispute_evidence_read = cls(
            created_at=created_at,
            description=description,
            dispute_id=dispute_id,
            id=id,
            submitter_address=submitter_address,
            consensus_job_id=consensus_job_id,
            link=link,
        )


        dispute_evidence_read.additional_properties = d
        return dispute_evidence_read

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
