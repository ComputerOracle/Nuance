from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast
import datetime

if TYPE_CHECKING:
  from ..models.user_settings_read import UserSettingsRead





T = TypeVar("T", bound="UserRead")



@_attrs_define
class UserRead:
    """ 
        Attributes:
            created_at (datetime.datetime):
            wallet_address (str):
            display_name (None | str | Unset):
            settings (None | Unset | UserSettingsRead):
     """

    created_at: datetime.datetime
    wallet_address: str
    display_name: None | str | Unset = UNSET
    settings: None | Unset | UserSettingsRead = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.user_settings_read import UserSettingsRead # noqa: PLC0415
        created_at = self.created_at.isoformat()

        wallet_address = self.wallet_address

        display_name: None | str | Unset
        if isinstance(self.display_name, Unset):
            display_name = UNSET
        else:
            display_name = self.display_name

        settings: dict[str, Any] | None | Unset
        if isinstance(self.settings, Unset):
            settings = UNSET
        elif isinstance(self.settings, UserSettingsRead):
            settings = self.settings.to_dict()
        else:
            settings = self.settings


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "created_at": created_at,
            "wallet_address": wallet_address,
        })
        if display_name is not UNSET:
            field_dict["display_name"] = display_name
        if settings is not UNSET:
            field_dict["settings"] = settings

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.user_settings_read import UserSettingsRead # noqa: PLC0415
        d = dict(src_dict)
        created_at = datetime.datetime.fromisoformat(d.pop("created_at"))




        wallet_address = d.pop("wallet_address")

        def _parse_display_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        display_name = _parse_display_name(d.pop("display_name", UNSET))


        def _parse_settings(data: object) -> None | Unset | UserSettingsRead:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                settings_type_0 = UserSettingsRead.from_dict(data)



                return settings_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UserSettingsRead, data)

        settings = _parse_settings(d.pop("settings", UNSET))


        user_read = cls(
            created_at=created_at,
            wallet_address=wallet_address,
            display_name=display_name,
            settings=settings,
        )


        user_read.additional_properties = d
        return user_read

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
