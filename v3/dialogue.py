def enrich_with_context(parsed, state):
    e = parsed.setdefault("entities", {})
    # Carry forward month or relationship only when the new turn omits it.
    for key in ("month", "relationship", "relationship_group"):
        if key not in e and state.get(key) is not None:
            e[key] = state[key]
    if parsed.get("intent") == "unknown" and (
        "month" in e or "relationship" in e or "person_id" in e
    ):
        parsed["intent"] = "birthday_search"
    return parsed


def update_state(parsed, state, last_result_ids=None):
    e = parsed.get("entities", {})
    for key in ("month", "relationship", "relationship_group", "person_id", "person_name"):
        if key in e:
            state[key] = e[key]
    if last_result_ids is not None:
        state["last_result_ids"] = last_result_ids
    return state
