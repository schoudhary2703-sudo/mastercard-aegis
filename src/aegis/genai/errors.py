"""Failure modes of the GenAI reasoning layer.

Every one of these is loud on purpose. The single most dangerous outcome for
this project would be a GenAI stage that quietly degrades into canned text and
is then presented to a judge as model reasoning, so there is no "fall back to
a default answer" path anywhere in `aegis.genai`: a stage either produces a
schema-valid response from a named provider, or it raises.
"""

from __future__ import annotations


class GenAIError(Exception):
    """Base class for every GenAI-layer failure."""


class GenAIConfigurationError(GenAIError):
    """Provider is unusable as configured (missing key, unknown provider name).

    Raised before any network call. Never downgraded to an offline response --
    choosing recorded mode is an explicit caller decision, not a fallback.
    """


class GenAIProviderError(GenAIError):
    """The provider was reachable but the call failed (API error, timeout).

    Carries `attempts` so a persisted failure artifact can record how many
    times the call was retried before giving up.
    """

    def __init__(self, message: str, *, attempts: int = 1) -> None:
        super().__init__(message)
        self.attempts = attempts


class GenAISchemaError(GenAIError):
    """The provider replied, but the reply is not a valid structured response.

    The offending raw text is kept on the exception so the failure artifact can
    persist exactly what came back, rather than a summary of it.
    """

    def __init__(self, message: str, *, raw_text: str = "") -> None:
        super().__init__(message)
        self.raw_text = raw_text


class MutationBoundsError(GenAIError):
    """A proposed mutation falls outside what the blueprint permits.

    The blind-spot analyst may only propose changes to parameters the
    blueprint itself declares mutable, within the magnitude ceiling in
    `aegis.genai.contracts`. This is what keeps a language model from widening
    the simulator's search space by asking nicely.
    """


__all__ = [
    "GenAIConfigurationError",
    "GenAIError",
    "GenAIProviderError",
    "GenAISchemaError",
    "MutationBoundsError",
]
