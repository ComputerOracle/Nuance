from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast
import datetime






T = TypeVar("T", bound="ApiKeyIssueResponse")



@_attrs_define
class ApiKeyIssueResponse:
    """ POST /auth/api-keys's response — the ONLY time `api_key` (the full
    "nuance_live_<key_id>_<secret>" credential) is ever returned. See
    models.core.ApiKey's own docstring on why: only a hash of the secret
    half is stored, so there's no "look it up again later" path — losing
    this means issuing a new key.

        Attributes:
            api_key (str):
            created_at (datetime.datetime):
            id (int):
            key_id (str):
            scopes (list[str]):
            label (None | str | Unset):
     """

    api_key: str
    created_at: datetime.datetime
    id: int
    key_id: str
    scopes: list[str]
    label: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        api_key = self.api_key

        created_at = self.created_at.isoformat()

        id = self.id

        key_id = self.key_id

        scopes = self.scopes



        label: None | str | Unset
        if isinstance(self.label, Unset):
            label = UNSET
        else:
            label = self.label


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "api_key": api_key,
            "created_at": created_at,
            "id": id,
            "key_id": key_id,
            "scopes": scopes,
        })
        if label is not UNSET:
            field_dict["label"] = label

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        api_key = d.pop("api_key")

        created_at = datetime.datetime.fromisoformat(d.pop("created_at"))




        id = d.pop("id")

        key_id = d.pop("key_id")

        scopes = cast(list[str], d.pop("scopes"))


        def _parse_label(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        label = _parse_label(d.pop("label", UNSET))


        api_key_issue_response = cls(
            api_key=api_key,
            created_at=created_at,
            id=id,
            key_id=key_id,
            scopes=scopes,
            label=label,
        )


        api_key_issue_response.additional_properties = d
        return api_key_issue_response

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
