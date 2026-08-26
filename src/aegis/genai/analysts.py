"""The two GenAI reasoning stages, end to end.

Each stage does the same four things: render a versioned prompt, call the
configured provider, validate the reply against a typed schema, and persist a
run artifact carrying full provenance. Validation and bounds-checking live
here rather than in the provider so that swapping providers cannot change how
strictly a response is policed.

Where GenAI sits in the loop:

    research / taxonomy
      -> GenAI ATTACK ANALYST        (this module)
      -> structured blueprint parameters
      -> deterministic constrained simulator   (aegis.generate)
      -> XGBoost defender                       (aegis.defend)
      -> evasion / fidelity feedback            (aegis.evaluate)
      -> GenAI BLIND-SPOT ANALYST    (this module)
      -> bounded mutation proposal
      -> next simulation

The two GenAI stages bracket the deterministic core; they never replace any
part of it. Nothing in this module generates a transaction, fits a model, or
computes a metric.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar

from pydantic import ValidationError

from aegis.genai.artifacts import build_run_id, write_run_artifact
from aegis.genai.contracts import (
    AttackAnalystRequest,
    AttackAnalystResponse,
    BlindSpotAnalystRequest,
    BlindSpotAnalystResponse,
    GenAIProvenance,
    GenAIRunArtifact,
)
from aegis.genai.errors import GenAIProviderError, GenAISchemaError, MutationBoundsError
from aegis.genai.prompts import (
    PROMPT_VERSION,
    attack_analyst_system_prompt,
    attack_analyst_user_prompt,
    blind_spot_analyst_system_prompt,
    blind_spot_analyst_user_prompt,
)
from aegis.genai.provider import GenAIProvider
from aegis.shared.base import AegisModel

ATTACK_ANALYST_STAGE = "attack_analyst"
BLIND_SPOT_ANALYST_STAGE = "blind_spot_analyst"

_ResponseT = TypeVar("_ResponseT", bound=AegisModel)


class GenAIRunOutcome:
    """A completed stage: the validated response plus where it was persisted."""

    def __init__(
        self,
        *,
        response: Any,
        artifact: GenAIRunArtifact,
        artifact_path: Path,
    ) -> None:
        self.response = response
        self.artifact = artifact
        self.artifact_path = artifact_path


def _strip_code_fence(text: str) -> str:
    """Tolerate a ```json fence without tolerating arbitrary prose.

    Fencing is a formatting habit, not a semantic failure; anything else that
    is not parseable JSON is still rejected.
    """
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) < 2:
        return stripped
    body = lines[1:]
    if body and body[-1].strip().startswith("```"):
        body = body[:-1]
    return "\n".join(body).strip()


def _parse_response(raw_text: str, model_cls: type[_ResponseT]) -> _ResponseT:
    """Parse and validate, or raise `GenAISchemaError` carrying the raw text."""
    candidate = _strip_code_fence(raw_text)
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        msg = f"response is not valid JSON: {exc}"
        raise GenAISchemaError(msg, raw_text=raw_text) from exc
    if not isinstance(payload, dict):
        msg = f"response JSON must be an object, got {type(payload).__name__}"
        raise GenAISchemaError(msg, raw_text=raw_text)
    try:
        return model_cls.model_validate(payload)
    except ValidationError as exc:
        msg = f"response does not match {model_cls.__name__}: {exc}"
        raise GenAISchemaError(msg, raw_text=raw_text) from exc


def enforce_mutation_bounds(
    response: BlindSpotAnalystResponse, allowed_parameters: list[str]
) -> None:
    """Reject proposals that touch parameters the blueprint did not open up.

    Magnitude ceilings are already enforced by `BoundedMutationProposal`'s
    field constraints; what cannot be expressed there is the per-blueprint
    allow-list, because it varies per request. Both halves must hold before a
    proposal is allowed to reach `loop/`.
    """
    if not allowed_parameters:
        if response.mutation_proposals:
            msg = (
                "mutation proposals were returned but the blueprint declares no mutable "
                "parameters"
            )
            raise MutationBoundsError(msg)
        return
    allowed = set(allowed_parameters)
    offenders = sorted(
        {p.parameter for p in response.mutation_proposals if p.parameter not in allowed}
    )
    if offenders:
        msg = (
            f"mutation proposals reference non-mutable parameter(s) {offenders}; "
            f"allowed: {sorted(allowed)}"
        )
        raise MutationBoundsError(msg)


def _persist(
    *,
    root: Path,
    stage: str,
    request_payload: dict[str, Any],
    provider: GenAIProvider,
    prompt_version: str,
    live: bool,
    request_id: str | None,
    latency_ms: float | None,
    attempts: int,
    source_artifacts: list[str],
    response_payload: dict[str, Any] | None,
    schema_valid: bool,
    failure: str | None,
    raw_response_text: str | None,
) -> tuple[GenAIRunArtifact, Path]:
    artifact = GenAIRunArtifact(
        run_id=build_run_id(
            stage=stage,
            request=request_payload,
            prompt_version=prompt_version,
            model=provider.model,
        ),
        stage=stage,
        provenance=GenAIProvenance(
            provider=provider.name,
            model=provider.model,
            prompt_version=prompt_version,
            live=live,
            request_id=request_id,
            latency_ms=latency_ms,
            attempts=attempts,
            source_artifacts=source_artifacts,
        ),
        request=request_payload,
        response=response_payload,
        schema_valid=schema_valid,
        failure=failure,
        raw_response_text=raw_response_text,
    )
    return artifact, write_run_artifact(root, artifact)


