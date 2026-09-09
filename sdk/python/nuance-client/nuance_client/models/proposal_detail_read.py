from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.proposal_status import ProposalStatus
from ..models.vote_choice import VoteChoice
from ..types import UNSET, Unset
from typing import cast
import datetime

if TYPE_CHECKING:
  from ..models.vote_read import VoteRead





T = TypeVar("T", bound="ProposalDetailRead")



@_attrs_define
class ProposalDetailRead:
    """ 
        Attributes:
            abstain_pct (float):
            against_pct (float):
            category (str):
            created_at (datetime.datetime):
            description (str):
            end_time (datetime.datetime):
            for_pct (float):
            id (int):
            pass_threshold (int):
            proposer_address (str):
            quorum_met (bool):
            quorum_threshold (int):
            start_time (datetime.datetime):
            status (ProposalStatus): A governance proposal's lifecycle. finalize() (routers/governance.py)
                is the only thing that moves ACTIVE -> PASSED/REJECTED; EXECUTED is
                reserved for a future action that actually applies a passed proposal's
                effect (see ROADMAP.md Part 1) and isn't set by anything yet.
            title (str):
            total_abstain (int):
            total_against (int):
            total_for (int):
            turnout_pct (float):
            executed_at (datetime.datetime | None | Unset):
            executed_by (None | str | Unset):
            user_vote (None | Unset | VoteChoice):
            votes (list[VoteRead] | Unset):
     """

    abstain_pct: float
    against_pct: float
    category: str
    created_at: datetime.datetime
    description: str
    end_time: datetime.datetime
    for_pct: float
    id: int
    pass_threshold: int
    proposer_address: str
    quorum_met: bool
    quorum_threshold: int
    start_time: datetime.datetime
    status: ProposalStatus
    title: str
    total_abstain: int
    total_against: int
    total_for: int
    turnout_pct: float
    executed_at: datetime.datetime | None | Unset = UNSET
    executed_by: None | str | Unset = UNSET
    user_vote: None | Unset | VoteChoice = UNSET
    votes: list[VoteRead] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.vote_read import VoteRead # noqa: PLC0415
        abstain_pct = self.abstain_pct

        against_pct = self.against_pct

        category = self.category

        created_at = self.created_at.isoformat()

        description = self.description

        end_time = self.end_time.isoformat()

        for_pct = self.for_pct

        id = self.id

        pass_threshold = self.pass_threshold

        proposer_address = self.proposer_address

        quorum_met = self.quorum_met

        quorum_threshold = self.quorum_threshold

        start_time = self.start_time.isoformat()

        status = self.status.value

        title = self.title

        total_abstain = self.total_abstain

        total_against = self.total_against

        total_for = self.total_for

        turnout_pct = self.turnout_pct

        executed_at: None | str | Unset
        if isinstance(self.executed_at, Unset):
            executed_at = UNSET
        elif isinstance(self.executed_at, datetime.datetime):
            executed_at = self.executed_at.isoformat()
        else:
            executed_at = self.executed_at

        executed_by: None | str | Unset
        if isinstance(self.executed_by, Unset):
            executed_by = UNSET
        else:
            executed_by = self.executed_by

        user_vote: None | str | Unset
        if isinstance(self.user_vote, Unset):
            user_vote = UNSET
        elif isinstance(self.user_vote, VoteChoice):
            user_vote = self.user_vote.value
        else:
            user_vote = self.user_vote

        votes: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.votes, Unset):
            votes = []
            for votes_item_data in self.votes:
                votes_item = votes_item_data.to_dict()
                votes.append(votes_item)




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "abstain_pct": abstain_pct,
            "against_pct": against_pct,
            "category": category,
            "created_at": created_at,
            "description": description,
            "end_time": end_time,
            "for_pct": for_pct,
            "id": id,
            "pass_threshold": pass_threshold,
            "proposer_address": proposer_address,
            "quorum_met": quorum_met,
            "quorum_threshold": quorum_threshold,
            "start_time": start_time,
            "status": status,
            "title": title,
            "total_abstain": total_abstain,
            "total_against": total_against,
            "total_for": total_for,
            "turnout_pct": turnout_pct,
        })
        if executed_at is not UNSET:
            field_dict["executed_at"] = executed_at
        if executed_by is not UNSET:
            field_dict["executed_by"] = executed_by
        if user_vote is not UNSET:
            field_dict["user_vote"] = user_vote
        if votes is not UNSET:
            field_dict["votes"] = votes

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.vote_read import VoteRead # noqa: PLC0415
        d = dict(src_dict)
        abstain_pct = d.pop("abstain_pct")

        against_pct = d.pop("against_pct")

        category = d.pop("category")

        created_at = datetime.datetime.fromisoformat(d.pop("created_at"))




        description = d.pop("description")

        end_time = datetime.datetime.fromisoformat(d.pop("end_time"))




        for_pct = d.pop("for_pct")

        id = d.pop("id")

        pass_threshold = d.pop("pass_threshold")

        proposer_address = d.pop("proposer_address")

        quorum_met = d.pop("quorum_met")

        quorum_threshold = d.pop("quorum_threshold")

        start_time = datetime.datetime.fromisoformat(d.pop("start_time"))




        status = ProposalStatus(d.pop("status"))




        title = d.pop("title")

        total_abstain = d.pop("total_abstain")

        total_against = d.pop("total_against")

        total_for = d.pop("total_for")

        turnout_pct = d.pop("turnout_pct")

        def _parse_executed_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                executed_at_type_0 = datetime.datetime.fromisoformat(data)



                return executed_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        executed_at = _parse_executed_at(d.pop("executed_at", UNSET))


        def _parse_executed_by(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        executed_by = _parse_executed_by(d.pop("executed_by", UNSET))


        def _parse_user_vote(data: object) -> None | Unset | VoteChoice:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                user_vote_type_0 = VoteChoice(data)



                return user_vote_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | VoteChoice, data)

        user_vote = _parse_user_vote(d.pop("user_vote", UNSET))


        _votes = d.pop("votes", UNSET)
        votes: list[VoteRead] | Unset = UNSET
        if _votes is not UNSET:
            votes = []
            for votes_item_data in _votes:
                votes_item = VoteRead.from_dict(votes_item_data)



                votes.append(votes_item)


        proposal_detail_read = cls(
            abstain_pct=abstain_pct,
            against_pct=against_pct,
            category=category,
            created_at=created_at,
            description=description,
            end_time=end_time,
            for_pct=for_pct,
            id=id,
            pass_threshold=pass_threshold,
            proposer_address=proposer_address,
            quorum_met=quorum_met,
            quorum_threshold=quorum_threshold,
            start_time=start_time,
            status=status,
            title=title,
            total_abstain=total_abstain,
            total_against=total_against,
            total_for=total_for,
            turnout_pct=turnout_pct,
            executed_at=executed_at,
            executed_by=executed_by,
            user_vote=user_vote,
            votes=votes,
        )


        proposal_detail_read.additional_properties = d
        return proposal_detail_read

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
