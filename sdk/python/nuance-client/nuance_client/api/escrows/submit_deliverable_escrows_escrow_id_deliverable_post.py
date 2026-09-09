from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.deliverable_submission_create import DeliverableSubmissionCreate
from ...models.deliverable_submission_read import DeliverableSubmissionRead
from ...models.http_validation_error import HTTPValidationError
from typing import cast



def _get_kwargs(
    escrow_id: int,
    *,
    body: DeliverableSubmissionCreate,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/escrows/{escrow_id}/deliverable".format(escrow_id=quote(str(escrow_id), safe=""),),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> DeliverableSubmissionRead | HTTPValidationError | None:
    if response.status_code == 201:
        response_201 = DeliverableSubmissionRead.from_dict(response.json())



        return response_201

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[DeliverableSubmissionRead | HTTPValidationError]:
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
    body: DeliverableSubmissionCreate,

) -> Response[DeliverableSubmissionRead | HTTPValidationError]:
    """ Submit Deliverable

    Args:
        escrow_id (int):
        body (DeliverableSubmissionCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DeliverableSubmissionRead | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        escrow_id=escrow_id,
body=body,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    escrow_id: int,
    *,
    client: AuthenticatedClient,
    body: DeliverableSubmissionCreate,

) -> DeliverableSubmissionRead | HTTPValidationError | None:
    """ Submit Deliverable

    Args:
        escrow_id (int):
        body (DeliverableSubmissionCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DeliverableSubmissionRead | HTTPValidationError
     """


    return sync_detailed(
        escrow_id=escrow_id,
client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    escrow_id: int,
    *,
    client: AuthenticatedClient,
    body: DeliverableSubmissionCreate,

) -> Response[DeliverableSubmissionRead | HTTPValidationError]:
    """ Submit Deliverable

    Args:
        escrow_id (int):
        body (DeliverableSubmissionCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DeliverableSubmissionRead | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        escrow_id=escrow_id,
body=body,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    escrow_id: int,
    *,
    client: AuthenticatedClient,
    body: DeliverableSubmissionCreate,

) -> DeliverableSubmissionRead | HTTPValidationError | None:
    """ Submit Deliverable

    Args:
        escrow_id (int):
        body (DeliverableSubmissionCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DeliverableSubmissionRead | HTTPValidationError
     """


    return (await asyncio_detailed(
        escrow_id=escrow_id,
client=client,
body=body,

    )).parsed
