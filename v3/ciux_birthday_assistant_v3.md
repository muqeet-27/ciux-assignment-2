# CIUX Birthday Assistant — Version 3 (Dialogue State, Context & Clarification)

## Folder Structure

```text
V3/
├── app.py
├── dialogue.py
├── nlu.py
├── service.py
├── requirements.txt
├── data/
│   └── people.xlsx
├── templates/
│   └── index.html
└── static/
    ├── style.css
    └── chat.js
```

> Copy your `CIUX_Birthday_Assistant_100_People.xlsx` file into `V3/data/people.xlsx`.

## `V3/app.py`
```python
import os
from flask import Flask, render_template, request, jsonify, session
import pandas as pd
from nlu import parse
from service import execute
from dialogue import enrich_with_context, update_state

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "replace-this-in-production")

df = pd.read_excel("data/people.xlsx")
df["DOB"] = pd.to_datetime(df["DOB"])


@app.route("/")
def index():
    return render_template("index.html")


@app.post("/chat")
def chat():
    msg = request.json.get("message", "")
    state = session.get("dialogue_state", {})
    parsed = enrich_with_context(parse(msg, df), state)

    # Simple ambiguity check for relationship-only singular question
    e = parsed["entities"]
    if "relationship" in e and "person_id" not in e and ("when is my" in msg.lower()):
        matches = df[df.Relationship.str.lower() == e["relationship"].lower()]
        if len(matches) > 1:
            session["dialogue_state"] = update_state(
                parsed, state, list(matches.Person_ID)
            )
            names = ", ".join(matches.Name.head(8).tolist())
            return jsonify(
                answer=f"I found {len(matches)} people with that relationship: {names}. Which one do you mean?",
                debug=parsed,
                state=session["dialogue_state"],
            )

    ans = execute(parsed, df)
    session["dialogue_state"] = update_state(parsed, state)
    return jsonify(answer=ans, debug=parsed, state=session["dialogue_state"])


@app.post("/reset")
def reset():
    session.clear()
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(debug=True)
```

## `V3/dialogue.py`
```python
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
```

## `V3/nlu.py`
```python
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
```

## `V3/requirements.txt`
```text
flask>=3.0.0
pandas>=2.1.0
openpyxl>=3.1.0
python-dateutil>=2.8.2
```

## `V3/service.py`
```python
from datetime import date, timedelta
import calendar


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
```

## `V3/static/chat.js`
```javascript
async function sendMsg() {
  const q = document.getElementById("q");
  const text = q.value.trim();
  if (!text) return;

  addMessage(text, "user");
  q.value = "";

  const r = await fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: text })
  });
  const d = await r.json();
  addMessage(d.answer, "bot", d.debug);
}

async function resetChat() {
  await fetch("/reset", { method: "POST" });
  document.getElementById("chat").innerHTML = "";
  addMessage("Conversation context cleared. Start a new question!", "bot");
}

function addMessage(text, cls, debugInfo = null) {
  const e = document.createElement("div");
  e.className = "msg " + cls;
  e.textContent = text;
  if (debugInfo) {
    const dbg = document.createElement("div");
    dbg.className = "debug-tag";
    dbg.textContent = `intent: ${debugInfo.intent} | entities: ${JSON.stringify(debugInfo.entities)}`;
    e.appendChild(dbg);
  }
  document.getElementById("chat").appendChild(e);
  e.scrollIntoView();
}

document.getElementById("q").addEventListener("keydown", e => {
  if (e.key === "Enter") sendMsg();
});

addMessage("Hello! Ask a question or follow up across turns.", "bot");
```

## `V3/static/style.css`
```css
* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: #f3f5f8;
  color: #1e293b;
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  padding: 16px;
}

.card {
  width: 100%;
  max-width: 720px;
  background: #ffffff;
  border-radius: 14px;
  box-shadow: 0 8px 28px rgba(15, 23, 42, 0.08);
  padding: 20px 22px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  border-bottom: 1px solid #e2e8f0;
  padding-bottom: 10px;
}

.header h1 {
  font-size: 1.25rem;
  color: #0f172a;
}

.subtitle {
  font-size: 0.88rem;
  color: #64748b;
}

.chat {
  height: 380px;
  overflow-y: auto;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 12px;
  background: #f8fafc;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.msg {
  max-width: 82%;
  padding: 10px 13px;
  border-radius: 10px;
  font-size: 0.94rem;
  line-height: 1.45;
  white-space: pre-line;
}

.msg.user {
  align-self: flex-end;
  background: #2563eb;
  color: #ffffff;
}

.msg.bot {
  align-self: flex-start;
  background: #ffffff;
  color: #0f172a;
  border: 1px solid #e2e8f0;
}

.debug-tag {
  font-size: 0.75rem;
  color: #475569;
  background: #f1f5f9;
  border-radius: 6px;
  padding: 4px 8px;
  margin-top: 6px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.row {
  display: flex;
  gap: 8px;
}

input[type="text"],
#q {
  flex: 1;
  padding: 10px 12px;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  font-size: 0.95rem;
  outline: none;
}

input[type="text"]:focus,
#q:focus {
  border-color: #2563eb;
}

button {
  padding: 10px 16px;
  border: none;
  border-radius: 8px;
  background: #2563eb;
  color: #ffffff;
  font-size: 0.92rem;
  font-weight: 500;
  cursor: pointer;
}

button:hover {
  background: #1d4ed8;
}

button.secondary {
  background: #e2e8f0;
  color: #1e293b;
}

button.secondary:hover {
  background: #cbd5e1;
}

button.listening {
  background: #dc2626;
}

.controls {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.88rem;
  color: #475569;
}

label.toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}
```

## `V3/templates/index.html`
```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Birthday Assistant - V3</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
  <div class="card">
    <div class="header">
      <div>
        <h1>Birthday Assistant (V3)</h1>
        <p class="subtitle">Dialogue State, Context &amp; Clarification</p>
      </div>
      <button class="secondary" onclick="resetChat()">Reset Conversation</button>
    </div>
    <div id="chat" class="chat"></div>
    <div class="row">
      <input id="q" type="text" placeholder="Ask a birthday question or follow-up...">
      <button onclick="sendMsg()">Send</button>
    </div>
  </div>
  <script src="{{ url_for('static', filename='chat.js') }}"></script>
</body>
</html>
```
