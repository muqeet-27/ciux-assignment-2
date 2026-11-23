import calendar
import re

MONTHS = {
    name.lower(): number
    for number, name in enumerate(calendar.month_name)
    if name
}


def _extract_month_and_day(text, entities):
    for name, number in MONTHS.items():
        if not re.search(r"\b" + re.escape(name) + r"\b", text):
            continue
        entities["month"] = number
        pattern = (
            r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?"
            + re.escape(name)
            + r"\b|\b"
            + re.escape(name)
            + r"\s+(\d{1,2})(?:st|nd|rd|th)?\b"
        )
        match = re.search(pattern, text)
        if match:
            day = int(match.group(1) or match.group(2))
            if 1 <= day <= 31:
                entities["day_of_month"] = day
        return


def parse(message, people):
    text = message.lower().strip()
    result = {"intent": "unknown", "entities": {}}

    if "how many" in text or re.search(r"\bcount\b", text):
        result["intent"] = "count_birthdays"
    elif any(word in text for word in ("where", "stay", "live")):
        result["intent"] = "person_place"
    elif "upcoming" in text:
        result["intent"] = "upcoming_birthdays"
    elif (
        any(
            phrase in text
            for phrase in (
                "birthday",
                "birthdays",
                "born",
                "tomorrow",
                "next month",
                "what about",
                "when is",
            )
        )
        or any(
            re.search(r"\b" + re.escape(month) + r"\b", text)
            for month in MONTHS
        )
    ):
        result["intent"] = "birthday_search"

    if "tomorrow" in text:
        result["entities"]["relative_date"] = "tomorrow"
    if "next month" in text:
        result["entities"]["relative_month"] = "next"
    _extract_month_and_day(text, result["entities"])

    relationships = people["Relationship"].dropna().unique()
    for relationship in sorted(relationships, key=len, reverse=True):
        token = str(relationship).lower()
        if token and re.search(r"\b" + re.escape(token) + r"s?\b", text):
            result["entities"]["relationship"] = relationship
            break

    if (
        "Relationship_Group" in people.columns
        and "relationship" not in result["entities"]
    ):
        groups = people["Relationship_Group"].dropna().unique()
        for group in sorted(groups, key=len, reverse=True):
            token = str(group).lower()
            if token and re.search(r"\b" + re.escape(token) + r"\b", text):
                result["entities"]["relationship_group"] = group
                break

    name_columns = ["Name"]
    if "Nickname" in people.columns:
        name_columns.append("Nickname")
    for _, person in people.iterrows():
        for column in name_columns:
            candidate = str(person[column]).lower().strip()
            if (
                candidate
                and candidate != "nan"
                and re.search(r"\b" + re.escape(candidate) + r"\b", text)
            ):
                result["entities"]["person_id"] = person["Person_ID"]
                result["entities"]["person_name"] = person["Name"]
                if result["intent"] == "unknown":
                    result["intent"] = "birthday_search"
                break
        if "person_id" in result["entities"]:
            break

    return result
