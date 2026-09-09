from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="OnChainBetAck")



@_attrs_define
class OnChainBetAck:
    """ Body for POST /predictions/{id}/bet/on-chain — the frontend
    reporting a tx hash it already got back from signing and sending
    NuancePredictionMarket.bet itself (see components/app/
    genlayer-write-client.ts's betOnChain). Unlike a regular write ack,
    this ALSO carries side/amount: the real stake already lives in the
    contract's own storage, but this app still mirrors it into a
    PredictionPosition row immediately (same reasoning
    OnChainSubmissionAck's docstring gives for milestones) so the existing
    "my positions" UI keeps working without waiting on an indexer cycle
    that doesn't sync individual bettors' stakes at all today.

        Attributes:
            amount (int):
            side (str):
            tx_hash (str):
     """

    amount: int
    side: str
    tx_hash: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        amount = self.amount

        side = self.side

        tx_hash = self.tx_hash


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "amount": amount,
            "side": side,
            "tx_hash": tx_hash,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        amount = d.pop("amount")

        side = d.pop("side")

        tx_hash = d.pop("tx_hash")

        on_chain_bet_ack = cls(
            amount=amount,
            side=side,
            tx_hash=tx_hash,
        )


        on_chain_bet_ack.additional_properties = d
        return on_chain_bet_ack

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
