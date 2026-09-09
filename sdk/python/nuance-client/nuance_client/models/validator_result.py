from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="ValidatorResult")



@_attrs_define
class ValidatorResult:
    """ 
        Attributes:
            confidence (int):
            name (str):
            reasoning (str):
            vote (str):
            provider (None | str | Unset):
     """

    confidence: int
    name: str
    reasoning: str
    vote: str
    provider: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        confidence = self.confidence

        name = self.name

        reasoning = self.reasoning

        vote = self.vote

        provider: None | str | Unset
        if isinstance(self.provider, Unset):
            provider = UNSET
        else:
            provider = self.provider


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "confidence": confidence,
            "name": name,
            "reasoning": reasoning,
            "vote": vote,
        })
        if provider is not UNSET:
            field_dict["provider"] = provider

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        confidence = d.pop("confidence")

        name = d.pop("name")

        reasoning = d.pop("reasoning")

        vote = d.pop("vote")

        def _parse_provider(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        provider = _parse_provider(d.pop("provider", UNSET))


        validator_result = cls(
            confidence=confidence,
            name=name,
            reasoning=reasoning,
            vote=vote,
            provider=provider,
        )


        validator_result.additional_properties = d
        return validator_result

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
