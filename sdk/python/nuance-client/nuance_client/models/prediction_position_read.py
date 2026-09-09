from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast
import datetime






T = TypeVar("T", bound="PredictionPositionRead")



@_attrs_define
class PredictionPositionRead:
    """ 
        Attributes:
            amount (int):
            created_at (datetime.datetime):
            id (int):
            prediction_id (int):
            side (str):
            wallet_address (str):
            payout (float | None | Unset):  Default: 0.0.
            status (str | Unset):  Default: 'PENDING'.
     """

    amount: int
    created_at: datetime.datetime
    id: int
    prediction_id: int
    side: str
    wallet_address: str
    payout: float | None | Unset = 0.0
    status: str | Unset = 'PENDING'
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        amount = self.amount

        created_at = self.created_at.isoformat()

        id = self.id

        prediction_id = self.prediction_id

        side = self.side

        wallet_address = self.wallet_address

        payout: float | None | Unset
        if isinstance(self.payout, Unset):
            payout = UNSET
        else:
            payout = self.payout

        status = self.status


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "amount": amount,
            "created_at": created_at,
            "id": id,
            "prediction_id": prediction_id,
            "side": side,
            "wallet_address": wallet_address,
        })
        if payout is not UNSET:
            field_dict["payout"] = payout
        if status is not UNSET:
            field_dict["status"] = status

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        amount = d.pop("amount")

        created_at = datetime.datetime.fromisoformat(d.pop("created_at"))




        id = d.pop("id")

        prediction_id = d.pop("prediction_id")

        side = d.pop("side")

        wallet_address = d.pop("wallet_address")

        def _parse_payout(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        payout = _parse_payout(d.pop("payout", UNSET))


        status = d.pop("status", UNSET)

        prediction_position_read = cls(
            amount=amount,
            created_at=created_at,
            id=id,
            prediction_id=prediction_id,
            side=side,
            wallet_address=wallet_address,
            payout=payout,
            status=status,
        )


        prediction_position_read.additional_properties = d
        return prediction_position_read

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
