import typing
import json
import math
import numbers
import unicodedata
from pathlib import Path


def find_files(path: Path) -> typing.Iterator[str]:
    path = Path(path)
    for file_path in path.rglob("*"):
        if file_path.is_file():
            yield str(file_path.relative_to(path))


# From https://stackoverflow.com/a/29247821
def normalize_caseless(text):
    return unicodedata.normalize("NFKD", text.casefold())


def caseless_equal(left, right):
    return normalize_caseless(left) == normalize_caseless(right)


def caseless_in(left, right):
    return normalize_caseless(left) in normalize_caseless(right)


def sanitize_non_finite(value: typing.Any, replacement: typing.Any = None) -> typing.Any:
    """Recursively replace NaN/Infinity values with a safe replacement.

    - Traverses dicts, lists, tuples recursively.
    - Leaves other types unchanged.
    - Replaces any non-finite real number (NaN, +Inf, -Inf) with `replacement` (default: None).
    """
    # Numbers: replace only non-finite real numbers
    if isinstance(value, numbers.Real):
        if not math.isfinite(value):
            return replacement
        return value

    # Containers: recurse into supported JSON-like containers
    if isinstance(value, dict):
        return {k: sanitize_non_finite(v, replacement) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_non_finite(v, replacement) for v in value]
    if isinstance(value, tuple):
        return tuple(sanitize_non_finite(v, replacement) for v in value)

    # Leave other types unchanged
    return value


def json_dumps_strict(obj: typing.Any, *, replacement: typing.Any = None, **kwargs) -> str:
    """Serialize to JSON disallowing NaN/Infinity, with optional sanitization.

    - First sanitizes `obj` via `sanitize_non_finite` (default replacement: None -> JSON null).
    - Forces `allow_nan=False` to ensure strict RFC-compliant JSON.
    - Any additional kwargs are forwarded to `json.dumps`.
    """
    safe_obj = sanitize_non_finite(obj, replacement=replacement)
    kwargs.setdefault("allow_nan", False)
    return json.dumps(safe_obj, **kwargs)
