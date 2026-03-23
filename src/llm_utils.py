# -*- coding: utf-8 -*-
"""
Shared LLM call utilities with automatic continuation for truncated output.
"""


def call_llm_with_continuation(
    provider,
    prompt: str,
    images=None,
    max_tokens: int = 8192,
    max_continuations: int = 3,
    system: str = None,
) -> str:
    """
    Call LLM and automatically continue if JSON output is truncated.

    Args:
        provider: LLM provider with generate() method
        prompt: The prompt to send
        images: Optional images for vision models
        max_tokens: Max tokens per call
        max_continuations: Max continuation attempts (0 = no continuation)
        system: Optional system prompt (cached by ClaudeProvider for cost savings)

    Returns:
        Complete (or best-effort) LLM response text
    """
    extra_kwargs = {}
    if system:
        extra_kwargs["system"] = system

    if images and hasattr(provider, "generate_with_images"):
        resp = provider.generate_with_images(prompt, images, max_tokens=max_tokens, **extra_kwargs)
    else:
        resp = provider.generate(prompt, max_tokens=max_tokens, **extra_kwargs)

    for attempt in range(max_continuations):
        if json_looks_complete(resp):
            break
        print(f"    - output truncated, continuing ({attempt+1}/{max_continuations})...")
        cont_prompt = (
            "你的上一次输出被截断了，请从截断处继续输出（不要重复已输出的内容）。"
            f"\n\n已输出的末尾：\n...{resp[-500:]}"
        )
        cont = provider.generate(cont_prompt, max_tokens=max_tokens, **extra_kwargs)
        # Strip any preamble text before the JSON continuation fragment
        first_json_char = len(cont)
        for i, ch in enumerate(cont):
            if ch in ('{', '[', '"'):
                first_json_char = i
                break
        resp = resp + cont[first_json_char:]
    else:
        # Loop exhausted without break — JSON still incomplete
        if max_continuations > 0 and not json_looks_complete(resp):
            print(f"    - [WARNING] JSON still incomplete after {max_continuations} continuations")

    return resp


def json_looks_complete(text: str) -> bool:
    """Check if the JSON in text has balanced brackets."""
    start = -1
    for i, ch in enumerate(text):
        if ch in ('{', '['):
            start = i
            break
    if start < 0:
        return False  # No JSON found, treat as incomplete

    depth_brace = 0
    depth_bracket = 0
    in_string = False
    escape_next = False

    for ch in text[start:]:
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            depth_brace += 1
        elif ch == '}':
            depth_brace -= 1
        elif ch == '[':
            depth_bracket += 1
        elif ch == ']':
            depth_bracket -= 1

    return depth_brace == 0 and depth_bracket == 0
