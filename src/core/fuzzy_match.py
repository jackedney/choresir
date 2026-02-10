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
    matches: list[dict] = []

    # Exact match (highest priority)
    for item in items:
        if item[title_key].lower() == title_lower:
            matches.append(item)

    if matches:
        return matches

    # Contains match
    for item in items:
        if title_lower in item[title_key].lower():
            matches.append(item)

    if matches:
        return matches

    # Partial word match
    query_words = set(title_lower.split())
    for item in items:
        item_words = set(item[title_key].lower().split())
        if query_words & item_words:
            matches.append(item)

    return matches
