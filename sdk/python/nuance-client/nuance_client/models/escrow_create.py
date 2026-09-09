from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="EscrowCreate")



@_attrs_define
class EscrowCreate:
    """ 
        Attributes:
            counterparty_address (str):
            title (str):
            total (float | str):
            asset_symbol (str | Unset):  Default: 'GEN'.
            criteria (None | str | Unset):
     """

    counterparty_address: str
    title: str
    total: float | str
    asset_symbol: str | Unset = 'GEN'
    criteria: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        counterparty_address = self.counterparty_address

        title = self.title

        total: float | str
        total = self.total

        asset_symbol = self.asset_symbol

        criteria: None | str | Unset
        if isinstance(self.criteria, Unset):
            criteria = UNSET
        else:
            criteria = self.criteria


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "counterparty_address": counterparty_address,
            "title": title,
            "total": total,
        })
        if asset_symbol is not UNSET:
            field_dict["asset_symbol"] = asset_symbol
        if criteria is not UNSET:
            field_dict["criteria"] = criteria

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        counterparty_address = d.pop("counterparty_address")

        title = d.pop("title")

        def _parse_total(data: object) -> float | str:
            return cast(float | str, data)

        total = _parse_total(d.pop("total"))


        asset_symbol = d.pop("asset_symbol", UNSET)

        def _parse_criteria(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        criteria = _parse_criteria(d.pop("criteria", UNSET))


        escrow_create = cls(
            counterparty_address=counterparty_address,
            title=title,
            total=total,
            asset_symbol=asset_symbol,
            criteria=criteria,
        )


        escrow_create.additional_properties = d
        return escrow_create

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
