from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast
import datetime






T = TypeVar("T", bound="WebhookCreateResponse")



@_attrs_define
class WebhookCreateResponse:
    """ POST /webhooks's response — the only time `secret` is ever
    returned; see models.core.Webhook's own docstring on why this one
    (unlike an ApiKey's secret) can't just be hashed: it has to stay
    usable server-side to keep signing every future delivery. Callers
    that lose it must delete and re-register the webhook to get a new one
    (there's no "rotate secret" endpoint yet — out of scope for this
    pass).

        Attributes:
            created_at (datetime.datetime):
            event_types (list[str]):
            id (int):
            is_active (bool):
            secret (str):
            url (str):
            last_delivered_at (datetime.datetime | None | Unset):
            last_delivery_status (int | None | Unset):
     """

    created_at: datetime.datetime
    event_types: list[str]
    id: int
    is_active: bool
    secret: str
    url: str
    last_delivered_at: datetime.datetime | None | Unset = UNSET
    last_delivery_status: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        created_at = self.created_at.isoformat()

        event_types = self.event_types



        id = self.id

        is_active = self.is_active

        secret = self.secret

        url = self.url

        last_delivered_at: None | str | Unset
        if isinstance(self.last_delivered_at, Unset):
            last_delivered_at = UNSET
        elif isinstance(self.last_delivered_at, datetime.datetime):
            last_delivered_at = self.last_delivered_at.isoformat()
        else:
            last_delivered_at = self.last_delivered_at

        last_delivery_status: int | None | Unset
        if isinstance(self.last_delivery_status, Unset):
            last_delivery_status = UNSET
        else:
            last_delivery_status = self.last_delivery_status


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "created_at": created_at,
            "event_types": event_types,
            "id": id,
            "is_active": is_active,
            "secret": secret,
            "url": url,
        })
        if last_delivered_at is not UNSET:
            field_dict["last_delivered_at"] = last_delivered_at
        if last_delivery_status is not UNSET:
            field_dict["last_delivery_status"] = last_delivery_status

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        created_at = datetime.datetime.fromisoformat(d.pop("created_at"))




        event_types = cast(list[str], d.pop("event_types"))


        id = d.pop("id")

        is_active = d.pop("is_active")

        secret = d.pop("secret")

        url = d.pop("url")

        def _parse_last_delivered_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                last_delivered_at_type_0 = datetime.datetime.fromisoformat(data)



                return last_delivered_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        last_delivered_at = _parse_last_delivered_at(d.pop("last_delivered_at", UNSET))


        def _parse_last_delivery_status(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        last_delivery_status = _parse_last_delivery_status(d.pop("last_delivery_status", UNSET))


        webhook_create_response = cls(
            created_at=created_at,
            event_types=event_types,
            id=id,
            is_active=is_active,
            secret=secret,
            url=url,
            last_delivered_at=last_delivered_at,
            last_delivery_status=last_delivery_status,
        )


        webhook_create_response.additional_properties = d
        return webhook_create_response

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
