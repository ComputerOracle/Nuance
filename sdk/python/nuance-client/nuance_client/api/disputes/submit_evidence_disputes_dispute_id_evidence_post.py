from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.dispute_evidence_create import DisputeEvidenceCreate
from ...models.dispute_evidence_read import DisputeEvidenceRead
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    dispute_id: int,
    *,
    body: DisputeEvidenceCreate,
    x_api_key: None | str | Unset = UNSET,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-Api-Key"] = x_api_key



    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/disputes/{dispute_id}/evidence".format(dispute_id=quote(str(dispute_id), safe=""),),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> DisputeEvidenceRead | HTTPValidationError | None:
    if response.status_code == 201:
        response_201 = DisputeEvidenceRead.from_dict(response.json())



        return response_201

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[DisputeEvidenceRead | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    dispute_id: int,
    *,
    client: AuthenticatedClient,
    body: DisputeEvidenceCreate,
    x_api_key: None | str | Unset = UNSET,

) -> Response[DisputeEvidenceRead | HTTPValidationError]:
    """ Submit Evidence

    Args:
        dispute_id (int):
        x_api_key (None | str | Unset):
        body (DisputeEvidenceCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DisputeEvidenceRead | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        dispute_id=dispute_id,
body=body,
x_api_key=x_api_key,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    dispute_id: int,
    *,
    client: AuthenticatedClient,
    body: DisputeEvidenceCreate,
    x_api_key: None | str | Unset = UNSET,

) -> DisputeEvidenceRead | HTTPValidationError | None:
    """ Submit Evidence

    Args:
        dispute_id (int):
        x_api_key (None | str | Unset):
        body (DisputeEvidenceCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DisputeEvidenceRead | HTTPValidationError
     """


    return sync_detailed(
        dispute_id=dispute_id,
client=client,
body=body,
x_api_key=x_api_key,

    ).parsed

async def asyncio_detailed(
    dispute_id: int,
    *,
    client: AuthenticatedClient,
    body: DisputeEvidenceCreate,
    x_api_key: None | str | Unset = UNSET,

) -> Response[DisputeEvidenceRead | HTTPValidationError]:
    """ Submit Evidence

    Args:
        dispute_id (int):
        x_api_key (None | str | Unset):
        body (DisputeEvidenceCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DisputeEvidenceRead | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        dispute_id=dispute_id,
body=body,
x_api_key=x_api_key,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    dispute_id: int,
    *,
    client: AuthenticatedClient,
    body: DisputeEvidenceCreate,
    x_api_key: None | str | Unset = UNSET,

) -> DisputeEvidenceRead | HTTPValidationError | None:
    """ Submit Evidence

    Args:
        dispute_id (int):
        x_api_key (None | str | Unset):
        body (DisputeEvidenceCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DisputeEvidenceRead | HTTPValidationError
     """


    return (await asyncio_detailed(
        dispute_id=dispute_id,
client=client,
body=body,
x_api_key=x_api_key,

    )).parsed
