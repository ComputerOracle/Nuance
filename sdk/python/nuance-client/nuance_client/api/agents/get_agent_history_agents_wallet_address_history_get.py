from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.agent_case_read import AgentCaseRead
from ...models.http_validation_error import HTTPValidationError
from typing import cast



def _get_kwargs(
    wallet_address: str,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/agents/{wallet_address}/history".format(wallet_address=quote(str(wallet_address), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | list[AgentCaseRead] | None:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in (_response_200):
            response_200_item = AgentCaseRead.from_dict(response_200_item_data)



            response_200.append(response_200_item)

        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | list[AgentCaseRead]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    wallet_address: str,
    *,
    client: AuthenticatedClient | Client,

) -> Response[HTTPValidationError | list[AgentCaseRead]]:
    """ Get Agent History

     Empty list (not 404) for a wallet with no judged cases — same
    reasoning as every other computed-on-read list endpoint here
    (GET /disputes/{id}/messages, GET /validators): there's no row to
    check existence against, this is purely a query over ConsensusJob
    history.

    Args:
        wallet_address (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[AgentCaseRead]]
     """


    kwargs = _get_kwargs(
        wallet_address=wallet_address,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    wallet_address: str,
    *,
    client: AuthenticatedClient | Client,

) -> HTTPValidationError | list[AgentCaseRead] | None:
    """ Get Agent History

     Empty list (not 404) for a wallet with no judged cases — same
    reasoning as every other computed-on-read list endpoint here
    (GET /disputes/{id}/messages, GET /validators): there's no row to
    check existence against, this is purely a query over ConsensusJob
    history.

    Args:
        wallet_address (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[AgentCaseRead]
     """


    return sync_detailed(
        wallet_address=wallet_address,
client=client,

    ).parsed

async def asyncio_detailed(
    wallet_address: str,
    *,
    client: AuthenticatedClient | Client,

) -> Response[HTTPValidationError | list[AgentCaseRead]]:
    """ Get Agent History

     Empty list (not 404) for a wallet with no judged cases — same
    reasoning as every other computed-on-read list endpoint here
    (GET /disputes/{id}/messages, GET /validators): there's no row to
    check existence against, this is purely a query over ConsensusJob
    history.

    Args:
        wallet_address (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[AgentCaseRead]]
     """


    kwargs = _get_kwargs(
        wallet_address=wallet_address,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    wallet_address: str,
    *,
    client: AuthenticatedClient | Client,

) -> HTTPValidationError | list[AgentCaseRead] | None:
    """ Get Agent History

     Empty list (not 404) for a wallet with no judged cases — same
    reasoning as every other computed-on-read list endpoint here
    (GET /disputes/{id}/messages, GET /validators): there's no row to
    check existence against, this is purely a query over ConsensusJob
    history.

    Args:
        wallet_address (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[AgentCaseRead]
     """


    return (await asyncio_detailed(
        wallet_address=wallet_address,
client=client,

    )).parsed
