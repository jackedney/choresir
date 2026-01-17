#!/usr/bin/env python3
"""Test creating a record using PocketBase SDK directly."""

import contextlib
from datetime import datetime

from pocketbase import PocketBase


def main() -> None:
    pb = PocketBase("http://127.0.0.1:8090")

    # Test data - exactly as in webhook code
    data = {
        "message_id": "sdk_test_456",
        "from_phone": "+1234567890",
        "processed_at": datetime.now().isoformat(),
        "success": False,
        "error_message": "Processing in progress",
    }

    with contextlib.suppress(Exception):
        pb.collection("processed_messages").create(data)


if __name__ == "__main__":
    main()
