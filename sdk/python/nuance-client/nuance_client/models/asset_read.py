from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="AssetRead")



@_attrs_define
class AssetRead:
    """ 
        Attributes:
            decimals (int):
            id (int):
            is_native (bool):
            symbol (str):
            contract_address (None | str | Unset):
     """

    decimals: int
    id: int
    is_native: bool
    symbol: str
    contract_address: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        decimals = self.decimals

        id = self.id

        is_native = self.is_native

        symbol = self.symbol

        contract_address: None | str | Unset
        if isinstance(self.contract_address, Unset):
            contract_address = UNSET
        else:
            contract_address = self.contract_address


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "decimals": decimals,
            "id": id,
            "is_native": is_native,
            "symbol": symbol,
        })
        if contract_address is not UNSET:
            field_dict["contract_address"] = contract_address

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        decimals = d.pop("decimals")

        id = d.pop("id")

        is_native = d.pop("is_native")

        symbol = d.pop("symbol")

        def _parse_contract_address(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        contract_address = _parse_contract_address(d.pop("contract_address", UNSET))


        asset_read = cls(
            decimals=decimals,
            id=id,
            is_native=is_native,
            symbol=symbol,
            contract_address=contract_address,
        )


        asset_read.additional_properties = d
        return asset_read

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
