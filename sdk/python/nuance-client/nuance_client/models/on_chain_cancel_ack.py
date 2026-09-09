from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="OnChainCancelAck")



@_attrs_define
class OnChainCancelAck:
    """ Body for POST /escrows/{id}/cancel/on-chain — the frontend
    reporting a tx hash it already got back from signing and sending a
    real NuanceEscrow.cancel_escrow transaction (components/app/
    genlayer-write-client.ts's cancelEscrowOnChain).

    Unlike OnChainFundAck/OnChainSubmissionAck, this DOES immediately
    flip status_key to StatusKey.CANCELLED — same trust level as
    raise_dispute_on_chain's own ack already uses (create the local
    record from what the caller reports, rather than waiting on an
    indexer read). Safe here for the same reason: cancel_escrow's real
    enforcement lives entirely on the contract itself — submit_
    deliverable/fund_escrow/release_milestone all check the contract's
    own `status` field directly, never this app's DB. A caller falsely
    claiming a cancellation that never actually happened on-chain can
    only produce a stale/wrong *local* status badge, never let anyone
    bypass what the contract actually enforces.

        Attributes:
            tx_hash (str):
     """

    tx_hash: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        tx_hash = self.tx_hash


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "tx_hash": tx_hash,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        tx_hash = d.pop("tx_hash")

        on_chain_cancel_ack = cls(
            tx_hash=tx_hash,
        )


        on_chain_cancel_ack.additional_properties = d
        return on_chain_cancel_ack

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
