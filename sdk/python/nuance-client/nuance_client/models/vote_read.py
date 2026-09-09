from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.vote_choice import VoteChoice
from typing import cast
import datetime






T = TypeVar("T", bound="VoteRead")



@_attrs_define
class VoteRead:
    """ 
        Attributes:
            choice (VoteChoice):
            created_at (datetime.datetime):
            id (int):
            proposal_id (int):
            updated_at (datetime.datetime):
            voter_address (str):
            voting_power (int):
     """

    choice: VoteChoice
    created_at: datetime.datetime
    id: int
    proposal_id: int
    updated_at: datetime.datetime
    voter_address: str
    voting_power: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        choice = self.choice.value

        created_at = self.created_at.isoformat()

        id = self.id

        proposal_id = self.proposal_id

        updated_at = self.updated_at.isoformat()

        voter_address = self.voter_address

        voting_power = self.voting_power


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "choice": choice,
            "created_at": created_at,
            "id": id,
            "proposal_id": proposal_id,
            "updated_at": updated_at,
            "voter_address": voter_address,
            "voting_power": voting_power,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        choice = VoteChoice(d.pop("choice"))




        created_at = datetime.datetime.fromisoformat(d.pop("created_at"))




        id = d.pop("id")

        proposal_id = d.pop("proposal_id")

        updated_at = datetime.datetime.fromisoformat(d.pop("updated_at"))




        voter_address = d.pop("voter_address")

        voting_power = d.pop("voting_power")

        vote_read = cls(
            choice=choice,
            created_at=created_at,
            id=id,
            proposal_id=proposal_id,
            updated_at=updated_at,
            voter_address=voter_address,
            voting_power=voting_power,
        )


        vote_read.additional_properties = d
        return vote_read

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
