"""Versioned application model shared by UI onboarding and execution tooling."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import yaml


SCHEMA_VERSION = 1


@dataclass
class UiPage:
    page_id: str
    route: str
    entry: str
    roles: list[str] = field(default_factory=list)
    selectors: dict[str, str] = field(default_factory=dict)
    waits: list[dict[str, Any]] = field(default_factory=list)
    frames: dict[str, str] = field(default_factory=dict)
    dialogs: dict[str, str] = field(default_factory=dict)
    dynamic_masks: list[str] = field(default_factory=list)


def seed_model(*, system: str, base_url: str, roles: list[str] | None = None) -> dict[str, Any]:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("base_url must be an absolute HTTP(S) URL")
    page = UiPage(page_id="home", route=parsed.path or "/", entry=base_url,
                  roles=roles or [], waits=[{"type": "network_idle"}])
    return {
        "schema_version": SCHEMA_VERSION,
        "system": system,
        "base_url": base_url.rstrip("/"),
        "pages": {page.page_id: asdict(page)},
        "actions": {},
        "oracles": {},
        "metadata": {"status": "seeded", "requires_exploration": True},
    }


def validate_model(model: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if model.get("schema_version") != SCHEMA_VERSION:
        errors.append({"field": "schema_version", "message": f"must equal {SCHEMA_VERSION}"})
    base_url = str(model.get("base_url") or "")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        errors.append({"field": "base_url", "message": "must be an absolute HTTP(S) URL"})
    pages = model.get("pages")
    if not isinstance(pages, dict) or not pages:
        errors.append({"field": "pages", "message": "at least one page is required"})
        return errors
    for page_id, page in pages.items():
        if not isinstance(page, dict):
            errors.append({"field": f"pages.{page_id}", "message": "must be an object"})
            continue
        entry = str(page.get("entry") or "")
        if not entry:
            errors.append({"field": f"pages.{page_id}.entry", "message": "is required"})
        elif base_url and urlparse(urljoin(base_url + "/", entry)).netloc != parsed.netloc:
            errors.append({"field": f"pages.{page_id}.entry", "message": "must stay on base_url host"})
        selectors = page.get("selectors", {})
        if not isinstance(selectors, dict):
            errors.append({"field": f"pages.{page_id}.selectors", "message": "must be an object"})
    return errors


def load_model(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    model = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    errors = validate_model(model)
    if errors:
        raise ValueError(f"invalid UI application model: {errors}")
    return model


def write_model(model: dict[str, Any], path: str | Path) -> Path:
    errors = validate_model(model)
    if errors:
        raise ValueError(f"invalid UI application model: {errors}")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(model, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return target

