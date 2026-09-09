from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.prediction_bet_create import PredictionBetCreate
from ...models.prediction_read import PredictionRead
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    prediction_id: int,
    *,
    body: PredictionBetCreate,
    x_api_key: None | str | Unset = UNSET,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-Api-Key"] = x_api_key



    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/predictions/{prediction_id}/bet".format(prediction_id=quote(str(prediction_id), safe=""),),
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
    body: PredictionBetCreate,
    x_api_key: None | str | Unset = UNSET,

) -> Response[HTTPValidationError | PredictionRead]:
    """ Place Bet

    Args:
        prediction_id (int):
        x_api_key (None | str | Unset):
        body (PredictionBetCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PredictionRead]
     """


    kwargs = _get_kwargs(
        prediction_id=prediction_id,
body=body,
x_api_key=x_api_key,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    prediction_id: int,
    *,
    client: AuthenticatedClient,
    body: PredictionBetCreate,
    x_api_key: None | str | Unset = UNSET,

) -> HTTPValidationError | PredictionRead | None:
    """ Place Bet

    Args:
        prediction_id (int):
        x_api_key (None | str | Unset):
        body (PredictionBetCreate):

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
x_api_key=x_api_key,

    ).parsed

async def asyncio_detailed(
    prediction_id: int,
    *,
    client: AuthenticatedClient,
    body: PredictionBetCreate,
    x_api_key: None | str | Unset = UNSET,

) -> Response[HTTPValidationError | PredictionRead]:
    """ Place Bet

    Args:
        prediction_id (int):
        x_api_key (None | str | Unset):
        body (PredictionBetCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PredictionRead]
     """


    kwargs = _get_kwargs(
        prediction_id=prediction_id,
body=body,
x_api_key=x_api_key,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    prediction_id: int,
    *,
    client: AuthenticatedClient,
    body: PredictionBetCreate,
    x_api_key: None | str | Unset = UNSET,

) -> HTTPValidationError | PredictionRead | None:
    """ Place Bet

    Args:
        prediction_id (int):
        x_api_key (None | str | Unset):
        body (PredictionBetCreate):

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
x_api_key=x_api_key,

    )).parsed
