"""Small deterministic helpers used across the compiler."""

from __future__ import annotations

import hashlib
import re
import time
from typing import Iterable, List


def now_ms() -> float:
    return time.perf_counter() * 1000


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return re.sub(r"_+", "_", value).strip("_") or "item"


def titleize(value: str) -> str:
    acronyms = {"api", "crm", "hr", "lms", "rbac", "saas", "sql", "ui"}
    parts = []
    for part in re.split(r"[_\s-]+", value):
        if not part:
            continue
        lowered = part.lower()
        parts.append(lowered.upper() if lowered in acronyms else part.capitalize())
    return " ".join(parts)


def stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]
    return f"{slugify(prefix)}_{digest}"


def unique(values: Iterable[str]) -> List[str]:
    seen = set()
    output = []
    for value in values:
        key = slugify(value)
        if key not in seen:
            seen.add(key)
            output.append(key)
    return output


def sentence(value: str) -> str:
    value = value.strip()
    if not value:
        return value
    return value[0].upper() + value[1:]
