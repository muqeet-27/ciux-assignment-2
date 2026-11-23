# CIUX Birthday Assistant — Version 5 (Voice Conversational Interface)

## Folder Structure

```text
V5/
├── app.py
├── dialogue.py
├── llm_nlu.py
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

> Copy your `CIUX_Birthday_Assistant_100_People.xlsx` file into `V5/data/people.xlsx`. The backend (`app.py`, `dialogue.py`, `llm_nlu.py`, `nlu.py`, `service.py`) stays unchanged from V4; only `templates/index.html`, `static/chat.js`, and `static/style.css` add voice input (`SpeechRecognition`, `en-IN`) and speech output (`SpeechSynthesisUtterance`).

## Setup & Run (PowerShell)

```powershell
pip install -r requirements.txt
$env:OPENAI_API_KEY="YOUR_KEY"
python app.py
```

> Open `http://127.0.0.1:5000` in **Chrome** or **Edge** to use the **Speak** button and **Read responses aloud** toggle.

## `V5/app.py`
```python
import os
from flask import Flask, render_template, request, jsonify, session
import pandas as pd
from nlu import parse as rule_parse
from llm_nlu import parse_with_llm
from service import execute
from dialogue import enrich_with_context, update_state

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "dev-secret")

df = pd.read_excel("data/people.xlsx")
df["DOB"] = pd.to_datetime(df["DOB"])

ALLOWED_INTENTS = {
    "birthday_search",
    "count_birthdays",
    "upcoming_birthdays",
    "person_place",
    "unknown",
}


def normalize_llm(parsed):
    # Ground LLM output against the spreadsheet; the LLM is never trusted for facts.
    if parsed.get("intent") not in ALLOWED_INTENTS:
        parsed["intent"] = "unknown"
    e = parsed.setdefault("entities", {})

    if e.get("person_name"):
        target = str(e["person_name"]).strip().lower()
        m = df[df.Name.str.lower() == target]
        if m.empty and "Nickname" in df.columns:
            m = df[df.Nickname.fillna("").str.lower() == target]
        if len(m) == 1:
            e["person_id"] = m.iloc[0].Person_ID
            e["person_name"] = m.iloc[0].Name

    if e.get("relationship"):
        rel_val = str(e["relationship"]).strip().lower()
        valid_rels = {r.lower(): r for r in df["Relationship"].dropna().unique()}
        if rel_val in valid_rels:
            e["relationship"] = valid_rels[rel_val]
        elif "Relationship_Group" in df.columns:
            valid_grps = {g.lower(): g for g in df["Relationship_Group"].dropna().unique()}
            if rel_val in valid_grps:
                e["relationship_group"] = valid_grps[rel_val]
                del e["relationship"]

    return parsed


@app.route("/")
def index():
    return render_template("index.html")


@app.post("/chat")
def chat():
    msg = request.json.get("message", "")
    state = session.get("dialogue_state", {})
    nlu_source = "rule_fallback"

    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("OPENAI_API_KEY"):
        try:
            parsed = normalize_llm(parse_with_llm(msg))
            nlu_source = "llm"
        except Exception:
            parsed = rule_parse(msg, df)
    else:
        parsed = rule_parse(msg, df)

    parsed = enrich_with_context(parsed, state)

    e = parsed["entities"]
    if "relationship" in e and "person_id" not in e and ("when is my" in msg.lower()):
        matches = df[df.Relationship.str.lower() == str(e["relationship"]).lower()]
        if len(matches) > 1:
            session["dialogue_state"] = update_state(
                parsed, state, list(matches.Person_ID)
            )
            names = ", ".join(matches.Name.head(8).tolist())
            return jsonify(
                answer=f"I found {len(matches)} people with that relationship: {names}. Which one do you mean?",
                debug={**parsed, "nlu_source": nlu_source},
            )

    ans = execute(parsed, df)
    session["dialogue_state"] = update_state(parsed, state)
    return jsonify(answer=ans, debug={**parsed, "nlu_source": nlu_source})


@app.post("/reset")
def reset():
    session.clear()
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(debug=True)
```

## `V5/dialogue.py`
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

## `V5/llm_nlu.py`
```python
import calendar
import json
import os
import urllib.request

SYSTEM = (
    "You are an NLU parser for a birthday assistant. "
    "Return JSON only with keys 'intent' and 'entities'. "
    "Allowed intents: birthday_search, count_birthdays, upcoming_birthdays, person_place, unknown. "
    "Allowed entities: person_name, relationship, relationship_group, month (integer 1-12), "
    "relative_date ('tomorrow'), relative_month ('next'), place. "
    "Never answer the user's factual question and never invent birthdays."
)


def _normalize_month(parsed):
    entities = parsed.setdefault("entities", {})
    if isinstance(entities.get("month"), str):
        months = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
        m_val = entities["month"].strip().lower()
        if m_val in months:
            entities["month"] = months[m_val]
        elif m_val.isdigit():
            entities["month"] = int(m_val)
    return parsed


def _parse_with_gemini(message, api_key):
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
        f":generateContent?key={api_key}"
    )
    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": message}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return _normalize_month(json.loads(text))


def _parse_with_openai(message, api_key):
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": message},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return _normalize_month(json.loads(response.choices[0].message.content))


def parse_with_llm(message):
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    # If a Gemini key (AIza...) was placed in OPENAI_API_KEY, route to Gemini automatically.
    if gemini_key:
        return _parse_with_gemini(message, gemini_key)
    if openai_key and openai_key.startswith("AIza"):
        return _parse_with_gemini(message, openai_key)
    if openai_key:
        return _parse_with_openai(message, openai_key)
    raise RuntimeError("No GEMINI_API_KEY or OPENAI_API_KEY is set.")
```

