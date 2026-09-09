from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.prediction_read import PredictionRead
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    *,
    status: None | str | Unset = 'open',

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    json_status: None | str | Unset
    if isinstance(status, Unset):
        json_status = UNSET
    else:
        json_status = status
    params["status"] = json_status


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/predictions",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | list[PredictionRead] | None:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in (_response_200):
            response_200_item = PredictionRead.from_dict(response_200_item_data)



            response_200.append(response_200_item)

        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | list[PredictionRead]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    status: None | str | Unset = 'open',

) -> Response[HTTPValidationError | list[PredictionRead]]:
    """ List Predictions

     Defaults to only `status_key == "open"` markets so unreviewed drafts
    (`"pending_review"`, see services/market_generator.py) never leak into
    the public betting feed just because a caller forgot to filter.

    `status=None` or `status="all"` (case-insensitive) returns every market
    regardless of status — e.g. for an internal review queue. Any other
    value filters to that exact status, matched case-insensitively since
    status_key casing isn't consistent across the codebase today (markets
    are created as lowercase "open"/"pending_review", but
    services/prediction_oracle.py resolves them to uppercase "RESOLVED").

    Args:
        status (None | str | Unset):  Default: 'open'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[PredictionRead]]
     """


    kwargs = _get_kwargs(
        status=status,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient | Client,
    status: None | str | Unset = 'open',

) -> HTTPValidationError | list[PredictionRead] | None:
    """ List Predictions

     Defaults to only `status_key == "open"` markets so unreviewed drafts
    (`"pending_review"`, see services/market_generator.py) never leak into
    the public betting feed just because a caller forgot to filter.

    `status=None` or `status="all"` (case-insensitive) returns every market
    regardless of status — e.g. for an internal review queue. Any other
    value filters to that exact status, matched case-insensitively since
    status_key casing isn't consistent across the codebase today (markets
    are created as lowercase "open"/"pending_review", but
    services/prediction_oracle.py resolves them to uppercase "RESOLVED").

    Args:
        status (None | str | Unset):  Default: 'open'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[PredictionRead]
     """


    return sync_detailed(
        client=client,
status=status,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    status: None | str | Unset = 'open',

) -> Response[HTTPValidationError | list[PredictionRead]]:
    """ List Predictions

     Defaults to only `status_key == "open"` markets so unreviewed drafts
    (`"pending_review"`, see services/market_generator.py) never leak into
    the public betting feed just because a caller forgot to filter.

    `status=None` or `status="all"` (case-insensitive) returns every market
    regardless of status — e.g. for an internal review queue. Any other
    value filters to that exact status, matched case-insensitively since
    status_key casing isn't consistent across the codebase today (markets
    are created as lowercase "open"/"pending_review", but
    services/prediction_oracle.py resolves them to uppercase "RESOLVED").

    Args:
        status (None | str | Unset):  Default: 'open'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[PredictionRead]]
     """


    kwargs = _get_kwargs(
        status=status,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    status: None | str | Unset = 'open',

) -> HTTPValidationError | list[PredictionRead] | None:
    """ List Predictions

     Defaults to only `status_key == "open"` markets so unreviewed drafts
    (`"pending_review"`, see services/market_generator.py) never leak into
    the public betting feed just because a caller forgot to filter.

    `status=None` or `status="all"` (case-insensitive) returns every market
    regardless of status — e.g. for an internal review queue. Any other
    value filters to that exact status, matched case-insensitively since
    status_key casing isn't consistent across the codebase today (markets
    are created as lowercase "open"/"pending_review", but
    services/prediction_oracle.py resolves them to uppercase "RESOLVED").

    Args:
        status (None | str | Unset):  Default: 'open'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[PredictionRead]
     """


    return (await asyncio_detailed(
        client=client,
status=status,

    )).parsed
