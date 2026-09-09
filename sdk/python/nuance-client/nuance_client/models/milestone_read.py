from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.chain_status import ChainStatus
from ..models.status_key import StatusKey
from ..types import UNSET, Unset
from typing import cast
import datetime






T = TypeVar("T", bound="MilestoneRead")



@_attrs_define
class MilestoneRead:
    """ 
        Attributes:
            amount (str):
            criteria (str):
            id (int):
            name (str):
            order_index (int):
            status_key (StatusKey):
            chain_status (ChainStatus | Unset): Mirrors lib/chain-status.ts's ChainStatus (LEGACY_OFFCHAIN +
                ChainStatusBucket) value-for-value — same reason StatusKey above
                mirrors types.ts: that file already collapses GenLayer's real 14-value
                TransactionStatus into this 4-bucket + legacy shape (via the SDK's own
                isDecidedState(), not a hand-copied list — see that file's header),
                and duplicating a *different* vocabulary here would let the two
                drift. scripts/genlayer-read.ts computes the bucket (it has
                genlayer-js loaded); services/genlayer_indexer.py only ever writes
                one of these five strings into a row's chain_status column.

                Every Milestone/Dispute/Prediction row defaults to LEGACY_OFFCHAIN and
                stays there until it's actually linked on-chain (Escrow.contract_address
                / Prediction.contract_address / Dispute.on_chain_dispute_id set) — see
                ROADMAP.md 4.5's deferred "add this together with the actual cutover"
                note; this is that column, added once there's a real indexer to drive
                it rather than speculatively ahead of one.
            on_chain_index (int | None | Unset):
            on_chain_tx_hash (None | str | Unset):
            reasoning (None | str | Unset):
            released_at (datetime.datetime | None | Unset):
     """

    amount: str
    criteria: str
    id: int
    name: str
    order_index: int
    status_key: StatusKey
    chain_status: ChainStatus | Unset = UNSET
    on_chain_index: int | None | Unset = UNSET
    on_chain_tx_hash: None | str | Unset = UNSET
    reasoning: None | str | Unset = UNSET
    released_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        amount = self.amount

        criteria = self.criteria

        id = self.id

        name = self.name

        order_index = self.order_index

        status_key = self.status_key.value

        chain_status: str | Unset = UNSET
        if not isinstance(self.chain_status, Unset):
            chain_status = self.chain_status.value


        on_chain_index: int | None | Unset
        if isinstance(self.on_chain_index, Unset):
            on_chain_index = UNSET
        else:
            on_chain_index = self.on_chain_index

        on_chain_tx_hash: None | str | Unset
        if isinstance(self.on_chain_tx_hash, Unset):
            on_chain_tx_hash = UNSET
        else:
            on_chain_tx_hash = self.on_chain_tx_hash

        reasoning: None | str | Unset
        if isinstance(self.reasoning, Unset):
            reasoning = UNSET
        else:
            reasoning = self.reasoning

        released_at: None | str | Unset
        if isinstance(self.released_at, Unset):
            released_at = UNSET
        elif isinstance(self.released_at, datetime.datetime):
            released_at = self.released_at.isoformat()
        else:
            released_at = self.released_at


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "amount": amount,
            "criteria": criteria,
            "id": id,
            "name": name,
            "order_index": order_index,
            "status_key": status_key,
        })
        if chain_status is not UNSET:
            field_dict["chain_status"] = chain_status
        if on_chain_index is not UNSET:
            field_dict["on_chain_index"] = on_chain_index
        if on_chain_tx_hash is not UNSET:
            field_dict["on_chain_tx_hash"] = on_chain_tx_hash
        if reasoning is not UNSET:
            field_dict["reasoning"] = reasoning
        if released_at is not UNSET:
            field_dict["released_at"] = released_at

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        amount = d.pop("amount")

        criteria = d.pop("criteria")

        id = d.pop("id")

        name = d.pop("name")

        order_index = d.pop("order_index")

        status_key = StatusKey(d.pop("status_key"))




        _chain_status = d.pop("chain_status", UNSET)
        chain_status: ChainStatus | Unset
        if isinstance(_chain_status,  Unset):
            chain_status = UNSET
        else:
            chain_status = ChainStatus(_chain_status)




        def _parse_on_chain_index(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        on_chain_index = _parse_on_chain_index(d.pop("on_chain_index", UNSET))


        def _parse_on_chain_tx_hash(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        on_chain_tx_hash = _parse_on_chain_tx_hash(d.pop("on_chain_tx_hash", UNSET))


        def _parse_reasoning(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        reasoning = _parse_reasoning(d.pop("reasoning", UNSET))


        def _parse_released_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                released_at_type_0 = datetime.datetime.fromisoformat(data)



                return released_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        released_at = _parse_released_at(d.pop("released_at", UNSET))


        milestone_read = cls(
            amount=amount,
            criteria=criteria,
            id=id,
            name=name,
            order_index=order_index,
            status_key=status_key,
            chain_status=chain_status,
            on_chain_index=on_chain_index,
            on_chain_tx_hash=on_chain_tx_hash,
            reasoning=reasoning,
            released_at=released_at,
        )


        milestone_read.additional_properties = d
        return milestone_read

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
