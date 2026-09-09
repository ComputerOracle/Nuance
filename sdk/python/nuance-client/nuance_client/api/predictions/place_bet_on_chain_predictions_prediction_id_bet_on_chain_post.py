from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.on_chain_bet_ack import OnChainBetAck
from ...models.prediction_read import PredictionRead
from typing import cast



def _get_kwargs(
    prediction_id: int,
    *,
    body: OnChainBetAck,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/predictions/{prediction_id}/bet/on-chain".format(prediction_id=quote(str(prediction_id), safe=""),),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | PredictionRead | None:
    if response.status_code == 201:
        response_201 = PredictionRead.from_dict(response.json())



        return response_201

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | PredictionRead]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    prediction_id: int,
    *,
    client: AuthenticatedClient,
    body: OnChainBetAck,

) -> Response[HTTPValidationError | PredictionRead]:
    """ Place Bet On Chain

     The on-chain counterpart to place_bet above — reached once
    components/app/genlayer-write-client.ts's betOnChain has already
    signed and sent a real NuancePredictionMarket.bet transaction directly
    to the chain. Doesn't verify the hash is real (see
    OnChainSubmissionAck's own docstring on why that's fine — nothing here
    is a trust boundary for the market's actual outcome); this only
    mirrors the stake into a PredictionPosition row so the existing "my
    positions" UI keeps working, since services/genlayer_indexer.py's
    view-sync doesn't track individual bettors' on-chain stakes today,
    only the market's own state/outcome as a whole.

    Args:
        prediction_id (int):
        body (OnChainBetAck): Body for POST /predictions/{id}/bet/on-chain — the frontend
            reporting a tx hash it already got back from signing and sending
            NuancePredictionMarket.bet itself (see components/app/
            genlayer-write-client.ts's betOnChain). Unlike a regular write ack,
            this ALSO carries side/amount: the real stake already lives in the
            contract's own storage, but this app still mirrors it into a
            PredictionPosition row immediately (same reasoning
            OnChainSubmissionAck's docstring gives for milestones) so the existing
            "my positions" UI keeps working without waiting on an indexer cycle
            that doesn't sync individual bettors' stakes at all today.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PredictionRead]
     """


    kwargs = _get_kwargs(
        prediction_id=prediction_id,
body=body,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    prediction_id: int,
    *,
    client: AuthenticatedClient,
    body: OnChainBetAck,

) -> HTTPValidationError | PredictionRead | None:
    """ Place Bet On Chain

     The on-chain counterpart to place_bet above — reached once
    components/app/genlayer-write-client.ts's betOnChain has already
    signed and sent a real NuancePredictionMarket.bet transaction directly
    to the chain. Doesn't verify the hash is real (see
    OnChainSubmissionAck's own docstring on why that's fine — nothing here
    is a trust boundary for the market's actual outcome); this only
    mirrors the stake into a PredictionPosition row so the existing "my
    positions" UI keeps working, since services/genlayer_indexer.py's
    view-sync doesn't track individual bettors' on-chain stakes today,
    only the market's own state/outcome as a whole.

    Args:
        prediction_id (int):
        body (OnChainBetAck): Body for POST /predictions/{id}/bet/on-chain — the frontend
            reporting a tx hash it already got back from signing and sending
            NuancePredictionMarket.bet itself (see components/app/
            genlayer-write-client.ts's betOnChain). Unlike a regular write ack,
            this ALSO carries side/amount: the real stake already lives in the
            contract's own storage, but this app still mirrors it into a
            PredictionPosition row immediately (same reasoning
            OnChainSubmissionAck's docstring gives for milestones) so the existing
            "my positions" UI keeps working without waiting on an indexer cycle
            that doesn't sync individual bettors' stakes at all today.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PredictionRead
     """


    return sync_detailed(
        prediction_id=prediction_id,
client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    prediction_id: int,
    *,
    client: AuthenticatedClient,
    body: OnChainBetAck,

) -> Response[HTTPValidationError | PredictionRead]:
    """ Place Bet On Chain

     The on-chain counterpart to place_bet above — reached once
    components/app/genlayer-write-client.ts's betOnChain has already
    signed and sent a real NuancePredictionMarket.bet transaction directly
    to the chain. Doesn't verify the hash is real (see
    OnChainSubmissionAck's own docstring on why that's fine — nothing here
    is a trust boundary for the market's actual outcome); this only
    mirrors the stake into a PredictionPosition row so the existing "my
    positions" UI keeps working, since services/genlayer_indexer.py's
    view-sync doesn't track individual bettors' on-chain stakes today,
    only the market's own state/outcome as a whole.

    Args:
        prediction_id (int):
        body (OnChainBetAck): Body for POST /predictions/{id}/bet/on-chain — the frontend
            reporting a tx hash it already got back from signing and sending
            NuancePredictionMarket.bet itself (see components/app/
            genlayer-write-client.ts's betOnChain). Unlike a regular write ack,
            this ALSO carries side/amount: the real stake already lives in the
            contract's own storage, but this app still mirrors it into a
            PredictionPosition row immediately (same reasoning
            OnChainSubmissionAck's docstring gives for milestones) so the existing
            "my positions" UI keeps working without waiting on an indexer cycle
            that doesn't sync individual bettors' stakes at all today.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PredictionRead]
     """


    kwargs = _get_kwargs(
        prediction_id=prediction_id,
body=body,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    prediction_id: int,
    *,
    client: AuthenticatedClient,
    body: OnChainBetAck,

) -> HTTPValidationError | PredictionRead | None:
    """ Place Bet On Chain

     The on-chain counterpart to place_bet above — reached once
    components/app/genlayer-write-client.ts's betOnChain has already
    signed and sent a real NuancePredictionMarket.bet transaction directly
    to the chain. Doesn't verify the hash is real (see
    OnChainSubmissionAck's own docstring on why that's fine — nothing here
    is a trust boundary for the market's actual outcome); this only
    mirrors the stake into a PredictionPosition row so the existing "my
    positions" UI keeps working, since services/genlayer_indexer.py's
    view-sync doesn't track individual bettors' on-chain stakes today,
    only the market's own state/outcome as a whole.

    Args:
        prediction_id (int):
        body (OnChainBetAck): Body for POST /predictions/{id}/bet/on-chain — the frontend
            reporting a tx hash it already got back from signing and sending
            NuancePredictionMarket.bet itself (see components/app/
            genlayer-write-client.ts's betOnChain). Unlike a regular write ack,
            this ALSO carries side/amount: the real stake already lives in the
            contract's own storage, but this app still mirrors it into a
            PredictionPosition row immediately (same reasoning
            OnChainSubmissionAck's docstring gives for milestones) so the existing
            "my positions" UI keeps working without waiting on an indexer cycle
            that doesn't sync individual bettors' stakes at all today.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PredictionRead
     """


    return (await asyncio_detailed(
        prediction_id=prediction_id,
client=client,
body=body,

    )).parsed
