from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.chain_status import ChainStatus
from ..types import UNSET, Unset
from typing import cast
import datetime

if TYPE_CHECKING:
  from ..models.prediction_position_read import PredictionPositionRead





T = TypeVar("T", bound="PredictionRead")



@_attrs_define
class PredictionRead:
    """ 
        Attributes:
            category (str):
            created_at (datetime.datetime):
            description (str):
            id (int):
            resolution_date (datetime.datetime):
            status_key (str):
            title (str):
            volume (int):
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
            contract_address (None | str | Unset):
            outcome (None | str | Unset):
            positions (list[PredictionPositionRead] | Unset):
            resolution_reasoning (None | str | Unset):
            resolution_source_url (None | str | Unset):
            resolution_trigger_tx_hash (None | str | Unset):
            resolved_at (datetime.datetime | None | Unset):
     """

    category: str
    created_at: datetime.datetime
    description: str
    id: int
    resolution_date: datetime.datetime
    status_key: str
    title: str
    volume: int
    chain_status: ChainStatus | Unset = UNSET
    contract_address: None | str | Unset = UNSET
    outcome: None | str | Unset = UNSET
    positions: list[PredictionPositionRead] | Unset = UNSET
    resolution_reasoning: None | str | Unset = UNSET
    resolution_source_url: None | str | Unset = UNSET
    resolution_trigger_tx_hash: None | str | Unset = UNSET
    resolved_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.prediction_position_read import PredictionPositionRead # noqa: PLC0415
        category = self.category

        created_at = self.created_at.isoformat()

        description = self.description

        id = self.id

        resolution_date = self.resolution_date.isoformat()

        status_key = self.status_key

        title = self.title

        volume = self.volume

        chain_status: str | Unset = UNSET
        if not isinstance(self.chain_status, Unset):
            chain_status = self.chain_status.value


        contract_address: None | str | Unset
        if isinstance(self.contract_address, Unset):
            contract_address = UNSET
        else:
            contract_address = self.contract_address

        outcome: None | str | Unset
        if isinstance(self.outcome, Unset):
            outcome = UNSET
        else:
            outcome = self.outcome

        positions: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.positions, Unset):
            positions = []
            for positions_item_data in self.positions:
                positions_item = positions_item_data.to_dict()
                positions.append(positions_item)



        resolution_reasoning: None | str | Unset
        if isinstance(self.resolution_reasoning, Unset):
            resolution_reasoning = UNSET
        else:
            resolution_reasoning = self.resolution_reasoning

        resolution_source_url: None | str | Unset
        if isinstance(self.resolution_source_url, Unset):
            resolution_source_url = UNSET
        else:
            resolution_source_url = self.resolution_source_url

        resolution_trigger_tx_hash: None | str | Unset
        if isinstance(self.resolution_trigger_tx_hash, Unset):
            resolution_trigger_tx_hash = UNSET
        else:
            resolution_trigger_tx_hash = self.resolution_trigger_tx_hash

        resolved_at: None | str | Unset
        if isinstance(self.resolved_at, Unset):
            resolved_at = UNSET
        elif isinstance(self.resolved_at, datetime.datetime):
            resolved_at = self.resolved_at.isoformat()
        else:
            resolved_at = self.resolved_at


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "category": category,
            "created_at": created_at,
            "description": description,
            "id": id,
            "resolution_date": resolution_date,
            "status_key": status_key,
            "title": title,
            "volume": volume,
        })
        if chain_status is not UNSET:
            field_dict["chain_status"] = chain_status
        if contract_address is not UNSET:
            field_dict["contract_address"] = contract_address
        if outcome is not UNSET:
            field_dict["outcome"] = outcome
        if positions is not UNSET:
            field_dict["positions"] = positions
        if resolution_reasoning is not UNSET:
            field_dict["resolution_reasoning"] = resolution_reasoning
        if resolution_source_url is not UNSET:
            field_dict["resolution_source_url"] = resolution_source_url
        if resolution_trigger_tx_hash is not UNSET:
            field_dict["resolution_trigger_tx_hash"] = resolution_trigger_tx_hash
        if resolved_at is not UNSET:
            field_dict["resolved_at"] = resolved_at

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.prediction_position_read import PredictionPositionRead # noqa: PLC0415
        d = dict(src_dict)
        category = d.pop("category")

        created_at = datetime.datetime.fromisoformat(d.pop("created_at"))




        description = d.pop("description")

        id = d.pop("id")

        resolution_date = datetime.datetime.fromisoformat(d.pop("resolution_date"))




        status_key = d.pop("status_key")

        title = d.pop("title")

        volume = d.pop("volume")

        _chain_status = d.pop("chain_status", UNSET)
        chain_status: ChainStatus | Unset
        if isinstance(_chain_status,  Unset):
            chain_status = UNSET
        else:
            chain_status = ChainStatus(_chain_status)




        def _parse_contract_address(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        contract_address = _parse_contract_address(d.pop("contract_address", UNSET))


        def _parse_outcome(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        outcome = _parse_outcome(d.pop("outcome", UNSET))


        _positions = d.pop("positions", UNSET)
        positions: list[PredictionPositionRead] | Unset = UNSET
        if _positions is not UNSET:
            positions = []
            for positions_item_data in _positions:
                positions_item = PredictionPositionRead.from_dict(positions_item_data)



                positions.append(positions_item)


        def _parse_resolution_reasoning(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        resolution_reasoning = _parse_resolution_reasoning(d.pop("resolution_reasoning", UNSET))


        def _parse_resolution_source_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        resolution_source_url = _parse_resolution_source_url(d.pop("resolution_source_url", UNSET))


        def _parse_resolution_trigger_tx_hash(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        resolution_trigger_tx_hash = _parse_resolution_trigger_tx_hash(d.pop("resolution_trigger_tx_hash", UNSET))


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


        prediction_read = cls(
            category=category,
            created_at=created_at,
            description=description,
            id=id,
            resolution_date=resolution_date,
            status_key=status_key,
            title=title,
            volume=volume,
            chain_status=chain_status,
            contract_address=contract_address,
            outcome=outcome,
            positions=positions,
            resolution_reasoning=resolution_reasoning,
            resolution_source_url=resolution_source_url,
            resolution_trigger_tx_hash=resolution_trigger_tx_hash,
            resolved_at=resolved_at,
        )


        prediction_read.additional_properties = d
        return prediction_read

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
