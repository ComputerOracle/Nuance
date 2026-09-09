from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast
import datetime






T = TypeVar("T", bound="ValidatorStatRead")



@_attrs_define
class ValidatorStatRead:
    """ 
        Attributes:
            accuracy_pct (float):
            cases_judged (int):
            is_active (bool):
            name (str):
            last_active_at (datetime.datetime | None | Unset):
            last_provider (None | str | Unset):
     """

    accuracy_pct: float
    cases_judged: int
    is_active: bool
    name: str
    last_active_at: datetime.datetime | None | Unset = UNSET
    last_provider: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        accuracy_pct = self.accuracy_pct

        cases_judged = self.cases_judged

        is_active = self.is_active

        name = self.name

        last_active_at: None | str | Unset
        if isinstance(self.last_active_at, Unset):
            last_active_at = UNSET
        elif isinstance(self.last_active_at, datetime.datetime):
            last_active_at = self.last_active_at.isoformat()
        else:
            last_active_at = self.last_active_at

        last_provider: None | str | Unset
        if isinstance(self.last_provider, Unset):
            last_provider = UNSET
        else:
            last_provider = self.last_provider


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "accuracy_pct": accuracy_pct,
            "cases_judged": cases_judged,
            "is_active": is_active,
            "name": name,
        })
        if last_active_at is not UNSET:
            field_dict["last_active_at"] = last_active_at
        if last_provider is not UNSET:
            field_dict["last_provider"] = last_provider

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        accuracy_pct = d.pop("accuracy_pct")

        cases_judged = d.pop("cases_judged")

        is_active = d.pop("is_active")

        name = d.pop("name")

        def _parse_last_active_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                last_active_at_type_0 = datetime.datetime.fromisoformat(data)



                return last_active_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        last_active_at = _parse_last_active_at(d.pop("last_active_at", UNSET))


        def _parse_last_provider(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        last_provider = _parse_last_provider(d.pop("last_provider", UNSET))


        validator_stat_read = cls(
            accuracy_pct=accuracy_pct,
            cases_judged=cases_judged,
            is_active=is_active,
            name=name,
            last_active_at=last_active_at,
            last_provider=last_provider,
        )


        validator_stat_read.additional_properties = d
        return validator_stat_read

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
