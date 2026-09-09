from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.escrow_read import EscrowRead
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    *,
    participant_address: None | str | Unset = UNSET,
    creator_address: None | str | Unset = UNSET,
    counterparty_address: None | str | Unset = UNSET,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    json_participant_address: None | str | Unset
    if isinstance(participant_address, Unset):
        json_participant_address = UNSET
    else:
        json_participant_address = participant_address
    params["participant_address"] = json_participant_address

    json_creator_address: None | str | Unset
    if isinstance(creator_address, Unset):
        json_creator_address = UNSET
    else:
        json_creator_address = creator_address
    params["creator_address"] = json_creator_address

    json_counterparty_address: None | str | Unset
    if isinstance(counterparty_address, Unset):
        json_counterparty_address = UNSET
    else:
        json_counterparty_address = counterparty_address
    params["counterparty_address"] = json_counterparty_address


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/escrows",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | list[EscrowRead] | None:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in (_response_200):
            response_200_item = EscrowRead.from_dict(response_200_item_data)



            response_200.append(response_200_item)

        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | list[EscrowRead]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    participant_address: None | str | Unset = UNSET,
    creator_address: None | str | Unset = UNSET,
    counterparty_address: None | str | Unset = UNSET,

) -> Response[HTTPValidationError | list[EscrowRead]]:
    """ List Escrows

    Args:
        participant_address (None | str | Unset):
        creator_address (None | str | Unset):
        counterparty_address (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[EscrowRead]]
     """


    kwargs = _get_kwargs(
        participant_address=participant_address,
creator_address=creator_address,
counterparty_address=counterparty_address,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,
    participant_address: None | str | Unset = UNSET,
    creator_address: None | str | Unset = UNSET,
    counterparty_address: None | str | Unset = UNSET,

) -> HTTPValidationError | list[EscrowRead] | None:
    """ List Escrows

    Args:
        participant_address (None | str | Unset):
        creator_address (None | str | Unset):
        counterparty_address (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[EscrowRead]
     """


    return sync_detailed(
        client=client,
participant_address=participant_address,
creator_address=creator_address,
counterparty_address=counterparty_address,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    participant_address: None | str | Unset = UNSET,
    creator_address: None | str | Unset = UNSET,
    counterparty_address: None | str | Unset = UNSET,

) -> Response[HTTPValidationError | list[EscrowRead]]:
    """ List Escrows

    Args:
        participant_address (None | str | Unset):
        creator_address (None | str | Unset):
        counterparty_address (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[EscrowRead]]
     """


    kwargs = _get_kwargs(
        participant_address=participant_address,
creator_address=creator_address,
counterparty_address=counterparty_address,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,
    participant_address: None | str | Unset = UNSET,
    creator_address: None | str | Unset = UNSET,
    counterparty_address: None | str | Unset = UNSET,

) -> HTTPValidationError | list[EscrowRead] | None:
    """ List Escrows

    Args:
        participant_address (None | str | Unset):
        creator_address (None | str | Unset):
        counterparty_address (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[EscrowRead]
     """


    return (await asyncio_detailed(
        client=client,
participant_address=participant_address,
creator_address=creator_address,
counterparty_address=counterparty_address,

    )).parsed
