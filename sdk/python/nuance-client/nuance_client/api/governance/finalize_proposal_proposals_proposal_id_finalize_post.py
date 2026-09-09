from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.proposal_read import ProposalRead
from typing import cast



def _get_kwargs(
    proposal_id: int,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/proposals/{proposal_id}/finalize".format(proposal_id=quote(str(proposal_id), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | ProposalRead | None:
    if response.status_code == 200:
        response_200 = ProposalRead.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | ProposalRead]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    proposal_id: int,
    *,
    client: AuthenticatedClient | Client,

) -> Response[HTTPValidationError | ProposalRead]:
    """ Finalize Proposal

     Idempotent — an already-finalized proposal is returned as-is rather
    than re-evaluated, so calling this twice is always safe. Raises 400 if
    `end_time` hasn't arrived yet; a future bulk sweep (ROADMAP.md Part 1's
    cron) should filter to `end_time <= now()` itself before calling this
    per-id rather than relying on the 400 to skip early proposals.

    Args:
        proposal_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ProposalRead]
     """


    kwargs = _get_kwargs(
        proposal_id=proposal_id,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    proposal_id: int,
    *,
    client: AuthenticatedClient | Client,

) -> HTTPValidationError | ProposalRead | None:
    """ Finalize Proposal

     Idempotent — an already-finalized proposal is returned as-is rather
    than re-evaluated, so calling this twice is always safe. Raises 400 if
    `end_time` hasn't arrived yet; a future bulk sweep (ROADMAP.md Part 1's
    cron) should filter to `end_time <= now()` itself before calling this
    per-id rather than relying on the 400 to skip early proposals.

    Args:
        proposal_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ProposalRead
     """


    return sync_detailed(
        proposal_id=proposal_id,
client=client,

    ).parsed

async def asyncio_detailed(
    proposal_id: int,
    *,
    client: AuthenticatedClient | Client,

) -> Response[HTTPValidationError | ProposalRead]:
    """ Finalize Proposal

     Idempotent — an already-finalized proposal is returned as-is rather
    than re-evaluated, so calling this twice is always safe. Raises 400 if
    `end_time` hasn't arrived yet; a future bulk sweep (ROADMAP.md Part 1's
    cron) should filter to `end_time <= now()` itself before calling this
    per-id rather than relying on the 400 to skip early proposals.

    Args:
        proposal_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ProposalRead]
     """


    kwargs = _get_kwargs(
        proposal_id=proposal_id,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    proposal_id: int,
    *,
    client: AuthenticatedClient | Client,

) -> HTTPValidationError | ProposalRead | None:
    """ Finalize Proposal

     Idempotent — an already-finalized proposal is returned as-is rather
    than re-evaluated, so calling this twice is always safe. Raises 400 if
    `end_time` hasn't arrived yet; a future bulk sweep (ROADMAP.md Part 1's
    cron) should filter to `end_time <= now()` itself before calling this
    per-id rather than relying on the 400 to skip early proposals.

    Args:
        proposal_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ProposalRead
     """


    return (await asyncio_detailed(
        proposal_id=proposal_id,
client=client,

    )).parsed
