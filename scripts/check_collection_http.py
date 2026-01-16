#!/usr/bin/env python3
"""Check processed_messages collection schema via HTTP API."""

import httpx


# HTTP status codes
HTTP_OK = 200
HTTP_NOT_FOUND = 404


def main() -> None:
    base_url = "http://127.0.0.1:8090"

    # Authenticate (PocketBase admin auth endpoint)
    auth_response = httpx.post(
        f"{base_url}/api/admins/auth-with-password",
        json={"identity": "admin@test.local", "password": "testpassword123"},
        headers={"Content-Type": "application/json"},
    )

    # If that fails, try the alternative endpoint
    if auth_response.status_code == HTTP_NOT_FOUND:
        auth_response = httpx.post(
            f"{base_url}/api/collections/_superusers/auth-with-password",
            json={"identity": "admin@test.local", "password": "testpassword123"},
            headers={"Content-Type": "application/json"},
        )

    if auth_response.status_code != HTTP_OK:
        return

    token = auth_response.json()["token"]

    # Get collection
    headers = {"Authorization": token}
    collection_response = httpx.get(f"{base_url}/api/collections/processed_messages", headers=headers)

    if collection_response.status_code != HTTP_OK:
        return

    collection = collection_response.json()

    for rule in ["listRule", "viewRule", "createRule", "updateRule", "deleteRule"]:
        collection.get(rule)

    for field in collection.get("schema", []):
        field["name"]
        field["type"]
        "REQUIRED" if field.get("required", False) else "optional"


if __name__ == "__main__":
    main()
