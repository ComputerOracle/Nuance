from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.escrow_read import EscrowRead
from ...models.http_validation_error import HTTPValidationError
from ...models.on_chain_cancel_ack import OnChainCancelAck
from typing import cast



def _get_kwargs(
    escrow_id: int,
    *,
    body: OnChainCancelAck,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/escrows/{escrow_id}/cancel/on-chain".format(escrow_id=quote(str(escrow_id), safe=""),),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> EscrowRead | HTTPValidationError | None:
    if response.status_code == 201:
        response_201 = EscrowRead.from_dict(response.json())



        return response_201

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[EscrowRead | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    escrow_id: int,
    *,
    client: AuthenticatedClient,
    body: OnChainCancelAck,

) -> Response[EscrowRead | HTTPValidationError]:
    """ Cancel Escrow On Chain

     Reached once components/app/genlayer-write-client.ts's
    cancelEscrowOnChain has already signed and sent a real
    NuanceEscrow.cancel_escrow transaction — the contract itself has
    already refunded whatever was locked back to the creator's wallet by
    the time this endpoint runs (see that contract method's own
    docstring). Only the escrow creator may call cancel_escrow on the
    contract itself, so this endpoint enforces the same restriction.

    Unlike fund/deliverable acks, this DOES immediately flip status_key —
    see OnChainCancelAck's own docstring on why that's safe here
    specifically (real enforcement lives entirely on the contract; this
    is local bookkeeping only, same trust level raise_dispute_on_chain's
    ack already uses elsewhere in this file).

    Args:
        escrow_id (int):
        body (OnChainCancelAck): Body for POST /escrows/{id}/cancel/on-chain — the frontend
            reporting a tx hash it already got back from signing and sending a
            real NuanceEscrow.cancel_escrow transaction (components/app/
            genlayer-write-client.ts's cancelEscrowOnChain).

            Unlike OnChainFundAck/OnChainSubmissionAck, this DOES immediately
            flip status_key to StatusKey.CANCELLED — same trust level as
            raise_dispute_on_chain's own ack already uses (create the local
            record from what the caller reports, rather than waiting on an
            indexer read). Safe here for the same reason: cancel_escrow's real
            enforcement lives entirely on the contract itself — submit_
            deliverable/fund_escrow/release_milestone all check the contract's
            own `status` field directly, never this app's DB. A caller falsely
            claiming a cancellation that never actually happened on-chain can
            only produce a stale/wrong *local* status badge, never let anyone
            bypass what the contract actually enforces.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[EscrowRead | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        escrow_id=escrow_id,
body=body,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    escrow_id: int,
    *,
    client: AuthenticatedClient,
    body: OnChainCancelAck,

) -> EscrowRead | HTTPValidationError | None:
    """ Cancel Escrow On Chain

     Reached once components/app/genlayer-write-client.ts's
    cancelEscrowOnChain has already signed and sent a real
    NuanceEscrow.cancel_escrow transaction — the contract itself has
    already refunded whatever was locked back to the creator's wallet by
    the time this endpoint runs (see that contract method's own
    docstring). Only the escrow creator may call cancel_escrow on the
    contract itself, so this endpoint enforces the same restriction.

    Unlike fund/deliverable acks, this DOES immediately flip status_key —
    see OnChainCancelAck's own docstring on why that's safe here
    specifically (real enforcement lives entirely on the contract; this
    is local bookkeeping only, same trust level raise_dispute_on_chain's
    ack already uses elsewhere in this file).

    Args:
        escrow_id (int):
        body (OnChainCancelAck): Body for POST /escrows/{id}/cancel/on-chain — the frontend
            reporting a tx hash it already got back from signing and sending a
            real NuanceEscrow.cancel_escrow transaction (components/app/
            genlayer-write-client.ts's cancelEscrowOnChain).

            Unlike OnChainFundAck/OnChainSubmissionAck, this DOES immediately
            flip status_key to StatusKey.CANCELLED — same trust level as
            raise_dispute_on_chain's own ack already uses (create the local
            record from what the caller reports, rather than waiting on an
            indexer read). Safe here for the same reason: cancel_escrow's real
            enforcement lives entirely on the contract itself — submit_
            deliverable/fund_escrow/release_milestone all check the contract's
            own `status` field directly, never this app's DB. A caller falsely
            claiming a cancellation that never actually happened on-chain can
            only produce a stale/wrong *local* status badge, never let anyone
            bypass what the contract actually enforces.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        EscrowRead | HTTPValidationError
     """


    return sync_detailed(
        escrow_id=escrow_id,
client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    escrow_id: int,
    *,
    client: AuthenticatedClient,
    body: OnChainCancelAck,

) -> Response[EscrowRead | HTTPValidationError]:
    """ Cancel Escrow On Chain

     Reached once components/app/genlayer-write-client.ts's
    cancelEscrowOnChain has already signed and sent a real
    NuanceEscrow.cancel_escrow transaction — the contract itself has
    already refunded whatever was locked back to the creator's wallet by
    the time this endpoint runs (see that contract method's own
    docstring). Only the escrow creator may call cancel_escrow on the
    contract itself, so this endpoint enforces the same restriction.

    Unlike fund/deliverable acks, this DOES immediately flip status_key —
    see OnChainCancelAck's own docstring on why that's safe here
    specifically (real enforcement lives entirely on the contract; this
    is local bookkeeping only, same trust level raise_dispute_on_chain's
    ack already uses elsewhere in this file).

    Args:
        escrow_id (int):
        body (OnChainCancelAck): Body for POST /escrows/{id}/cancel/on-chain — the frontend
            reporting a tx hash it already got back from signing and sending a
            real NuanceEscrow.cancel_escrow transaction (components/app/
            genlayer-write-client.ts's cancelEscrowOnChain).

            Unlike OnChainFundAck/OnChainSubmissionAck, this DOES immediately
            flip status_key to StatusKey.CANCELLED — same trust level as
            raise_dispute_on_chain's own ack already uses (create the local
            record from what the caller reports, rather than waiting on an
            indexer read). Safe here for the same reason: cancel_escrow's real
            enforcement lives entirely on the contract itself — submit_
            deliverable/fund_escrow/release_milestone all check the contract's
            own `status` field directly, never this app's DB. A caller falsely
            claiming a cancellation that never actually happened on-chain can
            only produce a stale/wrong *local* status badge, never let anyone
            bypass what the contract actually enforces.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[EscrowRead | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        escrow_id=escrow_id,
body=body,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    escrow_id: int,
    *,
    client: AuthenticatedClient,
    body: OnChainCancelAck,

) -> EscrowRead | HTTPValidationError | None:
    """ Cancel Escrow On Chain

     Reached once components/app/genlayer-write-client.ts's
    cancelEscrowOnChain has already signed and sent a real
    NuanceEscrow.cancel_escrow transaction — the contract itself has
    already refunded whatever was locked back to the creator's wallet by
    the time this endpoint runs (see that contract method's own
    docstring). Only the escrow creator may call cancel_escrow on the
    contract itself, so this endpoint enforces the same restriction.

    Unlike fund/deliverable acks, this DOES immediately flip status_key —
    see OnChainCancelAck's own docstring on why that's safe here
    specifically (real enforcement lives entirely on the contract; this
    is local bookkeeping only, same trust level raise_dispute_on_chain's
    ack already uses elsewhere in this file).

    Args:
        escrow_id (int):
        body (OnChainCancelAck): Body for POST /escrows/{id}/cancel/on-chain — the frontend
            reporting a tx hash it already got back from signing and sending a
            real NuanceEscrow.cancel_escrow transaction (components/app/
            genlayer-write-client.ts's cancelEscrowOnChain).

            Unlike OnChainFundAck/OnChainSubmissionAck, this DOES immediately
            flip status_key to StatusKey.CANCELLED — same trust level as
            raise_dispute_on_chain's own ack already uses (create the local
            record from what the caller reports, rather than waiting on an
            indexer read). Safe here for the same reason: cancel_escrow's real
            enforcement lives entirely on the contract itself — submit_
            deliverable/fund_escrow/release_milestone all check the contract's
            own `status` field directly, never this app's DB. A caller falsely
            claiming a cancellation that never actually happened on-chain can
            only produce a stale/wrong *local* status badge, never let anyone
            bypass what the contract actually enforces.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        EscrowRead | HTTPValidationError
     """


    return (await asyncio_detailed(
        escrow_id=escrow_id,
client=client,
body=body,

    )).parsed
