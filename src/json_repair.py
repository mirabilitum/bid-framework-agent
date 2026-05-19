# -*- coding: utf-8 -*-
"""
JSON repair utilities for handling malformed LLM output.
"""

import re
import json
import os
import tempfile


def repair_json(json_str: str) -> str:
    """
    Attempt to repair common JSON formatting issues from LLM output.
    """
    # 1. Remove trailing commas before } or ]
    json_str = re.sub(r',\s*([}\]])', r'\1', json_str)

    # 2. Fix truncated JSON: close unclosed brackets
    json_str = _close_unclosed_brackets(json_str)

    # 3. Escape unescaped control chars inside strings
    json_str = _escape_control_chars(json_str)

    return json_str


def _close_unclosed_brackets(json_str: str) -> str:
    """If JSON is truncated (LLM hit token limit), close unclosed brackets."""
    depth_brace = 0
    depth_bracket = 0
    bracket_stack = []
    in_string = False
    escape_next = False

    for ch in json_str:
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
            bracket_stack.append('{')
        elif ch == '}':
            depth_brace = max(0, depth_brace - 1)
            if bracket_stack and bracket_stack[-1] == '{':
                bracket_stack.pop()
        elif ch == '[':
            depth_bracket += 1
            bracket_stack.append('[')
        elif ch == ']':
            depth_bracket = max(0, depth_bracket - 1)
            if bracket_stack and bracket_stack[-1] == '[':
                bracket_stack.pop()

    # If unclosed, try to close them
    if depth_brace > 0 or depth_bracket > 0:
        # Strip trailing incomplete content (partial string, trailing comma)
        stripped = json_str.rstrip()
        # Remove trailing comma if present
        if stripped.endswith(','):
            stripped = stripped[:-1]
        # Remove incomplete string (ends with unclosed quote)
        # Count quotes to check
        quote_count = 0
        esc = False
        for c in stripped:
            if esc:
                esc = False
                continue
            if c == '\\':
                esc = True
                continue
            if c == '"':
                quote_count += 1
        if quote_count % 2 != 0:
            # Odd quotes - find last quote and truncate after it, adding closing quote
            last_q = stripped.rfind('"')
            stripped = stripped[:last_q + 1]

        # Now close brackets using stack order (correct nesting)
        suffix = ''.join('}' if b == '{' else ']' for b in reversed(bracket_stack))
        stripped += suffix
        return stripped

    return json_str


def _escape_control_chars(json_str: str) -> str:
    """Escape unescaped control characters inside JSON strings."""
    result = []
    in_string = False
    escape_next = False
    for ch in json_str:
        if escape_next:
            result.append(ch)
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            result.append(ch)
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            continue
        if in_string:
            if ch == '\n':
                result.append('\\n')
                continue
            if ch == '\t':
                result.append('\\t')
                continue
            if ch == '\r':
                continue
        result.append(ch)
    return ''.join(result)


def _save_debug_response(response: str, label: str) -> str:
    """Save raw LLM response to temp file for debugging. Returns path."""
    try:
        debug_dir = os.path.join(tempfile.gettempdir(), "bid_framework_debug")
        os.makedirs(debug_dir, exist_ok=True)
        path = os.path.join(debug_dir, f"llm_response_{label}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(response)
        return path
    except Exception:
        return ""


def extract_and_parse_json(response: str, label: str = "unknown", expect_array: bool = False):
    """
    Extract JSON from LLM response text, with repair on failure.

    Args:
        response: Raw LLM response text
        label: Label for debug output
        expect_array: If True, look for JSON array [...] first

    Returns:
        dict or list depending on JSON content
    """
    json_str = _extract_json_str(response, prefer_array=expect_array)

    # First attempt
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    # Second attempt: repair
    repaired = repair_json(json_str)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError as e:
        # Save debug file
        debug_path = _save_debug_response(response, label)
        debug_msg = f"\n原始响应已保存到: {debug_path}" if debug_path else ""

        error_pos = e.pos if hasattr(e, 'pos') else -1
        if error_pos >= 0:
            start = max(0, error_pos - 150)
            end = min(len(repaired), error_pos + 150)
            context = repaired[start:end]
            raise ValueError(
                f"LLM返回的JSON修复后仍无法解析。\n"
                f"错误: {str(e)}\n"
                f"错误位置附近: ...{context}..."
                f"{debug_msg}"
            )
        raise ValueError(
            f"LLM返回的JSON修复后仍无法解析。\n"
            f"错误: {str(e)}"
            f"{debug_msg}"
        )


def _extract_json_str(response: str, prefer_array: bool = False) -> str:
    """Extract JSON string (object or array) from LLM response."""
    # Try markdown code block first
    code_block = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', response, re.DOTALL)
    if code_block:
        candidate = code_block.group(1).strip()
        if candidate.startswith("{") or candidate.startswith("["):
            return candidate

    # Determine which bracket to look for
    brace_pos = response.find("{")
    bracket_pos = response.find("[")

    if prefer_array and bracket_pos >= 0:
        # For arrays: prefer [ unless { comes first and looks like a wrapper object
        if brace_pos < 0 or bracket_pos < brace_pos:
            return _match_brackets(response, bracket_pos, "[", "]")

    if brace_pos >= 0:
        return _match_brackets(response, brace_pos, "{", "}")

    if bracket_pos >= 0:
        return _match_brackets(response, bracket_pos, "[", "]")

    raise ValueError("LLM返回中未找到JSON内容。返回内容前200字: " + response[:200])


def _match_brackets(response: str, start: int, open_ch: str, close_ch: str) -> str:
    """Match balanced brackets from start position."""
    depth = 0
    in_string = False
    escape_next = False
    for i in range(start, len(response)):
        ch = response[i]
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return response[start:i + 1]

    # Unclosed - return everything from start (repair will close it)
    return response[start:]
