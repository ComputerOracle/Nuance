from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.status_key import StatusKey
from ..types import UNSET, Unset
from typing import cast
import datetime

if TYPE_CHECKING:
  from ..models.asset_read import AssetRead
  from ..models.milestone_read import MilestoneRead





T = TypeVar("T", bound="EscrowRead")



@_attrs_define
class EscrowRead:
    """ 
        Attributes:
            asset (AssetRead):
            counterparty_address (str):
            created_at (datetime.datetime):
            creator_address (str):
            id (int):
            status_key (StatusKey):
            title (str):
            total (str):
            cancelled_tx_hash (None | str | Unset):
            contract_address (None | str | Unset):
            funded_tx_hash (None | str | Unset):
            milestones (list[MilestoneRead] | Unset):
     """

    asset: AssetRead
    counterparty_address: str
    created_at: datetime.datetime
    creator_address: str
    id: int
    status_key: StatusKey
    title: str
    total: str
    cancelled_tx_hash: None | str | Unset = UNSET
    contract_address: None | str | Unset = UNSET
    funded_tx_hash: None | str | Unset = UNSET
    milestones: list[MilestoneRead] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.asset_read import AssetRead # noqa: PLC0415
        from ..models.milestone_read import MilestoneRead # noqa: PLC0415
        asset = self.asset.to_dict()

        counterparty_address = self.counterparty_address

        created_at = self.created_at.isoformat()

        creator_address = self.creator_address

        id = self.id

        status_key = self.status_key.value

        title = self.title

        total = self.total

        cancelled_tx_hash: None | str | Unset
        if isinstance(self.cancelled_tx_hash, Unset):
            cancelled_tx_hash = UNSET
        else:
            cancelled_tx_hash = self.cancelled_tx_hash

        contract_address: None | str | Unset
        if isinstance(self.contract_address, Unset):
            contract_address = UNSET
        else:
            contract_address = self.contract_address

        funded_tx_hash: None | str | Unset
        if isinstance(self.funded_tx_hash, Unset):
            funded_tx_hash = UNSET
        else:
            funded_tx_hash = self.funded_tx_hash

        milestones: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.milestones, Unset):
            milestones = []
            for milestones_item_data in self.milestones:
                milestones_item = milestones_item_data.to_dict()
                milestones.append(milestones_item)




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "asset": asset,
            "counterparty_address": counterparty_address,
            "created_at": created_at,
            "creator_address": creator_address,
            "id": id,
            "status_key": status_key,
            "title": title,
            "total": total,
        })
        if cancelled_tx_hash is not UNSET:
            field_dict["cancelled_tx_hash"] = cancelled_tx_hash
        if contract_address is not UNSET:
            field_dict["contract_address"] = contract_address
        if funded_tx_hash is not UNSET:
            field_dict["funded_tx_hash"] = funded_tx_hash
        if milestones is not UNSET:
            field_dict["milestones"] = milestones

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.asset_read import AssetRead # noqa: PLC0415
        from ..models.milestone_read import MilestoneRead # noqa: PLC0415
        d = dict(src_dict)
        asset = AssetRead.from_dict(d.pop("asset"))




        counterparty_address = d.pop("counterparty_address")

        created_at = datetime.datetime.fromisoformat(d.pop("created_at"))




        creator_address = d.pop("creator_address")

        id = d.pop("id")

        status_key = StatusKey(d.pop("status_key"))




        title = d.pop("title")

        total = d.pop("total")

        def _parse_cancelled_tx_hash(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cancelled_tx_hash = _parse_cancelled_tx_hash(d.pop("cancelled_tx_hash", UNSET))


        def _parse_contract_address(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        contract_address = _parse_contract_address(d.pop("contract_address", UNSET))


        def _parse_funded_tx_hash(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        funded_tx_hash = _parse_funded_tx_hash(d.pop("funded_tx_hash", UNSET))


        _milestones = d.pop("milestones", UNSET)
        milestones: list[MilestoneRead] | Unset = UNSET
        if _milestones is not UNSET:
            milestones = []
            for milestones_item_data in _milestones:
                milestones_item = MilestoneRead.from_dict(milestones_item_data)



                milestones.append(milestones_item)


        escrow_read = cls(
            asset=asset,
            counterparty_address=counterparty_address,
            created_at=created_at,
            creator_address=creator_address,
            id=id,
            status_key=status_key,
            title=title,
            total=total,
            cancelled_tx_hash=cancelled_tx_hash,
            contract_address=contract_address,
            funded_tx_hash=funded_tx_hash,
            milestones=milestones,
        )


        escrow_read.additional_properties = d
        return escrow_read

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
