import calendar
import re

MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}


def parse(message, people):
    text = message.lower().strip()
    result = {"intent": "unknown", "entities": {}}

    if "how many" in text or "count" in text:
        result["intent"] = "count_birthdays"
    elif "where" in text or "stay" in text or "live" in text:
        result["intent"] = "person_place"
    elif "upcoming" in text:
        result["intent"] = "upcoming_birthdays"
    elif any(
        kw in text
        for kw in (
            "birthday",
            "birthdays",
            "born",
            "tomorrow",
            "next month",
            "what about",
            "when is",
        )
    ) or any(m in text for m in MONTHS):
        result["intent"] = "birthday_search"

    if "tomorrow" in text:
        result["entities"]["relative_date"] = "tomorrow"
    if "next month" in text:
        result["entities"]["relative_month"] = "next"

    for name, num in MONTHS.items():
        if re.search(r"\b" + re.escape(name) + r"\b", text):
            result["entities"]["month"] = num
            break

    for rel in sorted(people["Relationship"].dropna().unique(), key=len, reverse=True):
        token = rel.lower()
        if re.search(r"\b" + re.escape(token) + r"s?\b", text):
            result["entities"]["relationship"] = rel
            break

    if "Relationship_Group" in people.columns and "relationship" not in result["entities"]:
        for grp in sorted(people["Relationship_Group"].dropna().unique(), key=len, reverse=True):
            token = grp.lower()
            if token in text:
                result["entities"]["relationship_group"] = grp
                break

    for _, r in people.iterrows():
        for candidate in [str(r["Name"]), str(r.get("Nickname", ""))]:
            c = candidate.lower().strip()
            if c and c != "nan" and re.search(r"\b" + re.escape(c) + r"\b", text):
                result["entities"]["person_id"] = r["Person_ID"]
                result["entities"]["person_name"] = r["Name"]
                if result["intent"] == "unknown":
                    result["intent"] = "birthday_search"
                break
        if "person_id" in result["entities"]:
            break

    return result
