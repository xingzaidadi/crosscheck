"""Actor context must replace captured identities in generated write bodies."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.modeler import _apply_actor_context  # noqa: E402


def main() -> None:
    body = {
        "applicantUserId": "old", "applicantUserNo": "1", "applicantUserName": "Old",
        "demanderUserId": "old", "demanderUserNo": "1", "demanderUserName": "Old",
        "other": "unchanged",
    }
    actor = {"values": {"user_id": "xuzhijun", "user_no": "74380", "user_name": "许志俊"},
             "bindings": {"applicantUserId": "user_id", "applicantUserNo": "user_no",
                          "applicantUserName": "user_name", "demanderUserId": "user_id",
                          "demanderUserNo": "user_no", "demanderUserName": "user_name"}}
    result = _apply_actor_context(body, actor)
    assert result["applicantUserId"] == result["demanderUserId"] == "xuzhijun"
    assert result["applicantUserNo"] == result["demanderUserNo"] == "74380"
    assert result["applicantUserName"] == result["demanderUserName"] == "许志俊"
    assert result["other"] == "unchanged"
    print("modeler actor context passed")


if __name__ == "__main__":
    main()
