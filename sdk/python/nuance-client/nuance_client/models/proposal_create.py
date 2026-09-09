from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset






T = TypeVar("T", bound="ProposalCreate")



@_attrs_define
class ProposalCreate:
    """ 
        Attributes:
            description (str):
            title (str):
            category (str | Unset):  Default: 'General'.
            pass_threshold (int | Unset):  Default: 50.
            quorum_threshold (int | Unset):  Default: 20.
            voting_period_days (int | Unset):  Default: 7.
     """

    description: str
    title: str
    category: str | Unset = 'General'
    pass_threshold: int | Unset = 50
    quorum_threshold: int | Unset = 20
    voting_period_days: int | Unset = 7
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        description = self.description

        title = self.title

        category = self.category

        pass_threshold = self.pass_threshold

        quorum_threshold = self.quorum_threshold

        voting_period_days = self.voting_period_days


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "description": description,
            "title": title,
        })
        if category is not UNSET:
            field_dict["category"] = category
        if pass_threshold is not UNSET:
            field_dict["pass_threshold"] = pass_threshold
        if quorum_threshold is not UNSET:
            field_dict["quorum_threshold"] = quorum_threshold
        if voting_period_days is not UNSET:
            field_dict["voting_period_days"] = voting_period_days

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        description = d.pop("description")

        title = d.pop("title")

        category = d.pop("category", UNSET)

        pass_threshold = d.pop("pass_threshold", UNSET)

        quorum_threshold = d.pop("quorum_threshold", UNSET)

        voting_period_days = d.pop("voting_period_days", UNSET)

        proposal_create = cls(
            description=description,
            title=title,
            category=category,
            pass_threshold=pass_threshold,
            quorum_threshold=quorum_threshold,
            voting_period_days=voting_period_days,
        )


        proposal_create.additional_properties = d
        return proposal_create

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
