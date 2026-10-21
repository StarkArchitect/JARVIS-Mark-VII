"""Brain: Multi-provider streaming client + tool loop + SQLite memory wiring.

Supports automatic fallback across free providers:
Google Gemini, Groq, OpenRouter, Mistral, Z.ai, and local Ollama.
"""

from __future__ import annotations

import json
import random
import time
from typing import Any, Callable

from .config import Config, get_providers
from .memory import Memory
from .persona import SYSTEM_PROMPT
from .tools import TOOL_SCHEMAS, ToolRegistry
from .utils import SentenceEmitter, get_logger, http_status

log = get_logger()


class Brain:
    """Streams replies, runs the tool loop across free providers, and persists memory."""

    def __init__(self, config: Config, memory: Memory) -> None:
        self.config = config
        self.memory = memory
        self.providers = get_providers(config)
        if not self.providers:
            raise RuntimeError(
                "No active API keys found in .env.\n"
                "Please configure at least GEMINI_API_KEY or GROQ_API_KEY."
            )
        self.registry = ToolRegistry(memory, config)
        self._summary = ""
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_requests = 0
        self.active_provider_label = self.providers[0]["label"]

    # ------------------------------------------------------------------ context

    def reset(self) -> None:
        self._summary = ""

    def build_history(self) -> list[dict]:
        """Rolling window over memory turns; dropped turns become a summary note."""
        limit = max(2, self.config.history_turns)
        all_turns = self.memory.recent(10_000)
        if len(all_turns) > limit:
            dropped = all_turns[:-limit]
            keep = all_turns[-limit:]
            recent_dropped = dropped[-8:]
            joined = "; ".join(
                f"{t['role']}: {t['content'][:120]}" for t in recent_dropped
            )
            self._summary = f"Earlier conversation summary: {joined}..."
        else:
            keep = all_turns
        return [{"role": t["role"], "content": t["content"]} for t in keep]

    def _system_prompt(self, user_text: str) -> str:
        parts = [SYSTEM_PROMPT]
        facts = self.memory.search(user_text, k=4)
        if facts:
            parts.append("Known user facts:\n- " + "\n- ".join(facts))
        if self._summary:
            parts.append(self._summary)
        return "\n\n".join(parts)

    # ------------------------------------------------------------------ provider cascade

    def _get_client_for_provider(self, prov: dict[str, Any]):
        from openai import OpenAI
        return OpenAI(
            base_url=prov["base_url"],
            api_key=prov["key"],
            default_headers=prov.get("headers") or None,
            timeout=40.0,
        )

    def _create_stream(self, prov: dict[str, Any], **kwargs):
        """Create a chat stream with retry and stream_options fallback."""
        client = self._get_client_for_provider(prov)
        include_usage = True
        for attempt in range(3):
            try:
                call_kwargs = dict(kwargs)
                call_kwargs["model"] = prov["model"]
                if include_usage:
                    call_kwargs["stream_options"] = {"include_usage": True}
                return client.chat.completions.create(**call_kwargs)
            except Exception as exc:  # noqa: BLE001
                if include_usage and "stream_options" in str(exc).lower():
                    include_usage = False
                    continue
                status = http_status(exc)
                retryable = status == 429 or (status is not None and 500 <= status < 600)
                if retryable and attempt < 2:
                    delay = (1.5 ** attempt) + random.uniform(0, 0.4)
                    log.warning("%s HTTP %s (attempt %d/3) - sleeping %.1fs",
                                prov["label"], status, attempt + 1, delay)
                    time.sleep(delay)
                    continue
                raise

    def _stream_once(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        tool_choice: str,
        on_sentence: Callable[[str], None] | None,
        on_token: Callable[[str], None] | None,
    ) -> tuple[str, list[dict], dict | None]:
        failures = []

        for prov in self.providers:
            kwargs: dict = {
                "messages": messages,
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
                "stream": True,
            }
            if tools is not None:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = tool_choice

            try:
                stream = self._create_stream(prov, **kwargs)
                content_parts: list[str] = []
                tc_map: dict[int, dict] = {}
                usage: dict | None = None
                emitter = SentenceEmitter(on_sentence) if on_sentence else None

                for chunk in stream:
                    if getattr(chunk, "usage", None):
                        u = chunk.usage
                        usage = {
                            "prompt_tokens": getattr(u, "prompt_tokens", 0) or 0,
                            "completion_tokens": getattr(u, "completion_tokens", 0) or 0,
                        }
                    if not getattr(chunk, "choices", None):
                        continue
                    delta = chunk.choices[0].delta
                    if getattr(delta, "tool_calls", None):
                        for d in delta.tool_calls:
                            entry = tc_map.setdefault(d.index, {"id": "", "name": "", "arguments": ""})
                            if d.id:
                                entry["id"] = d.id
                            if d.function and d.function.name:
                                entry["name"] = d.function.name
                            if d.function and d.function.arguments:
                                entry["arguments"] += d.function.arguments
                        emitter = None  # tool turn: suppress sentence callbacks
                        continue
                    token = delta.content or ""
                    if token:
                        content_parts.append(token)
                        if on_token:
                            on_token(token)
                        if emitter:
                            emitter.feed(token)

                if usage:
                    self.total_prompt_tokens += usage["prompt_tokens"]
                    self.total_completion_tokens += usage["completion_tokens"]
                    self.total_requests += 1

                if emitter:
                    emitter.flush()

                tool_calls = [
                    {"id": e["id"] or f"call_{i}", "type": "function",
                     "function": {"name": e["name"], "arguments": e["arguments"] or "{}"}}
                    for i, e in sorted(tc_map.items())
                ]
                self.active_provider_label = prov["label"]
                return "".join(content_parts), tool_calls, usage

            except Exception as exc:  # noqa: BLE001
                note = f"{prov['label']}: {type(exc).__name__}: {exc}"
                log.warning("Provider attempt failed -> %s", note)
                failures.append(note)
                continue

        raise RuntimeError("All providers failed:\n  " + "\n  ".join(failures))

    # ------------------------------------------------------------------ main loop

    def stream_reply(
        self,
        user_text: str,
        on_sentence: Callable[[str], None] | None = None,
        on_token: Callable[[str], None] | None = None,
    ) -> str:
        messages = [{"role": "system", "content": self._system_prompt(user_text)}]
        messages += self.build_history()
        messages.append({"role": "user", "content": user_text})

        final_text = ""
        max_iters = max(1, self.config.max_tool_iters)
        for iteration in range(max_iters + 1):
            last = iteration >= max_iters
            tool_choice = "none" if last else "auto"
            tools = TOOL_SCHEMAS if not last else None
            log.debug("tool loop iteration %d (choice=%s)", iteration, tool_choice)
            content, tool_calls, _ = self._stream_once(
                messages, tools, tool_choice, on_sentence, on_token
            )
            if not tool_calls:
                final_text = content
                break
            
            # Serialize assistant turn with tool_calls
            asst_msg: dict[str, Any] = {"role": "assistant"}
            if content:
                asst_msg["content"] = content
            else:
                asst_msg["content"] = None
            asst_msg["tool_calls"] = tool_calls
            messages.append(asst_msg)

            for tc in tool_calls:
                fname = tc["function"]["name"]
                try:
                    fargs = json.loads(tc["function"]["arguments"])
                    if not isinstance(fargs, dict):
                        fargs = {}
                except json.JSONDecodeError:
                    fargs = {}
                result = self.registry.dispatch(fname, fargs)
                log.debug("tool %s -> %s", fname, result[:200])
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": str(result)[:8000],
                })
        else:
            final_text = "(I reached the tool iteration limit without a final answer, sir.)"

        self.memory.add_turn("user", user_text)
        self.memory.add_turn("assistant", final_text)
        return final_text


# --------------------------------------------------------------------------- dry run

class MockBrain:
    """Offline stand-in with the same surface as Brain. No network calls."""

    def __init__(self, config: Config, memory: Memory) -> None:
        self.config = config
        self.memory = memory
        self._summary = ""
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_requests = 0
        self.active_provider_label = "Mock (Dry-Run)"

    def reset(self) -> None:
        self._summary = ""

    def build_history(self) -> list[dict]:
        return self.memory.recent(max(2, self.config.history_turns))

    def stream_reply(
        self,
        user_text: str,
        on_sentence: Callable[[str], None] | None = None,
        on_token: Callable[[str], None] | None = None,
    ) -> str:
        reply = (
            f"Dry-run mode, sir. All core plumbing is operational. "
            f"You requested: {user_text!r}."
        )
        if on_sentence:
            emitter = SentenceEmitter(on_sentence)
            for word in reply.split(" "):
                emitter.feed(word + " ")
            emitter.flush()
        if on_token:
            on_token(reply)
        self.total_requests += 1
        self.total_prompt_tokens += len(user_text) // 4
        self.total_completion_tokens += len(reply) // 4
        self.memory.add_turn("user", user_text)
        self.memory.add_turn("assistant", reply)
        return reply
