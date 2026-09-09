from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.dispute_evidence_read import DisputeEvidenceRead
from ...models.http_validation_error import HTTPValidationError
from ...models.on_chain_evidence_ack import OnChainEvidenceAck
from typing import cast



def _get_kwargs(
    dispute_id: int,
    *,
    body: OnChainEvidenceAck,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/disputes/{dispute_id}/evidence/on-chain".format(dispute_id=quote(str(dispute_id), safe=""),),
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
    body: OnChainEvidenceAck,

) -> Response[DisputeEvidenceRead | HTTPValidationError]:
    """ Submit Evidence On Chain

     The on-chain counterpart to submit_evidence above — reached once
    components/app/genlayer-write-client.ts's addEvidenceOnChain has
    already signed and sent a real NuanceDisputeCourt.add_evidence
    transaction. Added 2026-09-08 to close the actual gap that caused a
    real bug: before this endpoint existed, submitting evidence for ANY
    dispute — on-chain or not — always went through submit_evidence
    above, which always queues an off-chain ConsensusJob. That silently
    routed an on-chain-filed dispute's ruling through Nuance's own
    off-chain AI review instead of real GenVM validators, with nothing
    in the UI making the swap visible (found live, see contracts/
    nuance_dispute_court.py's add_evidence docstring for the full
    account).

    Unlike submit_evidence, this does NOT queue a ConsensusJob — real
    judgment happens via adjudicate_dispute on the contract itself
    (services/genlayer_indexer.py's trigger_pending_adjudications
    triggers it automatically once the dispute is open and matched).
    Still creates a local DisputeEvidence row purely so the evidence
    shows up in the UI's evidence list — same "not a trust boundary"
    reasoning as every other on-chain ack in this app: nothing here
    verifies the hash is real or that the contract call actually
    succeeded; only the indexer reading the contract's own ruling back
    is what actually matters.

    Args:
        dispute_id (int):
        body (OnChainEvidenceAck): Body for POST /disputes/{id}/evidence/on-chain — the frontend
            reporting a tx hash it already got back from signing and sending a
            real NuanceDisputeCourt.add_evidence transaction (components/app/
            genlayer-write-client.ts's addEvidenceOnChain). Unlike the off-chain
            submit_evidence, this does NOT queue a ConsensusJob — the real
            judgment happens via adjudicate_dispute on the contract itself
            (triggered automatically by services/genlayer_indexer.py, or
            manually). `evidence_url` is required (unlike the off-chain path's
            optional `link`) because the contract's own add_evidence only ever
            takes a URL — there's nowhere for free-text-only evidence to go
            on-chain (see that contract method's own docstring).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DisputeEvidenceRead | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        dispute_id=dispute_id,
body=body,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    dispute_id: int,
    *,
    client: AuthenticatedClient,
    body: OnChainEvidenceAck,

) -> DisputeEvidenceRead | HTTPValidationError | None:
    """ Submit Evidence On Chain

     The on-chain counterpart to submit_evidence above — reached once
    components/app/genlayer-write-client.ts's addEvidenceOnChain has
    already signed and sent a real NuanceDisputeCourt.add_evidence
    transaction. Added 2026-09-08 to close the actual gap that caused a
    real bug: before this endpoint existed, submitting evidence for ANY
    dispute — on-chain or not — always went through submit_evidence
    above, which always queues an off-chain ConsensusJob. That silently
    routed an on-chain-filed dispute's ruling through Nuance's own
    off-chain AI review instead of real GenVM validators, with nothing
    in the UI making the swap visible (found live, see contracts/
    nuance_dispute_court.py's add_evidence docstring for the full
    account).

    Unlike submit_evidence, this does NOT queue a ConsensusJob — real
    judgment happens via adjudicate_dispute on the contract itself
    (services/genlayer_indexer.py's trigger_pending_adjudications
    triggers it automatically once the dispute is open and matched).
    Still creates a local DisputeEvidence row purely so the evidence
    shows up in the UI's evidence list — same "not a trust boundary"
    reasoning as every other on-chain ack in this app: nothing here
    verifies the hash is real or that the contract call actually
    succeeded; only the indexer reading the contract's own ruling back
    is what actually matters.

    Args:
        dispute_id (int):
        body (OnChainEvidenceAck): Body for POST /disputes/{id}/evidence/on-chain — the frontend
            reporting a tx hash it already got back from signing and sending a
            real NuanceDisputeCourt.add_evidence transaction (components/app/
            genlayer-write-client.ts's addEvidenceOnChain). Unlike the off-chain
            submit_evidence, this does NOT queue a ConsensusJob — the real
            judgment happens via adjudicate_dispute on the contract itself
            (triggered automatically by services/genlayer_indexer.py, or
            manually). `evidence_url` is required (unlike the off-chain path's
            optional `link`) because the contract's own add_evidence only ever
            takes a URL — there's nowhere for free-text-only evidence to go
            on-chain (see that contract method's own docstring).

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

    ).parsed

async def asyncio_detailed(
    dispute_id: int,
    *,
    client: AuthenticatedClient,
    body: OnChainEvidenceAck,

) -> Response[DisputeEvidenceRead | HTTPValidationError]:
    """ Submit Evidence On Chain

     The on-chain counterpart to submit_evidence above — reached once
    components/app/genlayer-write-client.ts's addEvidenceOnChain has
    already signed and sent a real NuanceDisputeCourt.add_evidence
    transaction. Added 2026-09-08 to close the actual gap that caused a
    real bug: before this endpoint existed, submitting evidence for ANY
    dispute — on-chain or not — always went through submit_evidence
    above, which always queues an off-chain ConsensusJob. That silently
    routed an on-chain-filed dispute's ruling through Nuance's own
    off-chain AI review instead of real GenVM validators, with nothing
    in the UI making the swap visible (found live, see contracts/
    nuance_dispute_court.py's add_evidence docstring for the full
    account).

    Unlike submit_evidence, this does NOT queue a ConsensusJob — real
    judgment happens via adjudicate_dispute on the contract itself
    (services/genlayer_indexer.py's trigger_pending_adjudications
    triggers it automatically once the dispute is open and matched).
    Still creates a local DisputeEvidence row purely so the evidence
    shows up in the UI's evidence list — same "not a trust boundary"
    reasoning as every other on-chain ack in this app: nothing here
    verifies the hash is real or that the contract call actually
    succeeded; only the indexer reading the contract's own ruling back
    is what actually matters.

    Args:
        dispute_id (int):
        body (OnChainEvidenceAck): Body for POST /disputes/{id}/evidence/on-chain — the frontend
            reporting a tx hash it already got back from signing and sending a
            real NuanceDisputeCourt.add_evidence transaction (components/app/
            genlayer-write-client.ts's addEvidenceOnChain). Unlike the off-chain
            submit_evidence, this does NOT queue a ConsensusJob — the real
            judgment happens via adjudicate_dispute on the contract itself
            (triggered automatically by services/genlayer_indexer.py, or
            manually). `evidence_url` is required (unlike the off-chain path's
            optional `link`) because the contract's own add_evidence only ever
            takes a URL — there's nowhere for free-text-only evidence to go
            on-chain (see that contract method's own docstring).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DisputeEvidenceRead | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        dispute_id=dispute_id,
body=body,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    dispute_id: int,
    *,
    client: AuthenticatedClient,
    body: OnChainEvidenceAck,

) -> DisputeEvidenceRead | HTTPValidationError | None:
    """ Submit Evidence On Chain

     The on-chain counterpart to submit_evidence above — reached once
    components/app/genlayer-write-client.ts's addEvidenceOnChain has
    already signed and sent a real NuanceDisputeCourt.add_evidence
    transaction. Added 2026-09-08 to close the actual gap that caused a
    real bug: before this endpoint existed, submitting evidence for ANY
    dispute — on-chain or not — always went through submit_evidence
    above, which always queues an off-chain ConsensusJob. That silently
    routed an on-chain-filed dispute's ruling through Nuance's own
    off-chain AI review instead of real GenVM validators, with nothing
    in the UI making the swap visible (found live, see contracts/
    nuance_dispute_court.py's add_evidence docstring for the full
    account).

    Unlike submit_evidence, this does NOT queue a ConsensusJob — real
    judgment happens via adjudicate_dispute on the contract itself
    (services/genlayer_indexer.py's trigger_pending_adjudications
    triggers it automatically once the dispute is open and matched).
    Still creates a local DisputeEvidence row purely so the evidence
    shows up in the UI's evidence list — same "not a trust boundary"
    reasoning as every other on-chain ack in this app: nothing here
    verifies the hash is real or that the contract call actually
    succeeded; only the indexer reading the contract's own ruling back
    is what actually matters.

    Args:
        dispute_id (int):
        body (OnChainEvidenceAck): Body for POST /disputes/{id}/evidence/on-chain — the frontend
            reporting a tx hash it already got back from signing and sending a
            real NuanceDisputeCourt.add_evidence transaction (components/app/
            genlayer-write-client.ts's addEvidenceOnChain). Unlike the off-chain
            submit_evidence, this does NOT queue a ConsensusJob — the real
            judgment happens via adjudicate_dispute on the contract itself
            (triggered automatically by services/genlayer_indexer.py, or
            manually). `evidence_url` is required (unlike the off-chain path's
            optional `link`) because the contract's own add_evidence only ever
            takes a URL — there's nowhere for free-text-only evidence to go
            on-chain (see that contract method's own docstring).

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

    )).parsed
