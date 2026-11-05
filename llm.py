"""
llm.py — Shared Claude call helper: model IDs, thinking settings, text extraction.

Thinking is turned off on every call: these are one-shot writing/formatting tasks
and thinking tokens would only add cost. Sonnet calls also opt into server-side
refusal fallbacks, so a declined story is retried on another model automatically.
"""

SONNET = "claude-sonnet-5-5"
HAIKU  = "claude-haiku-5-5"
SONNET_HEADROOM = 4000   # extra max_tokens for any pre-answer reasoning (only used tokens are billed)


def ask(client, model: str, content, max_tokens: int, system: str | None = None) -> str:
    """Send one user message and return Claude's text reply."""
    kwargs = {"model": model, "max_tokens": max_tokens,
              "messages": [{"role": "user", "content": content}]}
    if system:
        kwargs["system"] = system

    if model == SONNET:
        # Sonnet 5.5 can still reason briefly before answering (e.g. on images), so
        # keep effort low and leave headroom so that never eats the reply itself.
        kwargs["max_tokens"] += SONNET_HEADROOM
        response = client.beta.messages.create(
            **kwargs,
            thinking={"type": "between_tools"},
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"],
            extra_body={"fallbacks": "default"},
        )
    else:
        response = client.messages.create(**kwargs, thinking={"type": "disabled"})

    if response.stop_reason == "refusal":
        raise RuntimeError(f"Claude declined the request ({model})")
    texts = [b.text for b in response.content if b.type == "text"]
    if not texts:
        raise RuntimeError(f"No text in Claude reply (stop_reason={response.stop_reason}, "
                           f"blocks={[b.type for b in response.content]})")
    return "".join(texts)
