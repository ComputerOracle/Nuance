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

if TYPE_CHECKING:
  from ..models.dispute_evidence_read import DisputeEvidenceRead
  from ..models.dispute_message_read import DisputeMessageRead





T = TypeVar("T", bound="DisputeRead")



@_attrs_define
class DisputeRead:
    """ 
        Attributes:
            created_at (datetime.datetime):
            escrow_id (int):
            id (int):
            issue (str):
            opened_by_address (str):
            status_key (StatusKey):
            adjudication_tx_hash (None | str | Unset):
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
            enforced_by (None | str | Unset):
            evidence (list[DisputeEvidenceRead] | Unset):
            messages (list[DisputeMessageRead] | Unset):
            milestone_id (int | None | Unset):
            on_chain_dispute_id (int | None | Unset):
            on_chain_tx_hash (None | str | Unset):
            resolved_at (datetime.datetime | None | Unset):
            ruling (None | str | Unset):
     """

    created_at: datetime.datetime
    escrow_id: int
    id: int
    issue: str
    opened_by_address: str
    status_key: StatusKey
    adjudication_tx_hash: None | str | Unset = UNSET
    chain_status: ChainStatus | Unset = UNSET
    enforced_by: None | str | Unset = UNSET
    evidence: list[DisputeEvidenceRead] | Unset = UNSET
    messages: list[DisputeMessageRead] | Unset = UNSET
    milestone_id: int | None | Unset = UNSET
    on_chain_dispute_id: int | None | Unset = UNSET
    on_chain_tx_hash: None | str | Unset = UNSET
    resolved_at: datetime.datetime | None | Unset = UNSET
    ruling: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.dispute_evidence_read import DisputeEvidenceRead # noqa: PLC0415
        from ..models.dispute_message_read import DisputeMessageRead # noqa: PLC0415
        created_at = self.created_at.isoformat()

        escrow_id = self.escrow_id

        id = self.id

        issue = self.issue

        opened_by_address = self.opened_by_address

        status_key = self.status_key.value

        adjudication_tx_hash: None | str | Unset
        if isinstance(self.adjudication_tx_hash, Unset):
            adjudication_tx_hash = UNSET
        else:
            adjudication_tx_hash = self.adjudication_tx_hash

        chain_status: str | Unset = UNSET
        if not isinstance(self.chain_status, Unset):
            chain_status = self.chain_status.value


        enforced_by: None | str | Unset
        if isinstance(self.enforced_by, Unset):
            enforced_by = UNSET
        else:
            enforced_by = self.enforced_by

        evidence: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.evidence, Unset):
            evidence = []
            for evidence_item_data in self.evidence:
                evidence_item = evidence_item_data.to_dict()
                evidence.append(evidence_item)



        messages: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.messages, Unset):
            messages = []
            for messages_item_data in self.messages:
                messages_item = messages_item_data.to_dict()
                messages.append(messages_item)



        milestone_id: int | None | Unset
        if isinstance(self.milestone_id, Unset):
            milestone_id = UNSET
        else:
            milestone_id = self.milestone_id

        on_chain_dispute_id: int | None | Unset
        if isinstance(self.on_chain_dispute_id, Unset):
            on_chain_dispute_id = UNSET
        else:
            on_chain_dispute_id = self.on_chain_dispute_id

        on_chain_tx_hash: None | str | Unset
        if isinstance(self.on_chain_tx_hash, Unset):
            on_chain_tx_hash = UNSET
        else:
            on_chain_tx_hash = self.on_chain_tx_hash

        resolved_at: None | str | Unset
        if isinstance(self.resolved_at, Unset):
            resolved_at = UNSET
        elif isinstance(self.resolved_at, datetime.datetime):
            resolved_at = self.resolved_at.isoformat()
        else:
            resolved_at = self.resolved_at

        ruling: None | str | Unset
        if isinstance(self.ruling, Unset):
            ruling = UNSET
        else:
            ruling = self.ruling


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "created_at": created_at,
            "escrow_id": escrow_id,
            "id": id,
            "issue": issue,
            "opened_by_address": opened_by_address,
            "status_key": status_key,
        })
        if adjudication_tx_hash is not UNSET:
            field_dict["adjudication_tx_hash"] = adjudication_tx_hash
        if chain_status is not UNSET:
            field_dict["chain_status"] = chain_status
        if enforced_by is not UNSET:
            field_dict["enforced_by"] = enforced_by
        if evidence is not UNSET:
            field_dict["evidence"] = evidence
        if messages is not UNSET:
            field_dict["messages"] = messages
        if milestone_id is not UNSET:
            field_dict["milestone_id"] = milestone_id
        if on_chain_dispute_id is not UNSET:
            field_dict["on_chain_dispute_id"] = on_chain_dispute_id
        if on_chain_tx_hash is not UNSET:
            field_dict["on_chain_tx_hash"] = on_chain_tx_hash
        if resolved_at is not UNSET:
            field_dict["resolved_at"] = resolved_at
        if ruling is not UNSET:
            field_dict["ruling"] = ruling

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.dispute_evidence_read import DisputeEvidenceRead # noqa: PLC0415
        from ..models.dispute_message_read import DisputeMessageRead # noqa: PLC0415
        d = dict(src_dict)
        created_at = datetime.datetime.fromisoformat(d.pop("created_at"))




        escrow_id = d.pop("escrow_id")

        id = d.pop("id")

        issue = d.pop("issue")

        opened_by_address = d.pop("opened_by_address")

        status_key = StatusKey(d.pop("status_key"))




        def _parse_adjudication_tx_hash(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        adjudication_tx_hash = _parse_adjudication_tx_hash(d.pop("adjudication_tx_hash", UNSET))


        _chain_status = d.pop("chain_status", UNSET)
        chain_status: ChainStatus | Unset
        if isinstance(_chain_status,  Unset):
            chain_status = UNSET
        else:
            chain_status = ChainStatus(_chain_status)




        def _parse_enforced_by(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        enforced_by = _parse_enforced_by(d.pop("enforced_by", UNSET))


        _evidence = d.pop("evidence", UNSET)
        evidence: list[DisputeEvidenceRead] | Unset = UNSET
        if _evidence is not UNSET:
            evidence = []
            for evidence_item_data in _evidence:
                evidence_item = DisputeEvidenceRead.from_dict(evidence_item_data)



                evidence.append(evidence_item)


        _messages = d.pop("messages", UNSET)
        messages: list[DisputeMessageRead] | Unset = UNSET
        if _messages is not UNSET:
            messages = []
            for messages_item_data in _messages:
                messages_item = DisputeMessageRead.from_dict(messages_item_data)



                messages.append(messages_item)


        def _parse_milestone_id(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        milestone_id = _parse_milestone_id(d.pop("milestone_id", UNSET))


        def _parse_on_chain_dispute_id(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        on_chain_dispute_id = _parse_on_chain_dispute_id(d.pop("on_chain_dispute_id", UNSET))


        def _parse_on_chain_tx_hash(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        on_chain_tx_hash = _parse_on_chain_tx_hash(d.pop("on_chain_tx_hash", UNSET))


        def _parse_resolved_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                resolved_at_type_0 = datetime.datetime.fromisoformat(data)



                return resolved_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        resolved_at = _parse_resolved_at(d.pop("resolved_at", UNSET))


        def _parse_ruling(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ruling = _parse_ruling(d.pop("ruling", UNSET))


        dispute_read = cls(
            created_at=created_at,
            escrow_id=escrow_id,
            id=id,
            issue=issue,
            opened_by_address=opened_by_address,
            status_key=status_key,
            adjudication_tx_hash=adjudication_tx_hash,
            chain_status=chain_status,
            enforced_by=enforced_by,
            evidence=evidence,
            messages=messages,
            milestone_id=milestone_id,
            on_chain_dispute_id=on_chain_dispute_id,
            on_chain_tx_hash=on_chain_tx_hash,
            resolved_at=resolved_at,
            ruling=ruling,
        )


        dispute_read.additional_properties = d
        return dispute_read

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
