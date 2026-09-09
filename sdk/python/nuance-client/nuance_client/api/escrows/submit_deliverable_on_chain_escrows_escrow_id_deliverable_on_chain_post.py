from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.milestone_read import MilestoneRead
from ...models.on_chain_submission_ack import OnChainSubmissionAck
from typing import cast



def _get_kwargs(
    escrow_id: int,
    *,
    body: OnChainSubmissionAck,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/escrows/{escrow_id}/deliverable/on-chain".format(escrow_id=quote(str(escrow_id), safe=""),),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | MilestoneRead | None:
    if response.status_code == 201:
        response_201 = MilestoneRead.from_dict(response.json())



        return response_201

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | MilestoneRead]:
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
    body: OnChainSubmissionAck,

) -> Response[HTTPValidationError | MilestoneRead]:
    """ Submit Deliverable On Chain

     The on-chain counterpart to submit_deliverable above — reached once
    components/app/genlayer-write-client.ts has already signed and sent a
    real `NuanceEscrow.submit_deliverable` transaction directly to the
    chain (see ROADMAP.md 4.6's verified writeContract pattern). This
    endpoint does NOT run consensus, queue a ConsensusJob, or touch
    deliverable text/reasoning — GenVM's own validator committee is
    already doing that job on the deployed contract. All this does is
    remember the tx hash so services/genlayer_indexer.py has something to
    poll; see OnChainSubmissionAck's own docstring on why that's safe even
    though nothing here verifies the hash is real.

    Args:
        escrow_id (int):
        body (OnChainSubmissionAck): Body for POST /escrows/{id}/deliverable/on-chain — the
            frontend
            reporting a tx hash it already got back from signing and sending
            `NuanceEscrow.submit_deliverable` itself (see components/app/
            genlayer-write-client.ts). This endpoint only remembers the hash for
            services/genlayer_indexer.py to poll; it is NOT a trust boundary for
            the verdict — status_key/deliverable text only ever change once the
            indexer reads the real result back from the contract's own get_milestone
            view. A caller reporting a bogus hash can make the indexer log a failed
            lookup; it can never fake an approval this way.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | MilestoneRead]
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
    body: OnChainSubmissionAck,

) -> HTTPValidationError | MilestoneRead | None:
    """ Submit Deliverable On Chain

     The on-chain counterpart to submit_deliverable above — reached once
    components/app/genlayer-write-client.ts has already signed and sent a
    real `NuanceEscrow.submit_deliverable` transaction directly to the
    chain (see ROADMAP.md 4.6's verified writeContract pattern). This
    endpoint does NOT run consensus, queue a ConsensusJob, or touch
    deliverable text/reasoning — GenVM's own validator committee is
    already doing that job on the deployed contract. All this does is
    remember the tx hash so services/genlayer_indexer.py has something to
    poll; see OnChainSubmissionAck's own docstring on why that's safe even
    though nothing here verifies the hash is real.

    Args:
        escrow_id (int):
        body (OnChainSubmissionAck): Body for POST /escrows/{id}/deliverable/on-chain — the
            frontend
            reporting a tx hash it already got back from signing and sending
            `NuanceEscrow.submit_deliverable` itself (see components/app/
            genlayer-write-client.ts). This endpoint only remembers the hash for
            services/genlayer_indexer.py to poll; it is NOT a trust boundary for
            the verdict — status_key/deliverable text only ever change once the
            indexer reads the real result back from the contract's own get_milestone
            view. A caller reporting a bogus hash can make the indexer log a failed
            lookup; it can never fake an approval this way.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | MilestoneRead
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
    body: OnChainSubmissionAck,

) -> Response[HTTPValidationError | MilestoneRead]:
    """ Submit Deliverable On Chain

     The on-chain counterpart to submit_deliverable above — reached once
    components/app/genlayer-write-client.ts has already signed and sent a
    real `NuanceEscrow.submit_deliverable` transaction directly to the
    chain (see ROADMAP.md 4.6's verified writeContract pattern). This
    endpoint does NOT run consensus, queue a ConsensusJob, or touch
    deliverable text/reasoning — GenVM's own validator committee is
    already doing that job on the deployed contract. All this does is
    remember the tx hash so services/genlayer_indexer.py has something to
    poll; see OnChainSubmissionAck's own docstring on why that's safe even
    though nothing here verifies the hash is real.

    Args:
        escrow_id (int):
        body (OnChainSubmissionAck): Body for POST /escrows/{id}/deliverable/on-chain — the
            frontend
            reporting a tx hash it already got back from signing and sending
            `NuanceEscrow.submit_deliverable` itself (see components/app/
            genlayer-write-client.ts). This endpoint only remembers the hash for
            services/genlayer_indexer.py to poll; it is NOT a trust boundary for
            the verdict — status_key/deliverable text only ever change once the
            indexer reads the real result back from the contract's own get_milestone
            view. A caller reporting a bogus hash can make the indexer log a failed
            lookup; it can never fake an approval this way.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | MilestoneRead]
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
    body: OnChainSubmissionAck,

) -> HTTPValidationError | MilestoneRead | None:
    """ Submit Deliverable On Chain

     The on-chain counterpart to submit_deliverable above — reached once
    components/app/genlayer-write-client.ts has already signed and sent a
    real `NuanceEscrow.submit_deliverable` transaction directly to the
    chain (see ROADMAP.md 4.6's verified writeContract pattern). This
    endpoint does NOT run consensus, queue a ConsensusJob, or touch
    deliverable text/reasoning — GenVM's own validator committee is
    already doing that job on the deployed contract. All this does is
    remember the tx hash so services/genlayer_indexer.py has something to
    poll; see OnChainSubmissionAck's own docstring on why that's safe even
    though nothing here verifies the hash is real.

    Args:
        escrow_id (int):
        body (OnChainSubmissionAck): Body for POST /escrows/{id}/deliverable/on-chain — the
            frontend
            reporting a tx hash it already got back from signing and sending
            `NuanceEscrow.submit_deliverable` itself (see components/app/
            genlayer-write-client.ts). This endpoint only remembers the hash for
            services/genlayer_indexer.py to poll; it is NOT a trust boundary for
            the verdict — status_key/deliverable text only ever change once the
            indexer reads the real result back from the contract's own get_milestone
            view. A caller reporting a bogus hash can make the indexer log a failed
            lookup; it can never fake an approval this way.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | MilestoneRead
     """


    return (await asyncio_detailed(
        escrow_id=escrow_id,
client=client,
body=body,

    )).parsed
