#!/usr/bin/env python3
"""Test creating a record in processed_messages."""

import logging
from datetime import datetime

import httpx


logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

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
        logger.info(f"Success: Record created with response: {response.json()}")
    else:
        logger.error(f"Error: Failed to create record. Status: {response.status_code}, Response: {response.text}")


if __name__ == "__main__":
    main()
