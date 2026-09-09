from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="OnChainEvidenceAck")



@_attrs_define
class OnChainEvidenceAck:
    """ Body for POST /disputes/{id}/evidence/on-chain — the frontend
    reporting a tx hash it already got back from signing and sending a
    real NuanceDisputeCourt.add_evidence transaction (components/app/
    genlayer-write-client.ts's addEvidenceOnChain). Unlike the off-chain
    submit_evidence, this does NOT queue a ConsensusJob — the real
    judgment happens via adjudicate_dispute on the contract itself
    (triggered automatically by services/genlayer_indexer.py, or
    manually). `evidence_url` is required (unlike the off-chain path's
    optional `link`) because the contract's own add_evidence only ever
    takes a URL — there's nowhere for free-text-only evidence to go
    on-chain (see that contract method's own docstring).

        Attributes:
            evidence_url (str):
            tx_hash (str):
     """

    evidence_url: str
    tx_hash: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        evidence_url = self.evidence_url

        tx_hash = self.tx_hash


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "evidence_url": evidence_url,
            "tx_hash": tx_hash,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        evidence_url = d.pop("evidence_url")

        tx_hash = d.pop("tx_hash")

        on_chain_evidence_ack = cls(
            evidence_url=evidence_url,
            tx_hash=tx_hash,
        )


        on_chain_evidence_ack.additional_properties = d
        return on_chain_evidence_ack

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
