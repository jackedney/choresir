"""Generic fuzzy matching utility for title-based searches."""


def fuzzy_match(
    items: list[dict],
    title_query: str,
    *,
    title_key: str = "title",
) -> dict | None:
    """Fuzzy match a single item by title.

    Priority: exact match > contains match > partial word match.

    Args:
        items: List of records to search
        title_query: User's search query
        title_key: Key to use for title comparison

    Returns:
        Best matching item or None
    """
    matches = fuzzy_match_all(items, title_query, title_key=title_key)
    return matches[0] if matches else None


def _get_title(item: dict, title_key: str) -> str | None:
    """Safely get a string title value from an item dict."""
    value = item.get(title_key)
    return value if isinstance(value, str) else None


def fuzzy_match_all(
    items: list[dict],
    title_query: str,
    *,
    title_key: str = "title",
) -> list[dict]:
    """Fuzzy match all items matching a title query.

    Priority: exact match > contains match > partial word match.

    Args:
        items: List of records to search
        title_query: User's search query
        title_key: Key to use for title comparison

    Returns:
        List of all matching items (may be empty)
    """
    title_lower = title_query.lower().strip()
    if not title_lower:
        return []

    # Exact match (highest priority)
    matches = [item for item in items if (v := _get_title(item, title_key)) and v.lower() == title_lower]
    if matches:
        return matches

    # Contains match
    matches = [item for item in items if (v := _get_title(item, title_key)) and title_lower in v.lower()]
    if matches:
        return matches

    # Partial word match
    query_words = set(title_lower.split())
    return [item for item in items if (v := _get_title(item, title_key)) and query_words & set(v.lower().split())]
