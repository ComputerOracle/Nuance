from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast
import datetime






T = TypeVar("T", bound="DisputeMessageRead")



@_attrs_define
class DisputeMessageRead:
    """ 
        Attributes:
            content (str):
            created_at (datetime.datetime):
            dispute_id (int):
            id (int):
            sender_address (str):
     """

    content: str
    created_at: datetime.datetime
    dispute_id: int
    id: int
    sender_address: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        content = self.content

        created_at = self.created_at.isoformat()

        dispute_id = self.dispute_id

        id = self.id

        sender_address = self.sender_address


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "content": content,
            "created_at": created_at,
            "dispute_id": dispute_id,
            "id": id,
            "sender_address": sender_address,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        content = d.pop("content")

        created_at = datetime.datetime.fromisoformat(d.pop("created_at"))




        dispute_id = d.pop("dispute_id")

        id = d.pop("id")

        sender_address = d.pop("sender_address")

        dispute_message_read = cls(
            content=content,
            created_at=created_at,
            dispute_id=dispute_id,
            id=id,
            sender_address=sender_address,
        )


        dispute_message_read.additional_properties = d
        return dispute_message_read

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
