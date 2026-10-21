"""LLM router: tries each free provider in order, runs the tool-calling loop."""
import json
import logging
import time

from openai import OpenAI

import config

log = logging.getLogger("jarvis.brain")


class AllProvidersFailed(RuntimeError):
    pass


def _serialize(msg) -> dict:
    """Convert an SDK message object into a plain dict the API will accept back."""
    out = {"role": "assistant"}
    if msg.content is not None:
        out["content"] = msg.content
    calls = getattr(msg, "tool_calls", None)
    if calls:
        out["tool_calls"] = [
            {"id": c.id, "type": "function",
             "function": {"name": c.function.name,
                          "arguments": c.function.arguments}}
            for c in calls
        ]
        if "content" not in out:
            out["content"] = None
    elif "content" not in out:
        out["content"] = ""
    return out


class Brain:
    def __init__(self, system_prompt: str):
        self.system_prompt = system_prompt
        self.last_provider = None

    # ------------------------------------------------------------------
    def think(self, history: list[dict], tools: list[dict], executor) -> str:
        if not config.PROVIDERS:
            raise AllProvidersFailed(
                "No API keys found. Put at least GROQ_API_KEY or GEMINI_API_KEY in .env")

        messages = [{"role": "system", "content": self.system_prompt}, *history]
        failures = []

        for prov in config.PROVIDERS:
            try:
                text = self._run_provider(prov, messages, tools, executor)
                self.last_provider = prov["label"]
                return text
            except Exception as exc:                      # noqa: BLE001
                note = f"{prov['label']}: {type(exc).__name__}: {exc}"
                failures.append(note)
                if config.VERBOSE:
                    log.warning("provider failed -> %s", note)

        raise AllProvidersFailed("All providers failed:\n  " + "\n  ".join(failures))

    # ------------------------------------------------------------------
    def _run_provider(self, prov, messages, tools, executor) -> str:
        client = OpenAI(
            api_key=prov["key"],
            base_url=prov["base_url"],
            default_headers=prov.get("headers") or None,
            timeout=90.0,
            max_retries=0,
        )
        convo = list(messages)

        for _ in range(config.MAX_TOOL_ROUNDS):
            resp = self._call(client, prov, convo, tools)
            msg = resp.choices[0].message
            calls = getattr(msg, "tool_calls", None)

            if not calls:
                return (msg.content or "").strip()

            convo.append(_serialize(msg))

            for call in calls:
                name = call.function.name
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                log.debug("tool -> %s(%s)", name, args)
                result = executor(name, args)
                convo.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": (json.dumps(result, ensure_ascii=False) if isinstance(result, (dict, list)) else str(result))[:8000],
                })

        # ran out of tool rounds -> force a plain answer
        resp = self._call(client, prov, convo, None)
        return (resp.choices[0].message.content or "").strip()

    # ------------------------------------------------------------------
    @staticmethod
    def _call(client, prov, messages, tools):
        kwargs = {
            "model": prov["model"],
            "messages": messages,
            "temperature": config.TEMPERATURE,
            "max_tokens": config.MAX_TOKENS,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        last = None
        for attempt in range(3):
            try:
                return client.chat.completions.create(**kwargs)
            except Exception as exc:                      # noqa: BLE001
                last = exc
                blob = str(exc).lower()
                if ("429" in blob or "rate" in blob or "overload" in blob) and attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise
        raise last