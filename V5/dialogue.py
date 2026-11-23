def enrich_with_context(parsed, state):
    entities = parsed.setdefault("entities", {})
    for key in ("month", "relationship", "relationship_group"):
        if key not in entities and state.get(key) is not None:
            entities[key] = state[key]
    if parsed.get("intent") == "unknown" and any(
        key in entities
        for key in ("month", "relationship", "relationship_group", "person_id")
    ):
        parsed["intent"] = "birthday_search"
    return parsed


def update_state(parsed, state, last_result_ids=None):
    entities = parsed.get("entities", {})
    for key in (
        "month",
        "relationship",
        "relationship_group",
        "person_id",
        "person_name",
    ):
        if key in entities:
            state[key] = entities[key]
    if last_result_ids is not None:
        state["last_result_ids"] = last_result_ids
    return state
