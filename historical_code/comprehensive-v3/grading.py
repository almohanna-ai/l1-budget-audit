"""Conservative CPU-only grading for the five fixed pilot questions.

No eval, CAS, remote judge, or GPU. Unsupported expressions remain unresolved.
"""
from __future__ import annotations
from fractions import Fraction
import re
from typing import Any


def normalize(text: str) -> str:
    """Normalize wrappers and common literal mathematical notation only."""
    text = text.strip().rstrip(".")
    for wrapper in [r"\(", r"\)", r"\[", r"\]", "$", r"\left", r"\right"]:
        text = text.replace(wrapper, "")
    text = text.replace("−", "-").replace(r"\infty", "inf").replace("∞", "inf")
    text = text.replace(r"\cup", "U").replace("∪", "U").replace(r"\,", "")
    text = re.sub(r"\\(?:dfrac|tfrac|frac)\{([+-]?\d+)\}\{([+-]?\d+)\}", r"\1/\2", text)
    text = re.sub(r"\\(?:mathrm|text)\{([^{}]*)\}", r"\1", text)
    return re.sub(r"\s+", "", text)


def literal(text: str) -> Any:
    """Parse a bounded rational literal or explicit union of real intervals."""
    text = normalize(text)
    if len(text) > 512:
        return None
    if re.fullmatch(r"[+-]?\d{1,18}(?:\.\d{1,18}|/[+-]?\d{1,18})?", text):
        try:
            return ("number", Fraction(text))
        except (ValueError, ZeroDivisionError):
            return None
    parts = text.split("U")
    intervals = []
    for part in parts:
        match = re.fullmatch(r"([\[(])([+-]?(?:\d+(?:\.\d+)?|inf)),([+-]?(?:\d+(?:\.\d+)?|inf))([\])])", part)
        if not match:
            return None
        left, lo, hi, right = match.groups()
        def endpoint(value: str) -> Any:
            """Represent finite and infinite endpoints without approximate arithmetic."""
            return value.replace("+inf", "inf") if "inf" in value else str(Fraction(value))
        intervals.append((left, endpoint(lo), endpoint(hi), right))
    return ("intervals", tuple(sorted(intervals))) if intervals else None


def boxes(text: str) -> list[str]:
    """Extract balanced boxed payloads without a nesting-fragile regex."""
    found = []
    for match in re.finditer(r"\\boxed\s*\{", text):
        start = match.end()
        depth = 1
        for index in range(start, len(text)):
            depth += (text[index] == "{") - (text[index] == "}")
            if depth == 0:
                found.append(text[start:index])
                break
    return found


def grade(full_output: str, final_text: str | None, references: list[str], hit_cap: bool) -> dict[str, Any]:
    """Grade unique explicit final answers; preserve caps/conflicts as unresolved."""
    def result(status: str, reason: str, answer: str | None = None) -> dict[str, Any]:
        """Produce the same grading schema on all paths."""
        return {"status": status, "reason": reason, "selected_answer": answer}
    if hit_cap:
        return result("unresolved", "output_cap_reached")
    if final_text is None:
        if "<think>" in full_output or "</think>" in full_output:
            return result("unresolved", "invalid_thinking_boundary")
        final_text = full_output  # Direct-answer NoCoT can omit thinking tags entirely.
    text = re.sub(r"<｜[^>]*?｜>", "", final_text).strip()
    candidates = boxes(text)
    for match in re.finditer(r"(?im)^\s*(?:\*\*)?Answer\s*:\s*(.+)$", text):
        line = match.group(1).strip().strip("*")
        candidates.extend(boxes(line) or [line])
    if not candidates:
        # Accept a bare mathematical literal only if the entire final region is it.
        if literal(text) is not None:
            candidates = [text]
        else:
            return result("unresolved", "no_supported_explicit_answer")
    parsed = [literal(x) for x in candidates]
    if any(x is None for x in parsed):
        return result("unresolved", "unsupported_expression")
    if len(set(parsed)) != 1:
        return result("unresolved", "conflicting_answers")
    expected = [literal(x) for x in references]
    if any(x is None for x in expected):
        return result("unresolved", "unsupported_reference")
    return result("correct" if parsed[0] in expected else "incorrect", "literal_comparison", candidates[-1])
