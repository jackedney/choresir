#!/usr/bin/env python3
"""Check processed_messages collection schema and rules."""

import logging

from pocketbase import PocketBase


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    pb = PocketBase("http://127.0.0.1:8090")

    # Authenticate as admin
    try:
        pb.admins.auth_with_password("admin@test.local", "testpassword123")
    except Exception:
        return

    # Get collection info
    try:
        collection = pb.collections.get_one("processed_messages")

        # The schema is in __dict__ as a list
        schema_fields = getattr(collection, "schema", collection.__dict__.get("schema", []))
        if schema_fields:
            for field in schema_fields:
                field_dict = field.__dict__ if hasattr(field, "__dict__") else field
                field_dict.get("name", "unknown")
                field_dict.get("type", "unknown")
                "required" if field_dict.get("required", False) else "optional"
        else:
            pass

    except Exception as e:
        logger.error(f"Error getting collection: {e}")


if __name__ == "__main__":
    main()
