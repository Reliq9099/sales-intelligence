"""Small data processing helpers shared by the UI and research layers."""

import re


def normalize_company_name(name: str) -> str:
    """Normalize legal suffixes, punctuation, and whitespace for matching."""
    normalized = re.sub(r"[^a-zA-Z0-9 ]", " ", name).lower()
    normalized = re.sub(
        r"\b(limited|ltd|incorporated|inc|corporation|corp|company|co)\b", " ", normalized
    )
    return " ".join(normalized.split())


def display_company_name(name: str) -> str:
    return " ".join(part.capitalize() for part in name.split())


def score_color(score: int) -> str:
    if score >= 75:
        return "#16805c"
    if score >= 50:
        return "#b7791f"
    return "#b13b45"