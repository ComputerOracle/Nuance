from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="OnChainDisputeAck")



@_attrs_define
class OnChainDisputeAck:
    """ Body for POST /escrows/{id}/dispute/on-chain — the frontend
    reporting a tx hash it already got back from signing and sending
    `NuanceDisputeCourt.file_dispute` itself (see components/app/
    genlayer-write-client.ts). Unlike OnChainSubmissionAck (which updates
    an existing Milestone), this one CREATES the local Dispute row
    immediately — file_dispute assigns the dispute's id on-chain, which
    isn't known yet at ack time. See services/genlayer_indexer.py's
    resolve_pending_dispute_ids for how on_chain_dispute_id gets filled in
    once the transaction actually lands. `issue` mirrors DisputeCreate's
    own optional-with-a-server-side-default behavior, and MUST match the
    `claim_statement` argument the frontend actually passed to
    file_dispute — the indexer matches on exact text equality, not fuzzy
    matching.

        Attributes:
            tx_hash (str):
            issue (None | str | Unset):
     """

    tx_hash: str
    issue: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        tx_hash = self.tx_hash

        issue: None | str | Unset
        if isinstance(self.issue, Unset):
            issue = UNSET
        else:
            issue = self.issue


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "tx_hash": tx_hash,
        })
        if issue is not UNSET:
            field_dict["issue"] = issue

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        tx_hash = d.pop("tx_hash")

        def _parse_issue(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        issue = _parse_issue(d.pop("issue", UNSET))


        on_chain_dispute_ack = cls(
            tx_hash=tx_hash,
            issue=issue,
        )


        on_chain_dispute_ack.additional_properties = d
        return on_chain_dispute_ack

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
