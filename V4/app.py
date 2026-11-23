import os
from pathlib import Path

from flask import Flask, jsonify, render_template, request, session
import pandas as pd
from dotenv import load_dotenv

from dialogue import enrich_with_context, update_state
from llm_nlu import parse_with_llm
from nlu import parse as rule_parse
from service import execute


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)
app.secret_key = os.getenv("FLASK_SECRET", "dev-secret")

data_path = BASE_DIR / "data" / "people.xlsx"
df = pd.read_excel(data_path)
df["DOB"] = pd.to_datetime(df["DOB"])

ALLOWED_INTENTS = {
    "birthday_search",
    "count_birthdays",
    "upcoming_birthdays",
    "person_place",
    "unknown",
}


def normalize_llm(parsed):
    """Ground model output against the spreadsheet before executing a query."""
    if not isinstance(parsed, dict):
        raise ValueError("LLM response must be a JSON object.")

    if parsed.get("intent") not in ALLOWED_INTENTS:
        parsed["intent"] = "unknown"

    entities = parsed.setdefault("entities", {})
    if not isinstance(entities, dict):
        entities = {}
        parsed["entities"] = entities

    person_name = entities.get("person_name")
    if person_name:
        target = str(person_name).strip().lower()
        matches = df[df["Name"].fillna("").str.lower() == target]
        if matches.empty and "Nickname" in df.columns:
            matches = df[df["Nickname"].fillna("").str.lower() == target]
        if len(matches) == 1:
            person = matches.iloc[0]
            entities["person_id"] = person["Person_ID"]
            entities["person_name"] = person["Name"]
        else:
            entities.pop("person_name", None)

    relationship = entities.get("relationship")
    if relationship:
        rel_value = str(relationship).strip().lower()
        valid_rels = {
            str(value).lower(): str(value)
            for value in df["Relationship"].dropna().unique()
        }
        if rel_value in valid_rels:
            entities["relationship"] = valid_rels[rel_value]
        elif "Relationship_Group" in df.columns:
            valid_groups = {
                str(value).lower(): str(value)
                for value in df["Relationship_Group"].dropna().unique()
            }
            if rel_value in valid_groups:
                entities["relationship_group"] = valid_groups[rel_value]
                entities.pop("relationship", None)

    month = entities.get("month")
    if isinstance(month, str):
        try:
            entities["month"] = int(month)
        except ValueError:
            entities.pop("month", None)

    place = entities.get("place")
    if place and "Place_of_Stay" in df.columns:
        valid_places = {
            str(value).lower(): str(value)
            for value in df["Place_of_Stay"].dropna().unique()
        }
        place_value = str(place).strip().lower()
        if place_value in valid_places:
            entities["place"] = valid_places[place_value]

    return parsed


@app.route("/")
def index():
    return render_template("index.html")


@app.post("/chat")
def chat():
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    state = session.get("dialogue_state", {})
    nlu_source = "rule_fallback"

    if os.getenv("GEMINI_API_KEY"):
        try:
            parsed = normalize_llm(parse_with_llm(message))
            nlu_source = "gemini"
        except Exception:
            parsed = rule_parse(message, df)
    else:
        parsed = rule_parse(message, df)

    parsed = enrich_with_context(parsed, state)
    entities = parsed["entities"]

    if (
        "relationship" in entities
        and "person_id" not in entities
        and "when is my" in message.lower()
    ):
        relationship = str(entities["relationship"]).lower()
        matches = df[df["Relationship"].str.lower() == relationship]
        if len(matches) > 1:
            session["dialogue_state"] = update_state(
                parsed, state, list(matches["Person_ID"])
            )
            names = ", ".join(matches["Name"].head(8).tolist())
            return jsonify(
                answer=f"I found {len(matches)} people with that relationship: {names}. Which one do you mean?",
                debug={**parsed, "nlu_source": nlu_source},
            )

    answer = execute(parsed, df)
    session["dialogue_state"] = update_state(parsed, state)
    return jsonify(
        answer=answer,
        debug={**parsed, "nlu_source": nlu_source},
    )


@app.post("/reset")
def reset():
    session.clear()
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(debug=True)
