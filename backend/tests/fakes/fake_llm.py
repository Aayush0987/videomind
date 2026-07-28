"""In-memory stand-in for app.core.llm.generate/generate_structured (§18.1).

Never touches the network. Monkeypatch `app.core.llm.generate` /
`app.core.llm.generate_structured` with a `FakeLLM` instance's bound methods
in unit tests; the same instance is injected via FastAPI dependency override
starting in Phase 8.
"""

from dataclasses import dataclass
from typing import Any, TypeVar

from app.core.errors import StructuredOutputError
from app.core.llm import LLMConfig
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass
class CallRecord:
    kind: str  # "generate" | "generate_structured"
    prompt: str
    schema: type[BaseModel] | None


class FakeLLM:
    def __init__(self) -> None:
        self.responses: dict[str, Any] = {}
        self.call_log: list[CallRecord] = []
        self._pending_failure: Exception | None = None
        self._pending_invalid_json = False
        self._pending_schema_violation = False

    def fail_next(self, exc: Exception) -> None:
        self._pending_failure = exc

    def return_invalid_json_next(self) -> None:
        self._pending_invalid_json = True

    def return_schema_violation_next(self) -> None:
        self._pending_schema_violation = True

    async def generate(self, prompt: str, cfg: LLMConfig, *, system: str | None = None) -> str:
        self.call_log.append(CallRecord("generate", prompt, None))
        self._raise_if_pending(schema=None)
        response = self.responses.get(prompt)
        if response is None:
            raise KeyError(f"FakeLLM has no canned response registered for prompt {prompt!r}.")
        return response if isinstance(response, str) else response.model_dump_json()

    async def generate_structured(
        self,
        prompt: str,
        cfg: LLMConfig,
        schema: type[T],
        *,
        system: str | None = None,
        repair_attempts: int = 1,
    ) -> T:
        self.call_log.append(CallRecord("generate_structured", prompt, schema))
        self._raise_if_pending(schema=schema)
        response = self.responses.get(prompt, self.responses.get(schema.__name__))
        if response is None:
            raise KeyError(
                f"FakeLLM has no canned response for prompt {prompt!r} "
                f"or schema {schema.__name__!r}."
            )
        if isinstance(response, schema):
            return response
        if isinstance(response, str):
            return schema.model_validate_json(response)
        raise TypeError(
            f"FakeLLM response for {schema.__name__!r} is not a {schema.__name__} or str."
        )

    def _raise_if_pending(self, *, schema: type[BaseModel] | None) -> None:
        if self._pending_failure is not None:
            exc, self._pending_failure = self._pending_failure, None
            raise exc
        if self._pending_invalid_json:
            self._pending_invalid_json = False
            raise StructuredOutputError(
                f"FakeLLM: invalid JSON injected for {schema.__name__ if schema else 'generate'}."
            )
        if self._pending_schema_violation:
            self._pending_schema_violation = False
            name = schema.__name__ if schema else "generate"
            raise StructuredOutputError(f"FakeLLM: schema violation injected for {name}.")