## `V5/nlu.py`
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

## `V5/requirements.txt`
```text
flask>=3.0.0
pandas>=2.1.0
openpyxl>=3.1.0
python-dateutil>=2.8.2
openai>=1.30.0
```

## `V5/service.py`
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

    if intent == "birthday_search" and not any(
        k in e
        for k in (
            "person_id",
            "relationship",
            "relationship_group",
            "place",
            "relative_date",
            "relative_month",
            "month",
        )
    ):
        return (
            "Please include a month, relationship, or person name "
            "(for example: 'birthdays in September' or 'Rahul Patil's birthday')."
        )

    return format_rows(work.sort_values(by=["DOB"]))
```

## `V5/static/chat.js`
```javascript
let isListening = false;

async function sendMsg() {
  const q = document.getElementById("q");
  const text = q.value.trim();
  if (!text) return;

  add(text, "user");
  q.value = "";

  const r = await fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: text })
  });
  const d = await r.json();
  add(d.answer, "bot", d.debug);

  if (document.getElementById("speakBack").checked && "speechSynthesis" in window) {
    speechSynthesis.cancel();
    speechSynthesis.speak(new SpeechSynthesisUtterance(d.answer));
  }
}

async function resetChat() {
  await fetch("/reset", { method: "POST" });
  if ("speechSynthesis" in window) speechSynthesis.cancel();
  document.getElementById("chat").innerHTML = "";
  add("Conversation context cleared. Type or use the microphone!", "bot");
}

function add(t, c, debugInfo = null) {
  const e = document.createElement("div");
  e.className = "msg " + c;
  e.textContent = t;
  if (debugInfo) {
    const dbg = document.createElement("div");
    dbg.className = "debug-tag";
    dbg.textContent = `source: ${debugInfo.nlu_source || "nlu"} | intent: ${debugInfo.intent} | entities: ${JSON.stringify(debugInfo.entities)}`;
    e.appendChild(dbg);
  }
  document.getElementById("chat").appendChild(e);
  e.scrollIntoView();
}

function listen() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    add("Speech recognition is not supported in this browser.", "bot");
    return;
  }
  if (isListening) return;

  const btn = document.getElementById("speakBtn");
  const status = document.getElementById("voiceStatus");
  const r = new SR();
  r.lang = "en-IN";
  r.continuous = false;
  r.interimResults = false;

  let sent = false;
  isListening = true;
  btn.classList.add("listening");
  btn.textContent = "Listening...";
  status.textContent = "Listening (en-IN)...";

  r.onresult = e => {
    const last = e.results[e.results.length - 1];
    if (!last || !last.isFinal || sent) return;
    sent = true;
    document.getElementById("q").value = last[0].transcript;
    r.stop();
    sendMsg();
  };
  r.onerror = e => {
    add("Voice input error: " + e.error, "bot");
  };
  r.onend = () => {
    isListening = false;
    btn.classList.remove("listening");
    btn.textContent = "Speak";
    status.textContent = "";
  };
  r.start();
}

document.getElementById("q").addEventListener("keydown", e => {
  if (e.key === "Enter") sendMsg();
});

add("Hello! You can type or use the microphone.", "bot");
```

## `V5/static/style.css`
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

## `V5/templates/index.html`
```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Voice Birthday Assistant - V5</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
  <div class="card">
    <div class="header">
      <div>
        <h1>Birthday Assistant - Voice Edition (V5)</h1>
        <p class="subtitle">Type or speak. Responses can be read aloud by the browser.</p>
      </div>
      <button class="secondary" onclick="resetChat()">Reset Conversation</button>
    </div>
    <div id="chat" class="chat"></div>
    <div class="row">
      <input id="q" type="text" placeholder="Ask a question or click Speak...">
      <button onclick="sendMsg()">Send</button>
      <button id="speakBtn" onclick="listen()">Speak</button>
    </div>
    <div class="controls">
      <label class="toggle">
        <input id="speakBack" type="checkbox" checked>
        Read responses aloud
      </label>
      <span id="voiceStatus"></span>
    </div>
  </div>
  <script src="{{ url_for('static', filename='chat.js') }}"></script>
</body>
</html>
```
