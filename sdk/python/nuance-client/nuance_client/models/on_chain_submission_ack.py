from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="OnChainSubmissionAck")



@_attrs_define
class OnChainSubmissionAck:
    """ Body for POST /escrows/{id}/deliverable/on-chain — the frontend
    reporting a tx hash it already got back from signing and sending
    `NuanceEscrow.submit_deliverable` itself (see components/app/
    genlayer-write-client.ts). This endpoint only remembers the hash for
    services/genlayer_indexer.py to poll; it is NOT a trust boundary for
    the verdict — status_key/deliverable text only ever change once the
    indexer reads the real result back from the contract's own get_milestone
    view. A caller reporting a bogus hash can make the indexer log a failed
    lookup; it can never fake an approval this way.

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

        on_chain_submission_ack = cls(
            tx_hash=tx_hash,
        )


        on_chain_submission_ack.additional_properties = d
        return on_chain_submission_ack

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
