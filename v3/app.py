import os
from pathlib import Path

from flask import Flask, render_template, request, jsonify, session
import pandas as pd
from nlu import parse
from service import execute
from dialogue import enrich_with_context, update_state

BASE_DIR = Path(__file__).resolve().parent
app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)
app.secret_key = os.getenv("FLASK_SECRET", "replace-this-in-production")

df = pd.read_excel(BASE_DIR / "data" / "people.xlsx")
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
