from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.consensus_verdict import ConsensusVerdict
  from ..models.validator_result import ValidatorResult





T = TypeVar("T", bound="ConsensusStatus")



@_attrs_define
class ConsensusStatus:
    """ 
        Attributes:
            stage (int):
            validator_results (list[ValidatorResult] | None | Unset):
            verdict (ConsensusVerdict | None | Unset):
     """

    stage: int
    validator_results: list[ValidatorResult] | None | Unset = UNSET
    verdict: ConsensusVerdict | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.consensus_verdict import ConsensusVerdict # noqa: PLC0415
        from ..models.validator_result import ValidatorResult # noqa: PLC0415
        stage = self.stage

        validator_results: list[dict[str, Any]] | None | Unset
        if isinstance(self.validator_results, Unset):
            validator_results = UNSET
        elif isinstance(self.validator_results, list):
            validator_results = []
            for validator_results_type_0_item_data in self.validator_results:
                validator_results_type_0_item = validator_results_type_0_item_data.to_dict()
                validator_results.append(validator_results_type_0_item)


        else:
            validator_results = self.validator_results

        verdict: dict[str, Any] | None | Unset
        if isinstance(self.verdict, Unset):
            verdict = UNSET
        elif isinstance(self.verdict, ConsensusVerdict):
            verdict = self.verdict.to_dict()
        else:
            verdict = self.verdict


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "stage": stage,
        })
        if validator_results is not UNSET:
            field_dict["validator_results"] = validator_results
        if verdict is not UNSET:
            field_dict["verdict"] = verdict

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.consensus_verdict import ConsensusVerdict # noqa: PLC0415
        from ..models.validator_result import ValidatorResult # noqa: PLC0415
        d = dict(src_dict)
        stage = d.pop("stage")

        def _parse_validator_results(data: object) -> list[ValidatorResult] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                validator_results_type_0 = []
                _validator_results_type_0 = data
                for validator_results_type_0_item_data in (_validator_results_type_0):
                    validator_results_type_0_item = ValidatorResult.from_dict(validator_results_type_0_item_data)



                    validator_results_type_0.append(validator_results_type_0_item)

                return validator_results_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[ValidatorResult] | None | Unset, data)

        validator_results = _parse_validator_results(d.pop("validator_results", UNSET))


        def _parse_verdict(data: object) -> ConsensusVerdict | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                verdict_type_0 = ConsensusVerdict.from_dict(data)



                return verdict_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ConsensusVerdict | None | Unset, data)

        verdict = _parse_verdict(d.pop("verdict", UNSET))


        consensus_status = cls(
            stage=stage,
            validator_results=validator_results,
            verdict=verdict,
        )


        consensus_status.additional_properties = d
        return consensus_status

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