def run_attack_analyst(
    request: AttackAnalystRequest,
    provider: GenAIProvider,
    *,
    root: Path,
    source_artifacts: list[str] | None = None,
) -> GenAIRunOutcome:
    """Stage 1: researched taxonomy scenario -> structured attack hypothesis.

    On provider failure or schema-validation failure this persists a failure
    artifact and re-raises. It never returns a placeholder response.
    """
    request_payload = request.model_dump(mode="json")
    sources = list(source_artifacts or [])

    try:
        result = provider.complete_json(
            system_prompt=attack_analyst_system_prompt(),
            user_prompt=attack_analyst_user_prompt(request),
            schema_name="attack_analyst_response",
            json_schema=AttackAnalystResponse.model_json_schema(),
        )
    except GenAIProviderError as exc:
        _persist(
            root=root,
            stage=ATTACK_ANALYST_STAGE,
            request_payload=request_payload,
            provider=provider,
            prompt_version=PROMPT_VERSION,
            live=True,
            request_id=None,
            latency_ms=None,
            attempts=exc.attempts,
            source_artifacts=sources,
            response_payload=None,
            schema_valid=False,
            failure=f"provider_error: {exc}",
            raw_response_text=None,
        )
        raise

    try:
        response = _parse_response(result.text, AttackAnalystResponse)
    except GenAISchemaError as exc:
        _persist(
            root=root,
            stage=ATTACK_ANALYST_STAGE,
            request_payload=request_payload,
            provider=provider,
            prompt_version=PROMPT_VERSION,
            live=result.live,
            request_id=result.request_id,
            latency_ms=result.latency_ms,
            attempts=result.attempts,
            source_artifacts=sources,
            response_payload=None,
            schema_valid=False,
            failure=f"schema_error: {exc}",
            raw_response_text=exc.raw_text,
        )
        raise

    artifact, path = _persist(
        root=root,
        stage=ATTACK_ANALYST_STAGE,
        request_payload=request_payload,
        provider=provider,
        prompt_version=PROMPT_VERSION,
        live=result.live,
        request_id=result.request_id,
        latency_ms=result.latency_ms,
        attempts=result.attempts,
        source_artifacts=sources,
        response_payload=response.model_dump(mode="json"),
        schema_valid=True,
        failure=None,
        raw_response_text=None,
    )
    return GenAIRunOutcome(response=response, artifact=artifact, artifact_path=path)


def run_blind_spot_analyst(
    request: BlindSpotAnalystRequest,
    provider: GenAIProvider,
    *,
    root: Path,
    source_artifacts: list[str] | None = None,
) -> GenAIRunOutcome:
    """Stage 2: real detector failures -> bounded mutation proposals.

    Out-of-bounds proposals are a *rejection*, not a clamp: silently shrinking
    an over-large magnitude would let the model steer the search space while
    appearing compliant on disk.
    """
    request_payload = request.model_dump(mode="json")
    sources = list(source_artifacts or [])

    try:
        result = provider.complete_json(
            system_prompt=blind_spot_analyst_system_prompt(),
            user_prompt=blind_spot_analyst_user_prompt(request),
            schema_name="blind_spot_analyst_response",
            json_schema=BlindSpotAnalystResponse.model_json_schema(),
        )
    except GenAIProviderError as exc:
        _persist(
            root=root,
            stage=BLIND_SPOT_ANALYST_STAGE,
            request_payload=request_payload,
            provider=provider,
            prompt_version=PROMPT_VERSION,
            live=True,
            request_id=None,
            latency_ms=None,
            attempts=exc.attempts,
            source_artifacts=sources,
            response_payload=None,
            schema_valid=False,
            failure=f"provider_error: {exc}",
            raw_response_text=None,
        )
        raise

    try:
        response = _parse_response(result.text, BlindSpotAnalystResponse)
        enforce_mutation_bounds(response, request.mutable_parameters)
    except (GenAISchemaError, MutationBoundsError) as exc:
        raw = exc.raw_text if isinstance(exc, GenAISchemaError) else result.text
        kind = "schema_error" if isinstance(exc, GenAISchemaError) else "mutation_bounds_error"
        _persist(
            root=root,
            stage=BLIND_SPOT_ANALYST_STAGE,
            request_payload=request_payload,
            provider=provider,
            prompt_version=PROMPT_VERSION,
            live=result.live,
            request_id=result.request_id,
            latency_ms=result.latency_ms,
            attempts=result.attempts,
            source_artifacts=sources,
            response_payload=None,
            schema_valid=False,
            failure=f"{kind}: {exc}",
            raw_response_text=raw,
        )
        raise

    artifact, path = _persist(
        root=root,
        stage=BLIND_SPOT_ANALYST_STAGE,
        request_payload=request_payload,
        provider=provider,
        prompt_version=PROMPT_VERSION,
        live=result.live,
        request_id=result.request_id,
        latency_ms=result.latency_ms,
        attempts=result.attempts,
        source_artifacts=sources,
        response_payload=response.model_dump(mode="json"),
        schema_valid=True,
        failure=None,
        raw_response_text=None,
    )
    return GenAIRunOutcome(response=response, artifact=artifact, artifact_path=path)


__all__ = [
    "ATTACK_ANALYST_STAGE",
    "BLIND_SPOT_ANALYST_STAGE",
    "GenAIRunOutcome",
    "enforce_mutation_bounds",
    "run_attack_analyst",
    "run_blind_spot_analyst",
]
