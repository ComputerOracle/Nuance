from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="UserSettingsUpdate")



@_attrs_define
class UserSettingsUpdate:
    """ 
        Attributes:
            auto_escalate_on (bool | None | Unset):
            notify_on (bool | None | Unset):
     """

    auto_escalate_on: bool | None | Unset = UNSET
    notify_on: bool | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        auto_escalate_on: bool | None | Unset
        if isinstance(self.auto_escalate_on, Unset):
            auto_escalate_on = UNSET
        else:
            auto_escalate_on = self.auto_escalate_on

        notify_on: bool | None | Unset
        if isinstance(self.notify_on, Unset):
            notify_on = UNSET
        else:
            notify_on = self.notify_on


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if auto_escalate_on is not UNSET:
            field_dict["auto_escalate_on"] = auto_escalate_on
        if notify_on is not UNSET:
            field_dict["notify_on"] = notify_on

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        def _parse_auto_escalate_on(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        auto_escalate_on = _parse_auto_escalate_on(d.pop("auto_escalate_on", UNSET))


        def _parse_notify_on(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        notify_on = _parse_notify_on(d.pop("notify_on", UNSET))


        user_settings_update = cls(
            auto_escalate_on=auto_escalate_on,
            notify_on=notify_on,
        )


        user_settings_update.additional_properties = d
        return user_settings_update

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
