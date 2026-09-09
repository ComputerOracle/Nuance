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
        "url": "/proposals/{proposal_id}/execute".format(proposal_id=quote(str(proposal_id), safe=""),),
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
    client: AuthenticatedClient,

) -> Response[HTTPValidationError | ProposalRead]:
    """ Execute Proposal

     Moves a PASSED proposal to EXECUTED — the formal "this decision has
    been enacted" marker. Not idempotent like finalize: a proposal can only
    be executed once, so a second call 400s rather than silently returning
    the same result, matching disputes.py's enforce_ruling precedent for
    the same "who did this and when" shape (executed_by/executed_at here,
    enforced_by/resolved_at there).

    No real on-chain effect is wired up yet (no treasury transfer, no
    parameter change) — see ROADMAP.md Part 3; this is deliberately scoped
    to just the status transition until there's a real effect to apply.

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
    client: AuthenticatedClient,

) -> HTTPValidationError | ProposalRead | None:
    """ Execute Proposal

     Moves a PASSED proposal to EXECUTED — the formal "this decision has
    been enacted" marker. Not idempotent like finalize: a proposal can only
    be executed once, so a second call 400s rather than silently returning
    the same result, matching disputes.py's enforce_ruling precedent for
    the same "who did this and when" shape (executed_by/executed_at here,
    enforced_by/resolved_at there).

    No real on-chain effect is wired up yet (no treasury transfer, no
    parameter change) — see ROADMAP.md Part 3; this is deliberately scoped
    to just the status transition until there's a real effect to apply.

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
    client: AuthenticatedClient,

) -> Response[HTTPValidationError | ProposalRead]:
    """ Execute Proposal

     Moves a PASSED proposal to EXECUTED — the formal "this decision has
    been enacted" marker. Not idempotent like finalize: a proposal can only
    be executed once, so a second call 400s rather than silently returning
    the same result, matching disputes.py's enforce_ruling precedent for
    the same "who did this and when" shape (executed_by/executed_at here,
    enforced_by/resolved_at there).

    No real on-chain effect is wired up yet (no treasury transfer, no
    parameter change) — see ROADMAP.md Part 3; this is deliberately scoped
    to just the status transition until there's a real effect to apply.

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
    client: AuthenticatedClient,

) -> HTTPValidationError | ProposalRead | None:
    """ Execute Proposal

     Moves a PASSED proposal to EXECUTED — the formal "this decision has
    been enacted" marker. Not idempotent like finalize: a proposal can only
    be executed once, so a second call 400s rather than silently returning
    the same result, matching disputes.py's enforce_ruling precedent for
    the same "who did this and when" shape (executed_by/executed_at here,
    enforced_by/resolved_at there).

    No real on-chain effect is wired up yet (no treasury transfer, no
    parameter change) — see ROADMAP.md Part 3; this is deliberately scoped
    to just the status transition until there's a real effect to apply.

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
