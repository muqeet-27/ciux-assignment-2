from datetime import date, timedelta


def format_rows(rows):
    if rows.empty:
        return "No matching people found."
    return "\n".join(
        f"{person.Name} - {person.DOB.strftime('%d %B')} ({person.Relationship})"
        for _, person in rows.iterrows()
    )


def execute(parsed, df):
    intent = parsed.get("intent", "unknown")
    entities = parsed.get("entities", {})
    work = df.copy()
    today = date.today()

    if intent == "unknown" and not entities:
        return (
            "I could not understand that as a birthday or person query. "
            "Try asking about upcoming birthdays, a month, a relationship, "
            "or a person's name."
        )

    if "person_id" in entities:
        matches = df[df.Person_ID == entities["person_id"]]
        if matches.empty:
            return "No matching person found in the spreadsheet."
        person = matches.iloc[0]
        if intent == "person_place":
            return f"{person.Name} stays in {person.Place_of_Stay}."
        return f"{person.Name}'s birthday is {person.DOB.strftime('%d %B %Y')}."

    if entities.get("relationship"):
        work = work[
            work.Relationship.str.lower()
            == str(entities["relationship"]).lower()
        ]

    if entities.get("relationship_group") and "Relationship_Group" in work.columns:
        work = work[
            work.Relationship_Group.fillna("").str.lower()
            == str(entities["relationship_group"]).lower()
        ]

    if entities.get("place"):
        work = work[
            work.Place_of_Stay.fillna("").str.lower()
            == str(entities["place"]).lower()
        ]

    if entities.get("relative_date") == "tomorrow":
        tomorrow = today + timedelta(days=1)
        work = work[
            (work.DOB.dt.month == tomorrow.month)
            & (work.DOB.dt.day == tomorrow.day)
        ]

    month = entities.get("month")
    if entities.get("relative_month") == "next":
        month = 1 if today.month == 12 else today.month + 1
    if month:
        try:
            month_number = int(month)
        except (TypeError, ValueError):
            month_number = None
        if month_number is not None and 1 <= month_number <= 12:
            work = work[work.DOB.dt.month == month_number]

    day = entities.get("day_of_month")
    if day:
        try:
            day_number = int(day)
        except (TypeError, ValueError):
            day_number = None
        if day_number is not None and 1 <= day_number <= 31:
            work = work[work.DOB.dt.day == day_number]

    if intent == "count_birthdays":
        return f"I found {len(work)} matching birthdays."

    if intent == "upcoming_birthdays":
        def days_until(person):
            try:
                birthday = date(today.year, person.DOB.month, person.DOB.day)
            except ValueError:
                birthday = date(today.year, 2, 28)
            if birthday < today:
                try:
                    birthday = date(today.year + 1, person.DOB.month, person.DOB.day)
                except ValueError:
                    birthday = date(today.year + 1, 2, 28)
            return (birthday - today).days

        work = work.assign(_days=work.apply(days_until, axis=1))
        work = work[(work._days >= 0) & (work._days <= 30)].sort_values("_days")
        return format_rows(work)

    if intent == "person_place":
        if work.empty:
            return "No matching people found."
        return "\n".join(
            f"{person.Name} stays in {person.Place_of_Stay}."
            for _, person in work.iterrows()
        )

    if intent == "birthday_search" and not any(
        key in entities
        for key in (
            "person_id",
            "relationship",
            "relationship_group",
            "place",
            "relative_date",
            "relative_month",
            "month",
            "day_of_month",
        )
    ):
        return (
            "Please include a month, relationship, or person name "
            "(for example: 'birthdays in September' or 'Rahul Patil's birthday')."
        )

    work = work.assign(_month=work.DOB.dt.month, _day=work.DOB.dt.day)
    work = work.sort_values(["_month", "_day", "Name"])
    return format_rows(work)
