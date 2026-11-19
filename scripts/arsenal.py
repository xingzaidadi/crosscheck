"""Inspect and validate a workspace capability registry."""
from __future__ import annotations

import argparse
import json

from core.arsenal import load_capabilities, validate_capability_registry
from core.config import config_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="业务武器库注册表检查")
    parser.add_argument("--registry", default=str(config_dir() / "capabilities.yaml"))
    parser.add_argument("--environment", default=None)
    args = parser.parse_args()
    capabilities = load_capabilities(args.registry)
    errors = validate_capability_registry(capabilities, environment=args.environment)
    print(json.dumps({"registry": args.registry, "count": len(capabilities), "errors": errors,
                      "valid": not errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
