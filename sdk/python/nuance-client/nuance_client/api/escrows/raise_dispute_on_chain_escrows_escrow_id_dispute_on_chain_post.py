from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.dispute_read import DisputeRead
from ...models.http_validation_error import HTTPValidationError
from ...models.on_chain_dispute_ack import OnChainDisputeAck
from typing import cast



def _get_kwargs(
    escrow_id: int,
    *,
    body: OnChainDisputeAck,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/escrows/{escrow_id}/dispute/on-chain".format(escrow_id=quote(str(escrow_id), safe=""),),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> DisputeRead | HTTPValidationError | None:
    if response.status_code == 201:
        response_201 = DisputeRead.from_dict(response.json())



        return response_201

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[DisputeRead | HTTPValidationError]:
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
    body: OnChainDisputeAck,

) -> Response[DisputeRead | HTTPValidationError]:
    """ Raise Dispute On Chain

     The on-chain counterpart to raise_dispute above — reached once
    genlayer-write-client.ts has already signed and sent a real
    NuanceDisputeCourt.file_dispute transaction directly to the chain.

    Unlike submit_deliverable_on_chain (which updates an existing row),
    this CREATES the Dispute immediately, with on_chain_dispute_id left
    null — file_dispute assigns that id on-chain, and there's no cheap way
    to read a regular write call's return value back out of genlayer-js's
    receipt (see Settings.dispute_id_scan_window's own comment for why).
    services/genlayer_indexer.py's resolve_pending_dispute_ids fills it in
    asynchronously once the transaction lands, by matching (claimant,
    escrow_address, claim_statement) against the contract's own history —
    same "not a trust boundary" reasoning as OnChainSubmissionAck: nothing
    here verifies the hash is real, only the indexer reading actual chain
    state ever changes status_key/ruling.

    No ConsensusJob queued, no run_consensus — GenVM's own validator
    committee is the jury once adjudicate_dispute is actually called
    against this contract (a separate action from filing, not wired by
    this endpoint).

    Args:
        escrow_id (int):
        body (OnChainDisputeAck): Body for POST /escrows/{id}/dispute/on-chain — the frontend
            reporting a tx hash it already got back from signing and sending
            `NuanceDisputeCourt.file_dispute` itself (see components/app/
            genlayer-write-client.ts). Unlike OnChainSubmissionAck (which updates
            an existing Milestone), this one CREATES the local Dispute row
            immediately — file_dispute assigns the dispute's id on-chain, which
            isn't known yet at ack time. See services/genlayer_indexer.py's
            resolve_pending_dispute_ids for how on_chain_dispute_id gets filled in
            once the transaction actually lands. `issue` mirrors DisputeCreate's
            own optional-with-a-server-side-default behavior, and MUST match the
            `claim_statement` argument the frontend actually passed to
            file_dispute — the indexer matches on exact text equality, not fuzzy
            matching.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DisputeRead | HTTPValidationError]
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
    body: OnChainDisputeAck,

) -> DisputeRead | HTTPValidationError | None:
    """ Raise Dispute On Chain

     The on-chain counterpart to raise_dispute above — reached once
    genlayer-write-client.ts has already signed and sent a real
    NuanceDisputeCourt.file_dispute transaction directly to the chain.

    Unlike submit_deliverable_on_chain (which updates an existing row),
    this CREATES the Dispute immediately, with on_chain_dispute_id left
    null — file_dispute assigns that id on-chain, and there's no cheap way
    to read a regular write call's return value back out of genlayer-js's
    receipt (see Settings.dispute_id_scan_window's own comment for why).
    services/genlayer_indexer.py's resolve_pending_dispute_ids fills it in
    asynchronously once the transaction lands, by matching (claimant,
    escrow_address, claim_statement) against the contract's own history —
    same "not a trust boundary" reasoning as OnChainSubmissionAck: nothing
    here verifies the hash is real, only the indexer reading actual chain
    state ever changes status_key/ruling.

    No ConsensusJob queued, no run_consensus — GenVM's own validator
    committee is the jury once adjudicate_dispute is actually called
    against this contract (a separate action from filing, not wired by
    this endpoint).

    Args:
        escrow_id (int):
        body (OnChainDisputeAck): Body for POST /escrows/{id}/dispute/on-chain — the frontend
            reporting a tx hash it already got back from signing and sending
            `NuanceDisputeCourt.file_dispute` itself (see components/app/
            genlayer-write-client.ts). Unlike OnChainSubmissionAck (which updates
            an existing Milestone), this one CREATES the local Dispute row
            immediately — file_dispute assigns the dispute's id on-chain, which
            isn't known yet at ack time. See services/genlayer_indexer.py's
            resolve_pending_dispute_ids for how on_chain_dispute_id gets filled in
            once the transaction actually lands. `issue` mirrors DisputeCreate's
            own optional-with-a-server-side-default behavior, and MUST match the
            `claim_statement` argument the frontend actually passed to
            file_dispute — the indexer matches on exact text equality, not fuzzy
            matching.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DisputeRead | HTTPValidationError
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
    body: OnChainDisputeAck,

) -> Response[DisputeRead | HTTPValidationError]:
    """ Raise Dispute On Chain

     The on-chain counterpart to raise_dispute above — reached once
    genlayer-write-client.ts has already signed and sent a real
    NuanceDisputeCourt.file_dispute transaction directly to the chain.

    Unlike submit_deliverable_on_chain (which updates an existing row),
    this CREATES the Dispute immediately, with on_chain_dispute_id left
    null — file_dispute assigns that id on-chain, and there's no cheap way
    to read a regular write call's return value back out of genlayer-js's
    receipt (see Settings.dispute_id_scan_window's own comment for why).
    services/genlayer_indexer.py's resolve_pending_dispute_ids fills it in
    asynchronously once the transaction lands, by matching (claimant,
    escrow_address, claim_statement) against the contract's own history —
    same "not a trust boundary" reasoning as OnChainSubmissionAck: nothing
    here verifies the hash is real, only the indexer reading actual chain
    state ever changes status_key/ruling.

    No ConsensusJob queued, no run_consensus — GenVM's own validator
    committee is the jury once adjudicate_dispute is actually called
    against this contract (a separate action from filing, not wired by
    this endpoint).

    Args:
        escrow_id (int):
        body (OnChainDisputeAck): Body for POST /escrows/{id}/dispute/on-chain — the frontend
            reporting a tx hash it already got back from signing and sending
            `NuanceDisputeCourt.file_dispute` itself (see components/app/
            genlayer-write-client.ts). Unlike OnChainSubmissionAck (which updates
            an existing Milestone), this one CREATES the local Dispute row
            immediately — file_dispute assigns the dispute's id on-chain, which
            isn't known yet at ack time. See services/genlayer_indexer.py's
            resolve_pending_dispute_ids for how on_chain_dispute_id gets filled in
            once the transaction actually lands. `issue` mirrors DisputeCreate's
            own optional-with-a-server-side-default behavior, and MUST match the
            `claim_statement` argument the frontend actually passed to
            file_dispute — the indexer matches on exact text equality, not fuzzy
            matching.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DisputeRead | HTTPValidationError]
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
    body: OnChainDisputeAck,

) -> DisputeRead | HTTPValidationError | None:
    """ Raise Dispute On Chain

     The on-chain counterpart to raise_dispute above — reached once
    genlayer-write-client.ts has already signed and sent a real
    NuanceDisputeCourt.file_dispute transaction directly to the chain.

    Unlike submit_deliverable_on_chain (which updates an existing row),
    this CREATES the Dispute immediately, with on_chain_dispute_id left
    null — file_dispute assigns that id on-chain, and there's no cheap way
    to read a regular write call's return value back out of genlayer-js's
    receipt (see Settings.dispute_id_scan_window's own comment for why).
    services/genlayer_indexer.py's resolve_pending_dispute_ids fills it in
    asynchronously once the transaction lands, by matching (claimant,
    escrow_address, claim_statement) against the contract's own history —
    same "not a trust boundary" reasoning as OnChainSubmissionAck: nothing
    here verifies the hash is real, only the indexer reading actual chain
    state ever changes status_key/ruling.

    No ConsensusJob queued, no run_consensus — GenVM's own validator
    committee is the jury once adjudicate_dispute is actually called
    against this contract (a separate action from filing, not wired by
    this endpoint).

    Args:
        escrow_id (int):
        body (OnChainDisputeAck): Body for POST /escrows/{id}/dispute/on-chain — the frontend
            reporting a tx hash it already got back from signing and sending
            `NuanceDisputeCourt.file_dispute` itself (see components/app/
            genlayer-write-client.ts). Unlike OnChainSubmissionAck (which updates
            an existing Milestone), this one CREATES the local Dispute row
            immediately — file_dispute assigns the dispute's id on-chain, which
            isn't known yet at ack time. See services/genlayer_indexer.py's
            resolve_pending_dispute_ids for how on_chain_dispute_id gets filled in
            once the transaction actually lands. `issue` mirrors DisputeCreate's
            own optional-with-a-server-side-default behavior, and MUST match the
            `claim_statement` argument the frontend actually passed to
            file_dispute — the indexer matches on exact text equality, not fuzzy
            matching.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DisputeRead | HTTPValidationError
     """


    return (await asyncio_detailed(
        escrow_id=escrow_id,
client=client,
body=body,

    )).parsed
