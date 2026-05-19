# -*- coding: utf-8 -*-
"""
Shared LLM call utilities with automatic continuation for truncated output.
"""

import time


def call_llm_with_continuation(
    provider,
    prompt: str,
    images=None,
    max_tokens: int = 8192,
    max_continuations: int = 3,
) -> str:
    """
    Call LLM and automatically continue if JSON output is truncated.

    Args:
        provider: LLM provider with generate() method
        prompt: The prompt to send
        images: Optional images for vision models
        max_tokens: Max tokens per call
        max_continuations: Max continuation attempts (0 = no continuation)

    Returns:
        Complete (or best-effort) LLM response text
    """
    try:
        import openai  # type: ignore
        timeout_error_type = openai.APITimeoutError
    except Exception:
        timeout_error_type = None

    def is_timeout_error(exc: Exception) -> bool:
        if timeout_error_type and isinstance(exc, timeout_error_type):
            return True
        message = str(exc).lower()
        return "timeout" in message or "timed out" in message or "readtimeout" in message

    last_error = None
    for attempt in range(3):
        try:
            print(f"    [发送LLM请求... streaming模式]", flush=True)
            start = time.time()
            if images and hasattr(provider, "generate_with_images"):
                resp = provider.generate_with_images(prompt, images, max_tokens=max_tokens)
            else:
                resp = provider.generate(prompt, max_tokens=max_tokens)
            elapsed = int(time.time() - start)
            print(f"    [LLM响应] 收到 {len(resp)} 字符 (用时 {elapsed}s)", flush=True)
            break
        except Exception as exc:
            last_error = exc
            if not is_timeout_error(exc) or attempt >= 2:
                raise
            print(f"  [WARNING] LLM 请求超时/中断，正在重试({attempt + 1}/2)...", flush=True)
    else:
        raise last_error

    for attempt in range(max_continuations):
        if json_looks_complete(resp):
            break
        print(f"    - [续写] 输出被截断，正在发起续写请求 ({attempt+1}/{max_continuations})...", flush=True)
        print(f"    - [续写] 当前响应长度: {len(resp)} 字符", flush=True)
        cont_prompt = (
            "你的上一次输出被截断了，请从截断处继续输出（不要重复已输出的内容）。"
            f"\n\n已输出的末尾：\n...{resp[-500:]}"
        )
        print(f"    [发送续写请求... streaming模式]", flush=True)
        cont = provider.generate(cont_prompt, max_tokens=max_tokens)
        print(f"    - [续写] 收到续写响应: {len(cont)} 字符", flush=True)
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
            print(f"    - [WARNING] JSON经过{max_continuations}次续写仍不完整（总长度: {len(resp)} 字符）", flush=True)

    print(f"    [LLM完成] 最终响应: {len(resp)} 字符, JSON完整: {json_looks_complete(resp)}", flush=True)
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
