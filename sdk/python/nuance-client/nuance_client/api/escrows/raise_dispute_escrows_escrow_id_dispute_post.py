from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.dispute_create import DisputeCreate
from ...models.dispute_create_read import DisputeCreateRead
from ...models.http_validation_error import HTTPValidationError
from typing import cast



def _get_kwargs(
    escrow_id: int,
    *,
    body: DisputeCreate,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/escrows/{escrow_id}/dispute".format(escrow_id=quote(str(escrow_id), safe=""),),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> DisputeCreateRead | HTTPValidationError | None:
    if response.status_code == 201:
        response_201 = DisputeCreateRead.from_dict(response.json())



        return response_201

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[DisputeCreateRead | HTTPValidationError]:
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
    body: DisputeCreate,

) -> Response[DisputeCreateRead | HTTPValidationError]:
    """ Raise Dispute

     Escalates the escrow's active milestone to a formal Dispute Court
    review. Not previously implemented anywhere in this backend — ROADMAP.md
    3.1's Part 1 checklist marks "GET/POST /disputes (implicit via escrow)"
    done, but no such endpoint, implicit or otherwise, actually existed;
    escrow-detail-view.tsx's "Escalate to Internet Court" button has been
    unwired since it was written. This is that missing endpoint, escrow-
    scoped to match the "implicit via escrow" framing rather than a bare
    POST /disputes.

    Either party to the escrow may open one — mirrors contracts/
    nuance_dispute_court.py's file_dispute (claimant is whoever calls it;
    the other party is derivable from the escrow, same as this repo's
    existing mapDispute on the frontend already does — no separate
    `respondent` field needed). Creates the Dispute row and an initial
    DisputeEvidence entry together, then queues the same AI-jury review
    submit_evidence already runs below — a claim with no supporting text
    isn't reviewable.

    Args:
        escrow_id (int):
        body (DisputeCreate): Body for POST /escrows/{id}/dispute — escalating a milestone's AI
            verdict to a formal Dispute Court review. `issue` is optional: the
            "Escalate to Internet Court" button (components/app/views/
            escrow-detail-view.tsx) fires this with no form of its own, so the
            endpoint fills in a reasonable default from the milestone's most
            recent ConsensusJob reasoning when omitted — see routers/escrows.py's
            raise_dispute for that logic. Free-text override kept for any future
            caller that does want to state its own claim.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DisputeCreateRead | HTTPValidationError]
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
    body: DisputeCreate,

) -> DisputeCreateRead | HTTPValidationError | None:
    """ Raise Dispute

     Escalates the escrow's active milestone to a formal Dispute Court
    review. Not previously implemented anywhere in this backend — ROADMAP.md
    3.1's Part 1 checklist marks "GET/POST /disputes (implicit via escrow)"
    done, but no such endpoint, implicit or otherwise, actually existed;
    escrow-detail-view.tsx's "Escalate to Internet Court" button has been
    unwired since it was written. This is that missing endpoint, escrow-
    scoped to match the "implicit via escrow" framing rather than a bare
    POST /disputes.

    Either party to the escrow may open one — mirrors contracts/
    nuance_dispute_court.py's file_dispute (claimant is whoever calls it;
    the other party is derivable from the escrow, same as this repo's
    existing mapDispute on the frontend already does — no separate
    `respondent` field needed). Creates the Dispute row and an initial
    DisputeEvidence entry together, then queues the same AI-jury review
    submit_evidence already runs below — a claim with no supporting text
    isn't reviewable.

    Args:
        escrow_id (int):
        body (DisputeCreate): Body for POST /escrows/{id}/dispute — escalating a milestone's AI
            verdict to a formal Dispute Court review. `issue` is optional: the
            "Escalate to Internet Court" button (components/app/views/
            escrow-detail-view.tsx) fires this with no form of its own, so the
            endpoint fills in a reasonable default from the milestone's most
            recent ConsensusJob reasoning when omitted — see routers/escrows.py's
            raise_dispute for that logic. Free-text override kept for any future
            caller that does want to state its own claim.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DisputeCreateRead | HTTPValidationError
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
    body: DisputeCreate,

) -> Response[DisputeCreateRead | HTTPValidationError]:
    """ Raise Dispute

     Escalates the escrow's active milestone to a formal Dispute Court
    review. Not previously implemented anywhere in this backend — ROADMAP.md
    3.1's Part 1 checklist marks "GET/POST /disputes (implicit via escrow)"
    done, but no such endpoint, implicit or otherwise, actually existed;
    escrow-detail-view.tsx's "Escalate to Internet Court" button has been
    unwired since it was written. This is that missing endpoint, escrow-
    scoped to match the "implicit via escrow" framing rather than a bare
    POST /disputes.

    Either party to the escrow may open one — mirrors contracts/
    nuance_dispute_court.py's file_dispute (claimant is whoever calls it;
    the other party is derivable from the escrow, same as this repo's
    existing mapDispute on the frontend already does — no separate
    `respondent` field needed). Creates the Dispute row and an initial
    DisputeEvidence entry together, then queues the same AI-jury review
    submit_evidence already runs below — a claim with no supporting text
    isn't reviewable.

    Args:
        escrow_id (int):
        body (DisputeCreate): Body for POST /escrows/{id}/dispute — escalating a milestone's AI
            verdict to a formal Dispute Court review. `issue` is optional: the
            "Escalate to Internet Court" button (components/app/views/
            escrow-detail-view.tsx) fires this with no form of its own, so the
            endpoint fills in a reasonable default from the milestone's most
            recent ConsensusJob reasoning when omitted — see routers/escrows.py's
            raise_dispute for that logic. Free-text override kept for any future
            caller that does want to state its own claim.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DisputeCreateRead | HTTPValidationError]
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
    body: DisputeCreate,

) -> DisputeCreateRead | HTTPValidationError | None:
    """ Raise Dispute

     Escalates the escrow's active milestone to a formal Dispute Court
    review. Not previously implemented anywhere in this backend — ROADMAP.md
    3.1's Part 1 checklist marks "GET/POST /disputes (implicit via escrow)"
    done, but no such endpoint, implicit or otherwise, actually existed;
    escrow-detail-view.tsx's "Escalate to Internet Court" button has been
    unwired since it was written. This is that missing endpoint, escrow-
    scoped to match the "implicit via escrow" framing rather than a bare
    POST /disputes.

    Either party to the escrow may open one — mirrors contracts/
    nuance_dispute_court.py's file_dispute (claimant is whoever calls it;
    the other party is derivable from the escrow, same as this repo's
    existing mapDispute on the frontend already does — no separate
    `respondent` field needed). Creates the Dispute row and an initial
    DisputeEvidence entry together, then queues the same AI-jury review
    submit_evidence already runs below — a claim with no supporting text
    isn't reviewable.

    Args:
        escrow_id (int):
        body (DisputeCreate): Body for POST /escrows/{id}/dispute — escalating a milestone's AI
            verdict to a formal Dispute Court review. `issue` is optional: the
            "Escalate to Internet Court" button (components/app/views/
            escrow-detail-view.tsx) fires this with no form of its own, so the
            endpoint fills in a reasonable default from the milestone's most
            recent ConsensusJob reasoning when omitted — see routers/escrows.py's
            raise_dispute for that logic. Free-text override kept for any future
            caller that does want to state its own claim.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DisputeCreateRead | HTTPValidationError
     """


    return (await asyncio_detailed(
        escrow_id=escrow_id,
client=client,
body=body,

    )).parsed
