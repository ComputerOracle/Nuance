from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast
import datetime

if TYPE_CHECKING:
  from ..models.validator_stat_read import ValidatorStatRead





T = TypeVar("T", bound="AnalyticsOverview")



@_attrs_define
class AnalyticsOverview:
    """ 
        Attributes:
            dispute_resolution_median_hours (float | None):
            generated_at (datetime.datetime):
            open_escrow_count (int):
            prediction_market_count (int):
            prediction_market_volume_gen (str):
            resolved_dispute_count (int):
            tvl_open_escrows_gen (str):
            validator_leaderboard (list[ValidatorStatRead]):
     """

    dispute_resolution_median_hours: float | None
    generated_at: datetime.datetime
    open_escrow_count: int
    prediction_market_count: int
    prediction_market_volume_gen: str
    resolved_dispute_count: int
    tvl_open_escrows_gen: str
    validator_leaderboard: list[ValidatorStatRead]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.validator_stat_read import ValidatorStatRead # noqa: PLC0415
        dispute_resolution_median_hours: float | None
        dispute_resolution_median_hours = self.dispute_resolution_median_hours

        generated_at = self.generated_at.isoformat()

        open_escrow_count = self.open_escrow_count

        prediction_market_count = self.prediction_market_count

        prediction_market_volume_gen = self.prediction_market_volume_gen

        resolved_dispute_count = self.resolved_dispute_count

        tvl_open_escrows_gen = self.tvl_open_escrows_gen

        validator_leaderboard = []
        for validator_leaderboard_item_data in self.validator_leaderboard:
            validator_leaderboard_item = validator_leaderboard_item_data.to_dict()
            validator_leaderboard.append(validator_leaderboard_item)




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "dispute_resolution_median_hours": dispute_resolution_median_hours,
            "generated_at": generated_at,
            "open_escrow_count": open_escrow_count,
            "prediction_market_count": prediction_market_count,
            "prediction_market_volume_gen": prediction_market_volume_gen,
            "resolved_dispute_count": resolved_dispute_count,
            "tvl_open_escrows_gen": tvl_open_escrows_gen,
            "validator_leaderboard": validator_leaderboard,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.validator_stat_read import ValidatorStatRead # noqa: PLC0415
        d = dict(src_dict)
        def _parse_dispute_resolution_median_hours(data: object) -> float | None:
            if data is None:
                return data
            return cast(float | None, data)

        dispute_resolution_median_hours = _parse_dispute_resolution_median_hours(d.pop("dispute_resolution_median_hours"))


        generated_at = datetime.datetime.fromisoformat(d.pop("generated_at"))




        open_escrow_count = d.pop("open_escrow_count")

        prediction_market_count = d.pop("prediction_market_count")

        prediction_market_volume_gen = d.pop("prediction_market_volume_gen")

        resolved_dispute_count = d.pop("resolved_dispute_count")

        tvl_open_escrows_gen = d.pop("tvl_open_escrows_gen")

        validator_leaderboard = []
        _validator_leaderboard = d.pop("validator_leaderboard")
        for validator_leaderboard_item_data in (_validator_leaderboard):
            validator_leaderboard_item = ValidatorStatRead.from_dict(validator_leaderboard_item_data)



            validator_leaderboard.append(validator_leaderboard_item)


        analytics_overview = cls(
            dispute_resolution_median_hours=dispute_resolution_median_hours,
            generated_at=generated_at,
            open_escrow_count=open_escrow_count,
            prediction_market_count=prediction_market_count,
            prediction_market_volume_gen=prediction_market_volume_gen,
            resolved_dispute_count=resolved_dispute_count,
            tvl_open_escrows_gen=tvl_open_escrows_gen,
            validator_leaderboard=validator_leaderboard,
        )


        analytics_overview.additional_properties = d
        return analytics_overview

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
