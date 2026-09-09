from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast
import datetime






T = TypeVar("T", bound="AgentCaseRead")



@_attrs_define
class AgentCaseRead:
    """ One judged case in an agent's real history — the "transaction
    drill-down" ROADMAP.md Part 4's Real Agent Directory item calls for.
    `AgentStatRead` above was already computed from real `ConsensusJob`
    rows (not seed data — see routers/agents.py's own docstring); what
    was actually missing was any way to see *which* cases a trust score
    was built from. `escrow_id` is always present (a dispute's own
    `escrow_id`, or the milestone's) so the frontend can link straight
    back to the real escrow/dispute detail view.

        Attributes:
            consensus_job_id (int):
            escrow_id (int):
            subject_id (int):
            subject_type (str):
            title (str):
            completed_at (datetime.datetime | None | Unset):
            dispute_id (int | None | Unset):
            verdict_approved (bool | None | Unset):
            verdict_confidence (int | None | Unset):
            verdict_label (None | str | Unset):
            verdict_reasoning (None | str | Unset):
     """

    consensus_job_id: int
    escrow_id: int
    subject_id: int
    subject_type: str
    title: str
    completed_at: datetime.datetime | None | Unset = UNSET
    dispute_id: int | None | Unset = UNSET
    verdict_approved: bool | None | Unset = UNSET
    verdict_confidence: int | None | Unset = UNSET
    verdict_label: None | str | Unset = UNSET
    verdict_reasoning: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        consensus_job_id = self.consensus_job_id

        escrow_id = self.escrow_id

        subject_id = self.subject_id

        subject_type = self.subject_type

        title = self.title

        completed_at: None | str | Unset
        if isinstance(self.completed_at, Unset):
            completed_at = UNSET
        elif isinstance(self.completed_at, datetime.datetime):
            completed_at = self.completed_at.isoformat()
        else:
            completed_at = self.completed_at

        dispute_id: int | None | Unset
        if isinstance(self.dispute_id, Unset):
            dispute_id = UNSET
        else:
            dispute_id = self.dispute_id

        verdict_approved: bool | None | Unset
        if isinstance(self.verdict_approved, Unset):
            verdict_approved = UNSET
        else:
            verdict_approved = self.verdict_approved

        verdict_confidence: int | None | Unset
        if isinstance(self.verdict_confidence, Unset):
            verdict_confidence = UNSET
        else:
            verdict_confidence = self.verdict_confidence

        verdict_label: None | str | Unset
        if isinstance(self.verdict_label, Unset):
            verdict_label = UNSET
        else:
            verdict_label = self.verdict_label

        verdict_reasoning: None | str | Unset
        if isinstance(self.verdict_reasoning, Unset):
            verdict_reasoning = UNSET
        else:
            verdict_reasoning = self.verdict_reasoning


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "consensus_job_id": consensus_job_id,
            "escrow_id": escrow_id,
            "subject_id": subject_id,
            "subject_type": subject_type,
            "title": title,
        })
        if completed_at is not UNSET:
            field_dict["completed_at"] = completed_at
        if dispute_id is not UNSET:
            field_dict["dispute_id"] = dispute_id
        if verdict_approved is not UNSET:
            field_dict["verdict_approved"] = verdict_approved
        if verdict_confidence is not UNSET:
            field_dict["verdict_confidence"] = verdict_confidence
        if verdict_label is not UNSET:
            field_dict["verdict_label"] = verdict_label
        if verdict_reasoning is not UNSET:
            field_dict["verdict_reasoning"] = verdict_reasoning

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        consensus_job_id = d.pop("consensus_job_id")

        escrow_id = d.pop("escrow_id")

        subject_id = d.pop("subject_id")

        subject_type = d.pop("subject_type")

        title = d.pop("title")

        def _parse_completed_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                completed_at_type_0 = datetime.datetime.fromisoformat(data)



                return completed_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        completed_at = _parse_completed_at(d.pop("completed_at", UNSET))


        def _parse_dispute_id(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        dispute_id = _parse_dispute_id(d.pop("dispute_id", UNSET))


        def _parse_verdict_approved(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        verdict_approved = _parse_verdict_approved(d.pop("verdict_approved", UNSET))


        def _parse_verdict_confidence(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        verdict_confidence = _parse_verdict_confidence(d.pop("verdict_confidence", UNSET))


        def _parse_verdict_label(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        verdict_label = _parse_verdict_label(d.pop("verdict_label", UNSET))


        def _parse_verdict_reasoning(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        verdict_reasoning = _parse_verdict_reasoning(d.pop("verdict_reasoning", UNSET))


        agent_case_read = cls(
            consensus_job_id=consensus_job_id,
            escrow_id=escrow_id,
            subject_id=subject_id,
            subject_type=subject_type,
            title=title,
            completed_at=completed_at,
            dispute_id=dispute_id,
            verdict_approved=verdict_approved,
            verdict_confidence=verdict_confidence,
            verdict_label=verdict_label,
            verdict_reasoning=verdict_reasoning,
        )


        agent_case_read.additional_properties = d
        return agent_case_read

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
