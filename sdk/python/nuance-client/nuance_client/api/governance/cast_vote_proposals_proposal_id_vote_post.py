from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.proposal_read import ProposalRead
from ...models.vote_create import VoteCreate
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    proposal_id: int,
    *,
    body: VoteCreate,
    x_api_key: None | str | Unset = UNSET,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-Api-Key"] = x_api_key



    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/proposals/{proposal_id}/vote".format(proposal_id=quote(str(proposal_id), safe=""),),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
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
    body: VoteCreate,
    x_api_key: None | str | Unset = UNSET,

) -> Response[HTTPValidationError | ProposalRead]:
    """ Cast Vote

    Args:
        proposal_id (int):
        x_api_key (None | str | Unset):
        body (VoteCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ProposalRead]
     """


    kwargs = _get_kwargs(
        proposal_id=proposal_id,
body=body,
x_api_key=x_api_key,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    proposal_id: int,
    *,
    client: AuthenticatedClient,
    body: VoteCreate,
    x_api_key: None | str | Unset = UNSET,

) -> HTTPValidationError | ProposalRead | None:
    """ Cast Vote

    Args:
        proposal_id (int):
        x_api_key (None | str | Unset):
        body (VoteCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ProposalRead
     """


    return sync_detailed(
        proposal_id=proposal_id,
client=client,
body=body,
x_api_key=x_api_key,

    ).parsed

async def asyncio_detailed(
    proposal_id: int,
    *,
    client: AuthenticatedClient,
    body: VoteCreate,
    x_api_key: None | str | Unset = UNSET,

) -> Response[HTTPValidationError | ProposalRead]:
    """ Cast Vote

    Args:
        proposal_id (int):
        x_api_key (None | str | Unset):
        body (VoteCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ProposalRead]
     """


    kwargs = _get_kwargs(
        proposal_id=proposal_id,
body=body,
x_api_key=x_api_key,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    proposal_id: int,
    *,
    client: AuthenticatedClient,
    body: VoteCreate,
    x_api_key: None | str | Unset = UNSET,

) -> HTTPValidationError | ProposalRead | None:
    """ Cast Vote

    Args:
        proposal_id (int):
        x_api_key (None | str | Unset):
        body (VoteCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ProposalRead
     """


    return (await asyncio_detailed(
        proposal_id=proposal_id,
client=client,
body=body,
x_api_key=x_api_key,

    )).parsed
