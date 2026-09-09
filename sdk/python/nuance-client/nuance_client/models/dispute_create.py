from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="DisputeCreate")



@_attrs_define
class DisputeCreate:
    """ Body for POST /escrows/{id}/dispute — escalating a milestone's AI
    verdict to a formal Dispute Court review. `issue` is optional: the
    "Escalate to Internet Court" button (components/app/views/
    escrow-detail-view.tsx) fires this with no form of its own, so the
    endpoint fills in a reasonable default from the milestone's most
    recent ConsensusJob reasoning when omitted — see routers/escrows.py's
    raise_dispute for that logic. Free-text override kept for any future
    caller that does want to state its own claim.

        Attributes:
            issue (None | str | Unset):
     """

    issue: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        issue: None | str | Unset
        if isinstance(self.issue, Unset):
            issue = UNSET
        else:
            issue = self.issue


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if issue is not UNSET:
            field_dict["issue"] = issue

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        def _parse_issue(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        issue = _parse_issue(d.pop("issue", UNSET))


        dispute_create = cls(
            issue=issue,
        )


        dispute_create.additional_properties = d
        return dispute_create

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
