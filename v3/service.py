from datetime import date, timedelta


def format_rows(rows):
    if rows.empty:
        return "No matching people found."
    return "\n".join(
        f"{r.Name} - {r.DOB.strftime('%d %B')} ({r.Relationship})"
        for _, r in rows.iterrows()
    )


def execute(parsed, df):
    intent = parsed.get("intent", "unknown")
    e = parsed.get("entities", {})
    work = df.copy()
    today = date.today()

    if intent == "unknown" and not e:
        return (
            "I could not understand that as a birthday or person query. "
            "Try asking about upcoming birthdays, a month, a relationship, or a person's name."
        )

    if "person_id" in e:
        matches = df[df.Person_ID == e["person_id"]]
        if matches.empty:
            return "No matching person found in the spreadsheet."
        r = matches.iloc[0]
        if intent == "person_place":
            return f"{r.Name} stays in {r.Place_of_Stay}."
        return f"{r.Name}'s birthday is {r.DOB.strftime('%d %B %Y')}."

    if "relationship" in e:
        work = work[work.Relationship.str.lower() == str(e["relationship"]).lower()]

    if "relationship_group" in e and "Relationship_Group" in work.columns:
        work = work[work.Relationship_Group.str.lower() == str(e["relationship_group"]).lower()]

    if "place" in e:
        work = work[work.Place_of_Stay.str.lower() == str(e["place"]).lower()]

    if e.get("relative_date") == "tomorrow":
        t = today + timedelta(days=1)
        work = work[(work.DOB.dt.month == t.month) & (work.DOB.dt.day == t.day)]

    month = e.get("month")
    if e.get("relative_month") == "next":
        month = 1 if today.month == 12 else today.month + 1
    if month:
        try:
            month_int = int(month)
            work = work[work.DOB.dt.month == month_int]
        except (TypeError, ValueError):
            pass

    if intent == "count_birthdays":
        return f"I found {len(work)} matching birthdays."

    if intent == "upcoming_birthdays":
        def days(r):
            try:
                cand = date(today.year, r.DOB.month, r.DOB.day)
            except ValueError:
                cand = date(today.year, 2, 28)
            if cand < today:
                try:
                    cand = date(today.year + 1, r.DOB.month, r.DOB.day)
                except ValueError:
                    cand = date(today.year + 1, 2, 28)
            return (cand - today).days

        work = work.assign(_days=work.apply(days, axis=1))
        work = work[(work._days >= 0) & (work._days <= 30)].sort_values("_days")
        return format_rows(work)

    if intent == "person_place":
        if work.empty:
            return "No matching people found."
        return "\n".join(f"{r.Name} stays in {r.Place_of_Stay}." for _, r in work.iterrows())

    return format_rows(work.sort_values(by=["DOB"]))
