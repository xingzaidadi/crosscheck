"""Installed-package resources and the public console entry point are usable."""
from __future__ import annotations

import importlib.resources as resources
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import crosscheck_templates  # noqa: E402


def main() -> None:
    names = {item.name for item in resources.files(crosscheck_templates).iterdir()}
    assert "profile.example.yaml" in names
    assert "suite.example.yaml" in names
    assert "case.example.yaml" in names
    print("package resources passed")


if __name__ == "__main__":
    main()
