from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="AgentStatRead")



@_attrs_define
class AgentStatRead:
    """ 
        Attributes:
            cases_judged (int):
            category (str):
            trust_score (int):
            wallet_address (str):
     """

    cases_judged: int
    category: str
    trust_score: int
    wallet_address: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        cases_judged = self.cases_judged

        category = self.category

        trust_score = self.trust_score

        wallet_address = self.wallet_address


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "cases_judged": cases_judged,
            "category": category,
            "trust_score": trust_score,
            "wallet_address": wallet_address,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        cases_judged = d.pop("cases_judged")

        category = d.pop("category")

        trust_score = d.pop("trust_score")

        wallet_address = d.pop("wallet_address")

        agent_stat_read = cls(
            cases_judged=cases_judged,
            category=category,
            trust_score=trust_score,
            wallet_address=wallet_address,
        )


        agent_stat_read.additional_properties = d
        return agent_stat_read

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
