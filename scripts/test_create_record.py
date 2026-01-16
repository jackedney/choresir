#!/usr/bin/env python3
"""Test creating a record in processed_messages."""

from datetime import datetime

import httpx


# HTTP status codes
HTTP_OK = 200


def main() -> None:
    # Test data
    data = {
        "message_id": "test_xyz_123",
        "from_phone": "+1234567890",
        "processed_at": datetime.now().isoformat(),
        "success": False,  # Python boolean
        "error_message": "test error",
    }

    # Create record
    response = httpx.post("http://127.0.0.1:8090/api/collections/processed_messages/records", json=data)

    if response.status_code == HTTP_OK:
        pass
    else:
        pass


if __name__ == "__main__":
    main()
