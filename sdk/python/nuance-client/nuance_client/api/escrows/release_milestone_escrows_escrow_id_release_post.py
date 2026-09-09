from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.escrow_read import EscrowRead
from ...models.http_validation_error import HTTPValidationError
from typing import cast



def _get_kwargs(
    escrow_id: int,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/escrows/{escrow_id}/release".format(escrow_id=quote(str(escrow_id), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> EscrowRead | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = EscrowRead.from_dict(response.json())



        return response_200

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

) -> Response[EscrowRead | HTTPValidationError]:
    """ Release Milestone

    Args:
        escrow_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[EscrowRead | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        escrow_id=escrow_id,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    escrow_id: int,
    *,
    client: AuthenticatedClient,

) -> EscrowRead | HTTPValidationError | None:
    """ Release Milestone

    Args:
        escrow_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        EscrowRead | HTTPValidationError
     """


    return sync_detailed(
        escrow_id=escrow_id,
client=client,

    ).parsed

async def asyncio_detailed(
    escrow_id: int,
    *,
    client: AuthenticatedClient,

) -> Response[EscrowRead | HTTPValidationError]:
    """ Release Milestone

    Args:
        escrow_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[EscrowRead | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        escrow_id=escrow_id,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    escrow_id: int,
    *,
    client: AuthenticatedClient,

) -> EscrowRead | HTTPValidationError | None:
    """ Release Milestone

    Args:
        escrow_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        EscrowRead | HTTPValidationError
     """


    return (await asyncio_detailed(
        escrow_id=escrow_id,
client=client,

    )).parsed
