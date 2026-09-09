from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.dispute_evidence_read import DisputeEvidenceRead
from ...models.http_validation_error import HTTPValidationError
from typing import cast



def _get_kwargs(
    dispute_id: int,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/disputes/{dispute_id}/evidence".format(dispute_id=quote(str(dispute_id), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | list[DisputeEvidenceRead] | None:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in (_response_200):
            response_200_item = DisputeEvidenceRead.from_dict(response_200_item_data)



            response_200.append(response_200_item)

        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | list[DisputeEvidenceRead]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    dispute_id: int,
    *,
    client: AuthenticatedClient | Client,

) -> Response[HTTPValidationError | list[DisputeEvidenceRead]]:
    """ List Evidence

    Args:
        dispute_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[DisputeEvidenceRead]]
     """


    kwargs = _get_kwargs(
        dispute_id=dispute_id,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    dispute_id: int,
    *,
    client: AuthenticatedClient | Client,

) -> HTTPValidationError | list[DisputeEvidenceRead] | None:
    """ List Evidence

    Args:
        dispute_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[DisputeEvidenceRead]
     """


    return sync_detailed(
        dispute_id=dispute_id,
client=client,

    ).parsed

async def asyncio_detailed(
    dispute_id: int,
    *,
    client: AuthenticatedClient | Client,

) -> Response[HTTPValidationError | list[DisputeEvidenceRead]]:
    """ List Evidence

    Args:
        dispute_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[DisputeEvidenceRead]]
     """


    kwargs = _get_kwargs(
        dispute_id=dispute_id,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    dispute_id: int,
    *,
    client: AuthenticatedClient | Client,

) -> HTTPValidationError | list[DisputeEvidenceRead] | None:
    """ List Evidence

    Args:
        dispute_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[DisputeEvidenceRead]
     """


    return (await asyncio_detailed(
        dispute_id=dispute_id,
client=client,

    )).parsed
