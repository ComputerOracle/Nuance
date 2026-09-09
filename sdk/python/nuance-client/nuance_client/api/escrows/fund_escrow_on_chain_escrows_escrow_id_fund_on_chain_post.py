from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.escrow_read import EscrowRead
from ...models.http_validation_error import HTTPValidationError
from ...models.on_chain_fund_ack import OnChainFundAck
from typing import cast



def _get_kwargs(
    escrow_id: int,
    *,
    body: OnChainFundAck,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/escrows/{escrow_id}/fund/on-chain".format(escrow_id=quote(str(escrow_id), safe=""),),
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
    body: OnChainFundAck,

) -> Response[EscrowRead | HTTPValidationError]:
    """ Fund Escrow On Chain

     Reached once components/app/genlayer-write-client.ts's
    fundEscrowOnChain has already signed and sent a real, *payable*
    NuanceEscrow.fund_escrow transaction — real GEN has already left the
    creator's wallet and now sits in the deployed contract's balance by
    the time this endpoint runs. Only the escrow creator may call
    fund_escrow on the contract itself (see that method's own source), so
    this endpoint enforces the same restriction rather than let anyone
    mark an escrow "funded." This does NOT verify the hash is real or
    read back the actual funded_amount — see OnChainFundAck's own
    docstring on why that's fine; it's UI bookkeeping (hide the "Fund
    Escrow" action), not the source of truth for whether the milestone
    can actually be released (release_milestone's own on-chain check
    against funded_amount is what actually matters).

    Args:
        escrow_id (int):
        body (OnChainFundAck): Body for POST /escrows/{id}/fund/on-chain — the frontend reporting
            a tx hash it already got back from signing and sending a real,
            *payable* NuanceEscrow.fund_escrow transaction (components/app/
            genlayer-write-client.ts's fundEscrowOnChain) — real GEN actually left
            the creator's wallet and now sits in the deployed contract's balance.
            Same "not a trust boundary" reasoning as OnChainSubmissionAck: this
            only remembers that a fund_escrow call was sent, for UI purposes
            (hide the "Fund Escrow" action once it has); the contract's own
            funded_amount (checked by release_milestone before any payout) is the
            real source of truth regardless of what this endpoint is told.

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
    body: OnChainFundAck,

) -> EscrowRead | HTTPValidationError | None:
    """ Fund Escrow On Chain

     Reached once components/app/genlayer-write-client.ts's
    fundEscrowOnChain has already signed and sent a real, *payable*
    NuanceEscrow.fund_escrow transaction — real GEN has already left the
    creator's wallet and now sits in the deployed contract's balance by
    the time this endpoint runs. Only the escrow creator may call
    fund_escrow on the contract itself (see that method's own source), so
    this endpoint enforces the same restriction rather than let anyone
    mark an escrow "funded." This does NOT verify the hash is real or
    read back the actual funded_amount — see OnChainFundAck's own
    docstring on why that's fine; it's UI bookkeeping (hide the "Fund
    Escrow" action), not the source of truth for whether the milestone
    can actually be released (release_milestone's own on-chain check
    against funded_amount is what actually matters).

    Args:
        escrow_id (int):
        body (OnChainFundAck): Body for POST /escrows/{id}/fund/on-chain — the frontend reporting
            a tx hash it already got back from signing and sending a real,
            *payable* NuanceEscrow.fund_escrow transaction (components/app/
            genlayer-write-client.ts's fundEscrowOnChain) — real GEN actually left
            the creator's wallet and now sits in the deployed contract's balance.
            Same "not a trust boundary" reasoning as OnChainSubmissionAck: this
            only remembers that a fund_escrow call was sent, for UI purposes
            (hide the "Fund Escrow" action once it has); the contract's own
            funded_amount (checked by release_milestone before any payout) is the
            real source of truth regardless of what this endpoint is told.

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
    body: OnChainFundAck,

) -> Response[EscrowRead | HTTPValidationError]:
    """ Fund Escrow On Chain

     Reached once components/app/genlayer-write-client.ts's
    fundEscrowOnChain has already signed and sent a real, *payable*
    NuanceEscrow.fund_escrow transaction — real GEN has already left the
    creator's wallet and now sits in the deployed contract's balance by
    the time this endpoint runs. Only the escrow creator may call
    fund_escrow on the contract itself (see that method's own source), so
    this endpoint enforces the same restriction rather than let anyone
    mark an escrow "funded." This does NOT verify the hash is real or
    read back the actual funded_amount — see OnChainFundAck's own
    docstring on why that's fine; it's UI bookkeeping (hide the "Fund
    Escrow" action), not the source of truth for whether the milestone
    can actually be released (release_milestone's own on-chain check
    against funded_amount is what actually matters).

    Args:
        escrow_id (int):
        body (OnChainFundAck): Body for POST /escrows/{id}/fund/on-chain — the frontend reporting
            a tx hash it already got back from signing and sending a real,
            *payable* NuanceEscrow.fund_escrow transaction (components/app/
            genlayer-write-client.ts's fundEscrowOnChain) — real GEN actually left
            the creator's wallet and now sits in the deployed contract's balance.
            Same "not a trust boundary" reasoning as OnChainSubmissionAck: this
            only remembers that a fund_escrow call was sent, for UI purposes
            (hide the "Fund Escrow" action once it has); the contract's own
            funded_amount (checked by release_milestone before any payout) is the
            real source of truth regardless of what this endpoint is told.

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
    body: OnChainFundAck,

) -> EscrowRead | HTTPValidationError | None:
    """ Fund Escrow On Chain

     Reached once components/app/genlayer-write-client.ts's
    fundEscrowOnChain has already signed and sent a real, *payable*
    NuanceEscrow.fund_escrow transaction — real GEN has already left the
    creator's wallet and now sits in the deployed contract's balance by
    the time this endpoint runs. Only the escrow creator may call
    fund_escrow on the contract itself (see that method's own source), so
    this endpoint enforces the same restriction rather than let anyone
    mark an escrow "funded." This does NOT verify the hash is real or
    read back the actual funded_amount — see OnChainFundAck's own
    docstring on why that's fine; it's UI bookkeeping (hide the "Fund
    Escrow" action), not the source of truth for whether the milestone
    can actually be released (release_milestone's own on-chain check
    against funded_amount is what actually matters).

    Args:
        escrow_id (int):
        body (OnChainFundAck): Body for POST /escrows/{id}/fund/on-chain — the frontend reporting
            a tx hash it already got back from signing and sending a real,
            *payable* NuanceEscrow.fund_escrow transaction (components/app/
            genlayer-write-client.ts's fundEscrowOnChain) — real GEN actually left
            the creator's wallet and now sits in the deployed contract's balance.
            Same "not a trust boundary" reasoning as OnChainSubmissionAck: this
            only remembers that a fund_escrow call was sent, for UI purposes
            (hide the "Fund Escrow" action once it has); the contract's own
            funded_amount (checked by release_milestone before any payout) is the
            real source of truth regardless of what this endpoint is told.

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
