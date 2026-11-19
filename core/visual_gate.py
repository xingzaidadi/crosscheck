"""Deterministic image comparison primitives used by visual acceptance."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def compare(reference: str | Path, actual: str | Path, *, threshold: float = 0.0,
            mask: list[tuple[int, int, int, int]] | None = None) -> dict[str, Any]:
    from PIL import Image, ImageChops
    ref = Image.open(reference).convert("RGBA")
    got = Image.open(actual).convert("RGBA")
    if ref.size != got.size:
        return {"passed": False, "reason": "size_mismatch", "reference_size": ref.size, "actual_size": got.size}
    if mask:
        for left, top, right, bottom in mask:
            got.paste(ref.crop((left, top, right, bottom)), (left, top))
    diff = ImageChops.difference(ref, got)
    histogram = diff.convert("L").histogram()
    changed = sum(count for index, count in enumerate(histogram) if index > 0)
    total = ref.width * ref.height
    ratio = changed / max(total, 1)
    return {"passed": ratio <= threshold, "changed_pixels": changed, "pixel_ratio": ratio,
            "threshold": threshold, "size": ref.size}


def compare_structural(reference: dict, actual: dict, *, ignored_keys: set[str] | None = None) -> dict[str, Any]:
    """Compare normalized component trees without depending on pixel rendering."""
    ignored_keys = ignored_keys or set()

    def normalize(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in sorted(value.items()) if key not in ignored_keys}
        if isinstance(value, list):
            return [normalize(item) for item in value]
        return value

    expected = normalize(reference)
    observed = normalize(actual)
    return {"passed": expected == observed, "reference": expected, "actual": observed}
