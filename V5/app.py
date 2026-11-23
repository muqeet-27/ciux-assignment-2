import logging
import os
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, render_template, request, session

from dialogue import enrich_with_context, update_state
from llm_nlu import parse_with_llm
from nlu import parse as rule_parse
from service import execute

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET") or os.urandom(32)

DATA_FILE = Path(__file__).parent / "data" / "people.xlsx"
df = pd.read_excel(DATA_FILE)
df["DOB"] = pd.to_datetime(df["DOB"], errors="coerce")
df = df.dropna(subset=["DOB", "Person_ID", "Name"]).copy()
df["Name"] = df["Name"].astype(str)
df["Relationship"] = df["Relationship"].fillna("").astype(str)
df["Place_of_Stay"] = df["Place_of_Stay"].fillna("").astype(str)
if "Nickname" in df.columns:
    df["Nickname"] = df["Nickname"].fillna("").astype(str)
if "Relationship_Group" in df.columns:
    df["Relationship_Group"] = df["Relationship_Group"].fillna("").astype(str)

ALLOWED_INTENTS = {
    "birthday_search",
    "count_birthdays",
    "upcoming_birthdays",
    "person_place",
    "unknown",
}
ALLOWED_ENTITIES = {
    "person_name",
    "relationship",
    "relationship_group",
    "month",
    "day_of_month",
    "relative_date",
    "relative_month",
    "place",
}


def normalize_llm(parsed):
    if not isinstance(parsed, dict):
        return {"intent": "unknown", "entities": {}}
    if parsed.get("intent") not in ALLOWED_INTENTS:
        parsed["intent"] = "unknown"
    raw_entities = parsed.get("entities")
    if not isinstance(raw_entities, dict):
        raw_entities = {}
    entities = {
        key: value
        for key, value in raw_entities.items()
        if key in ALLOWED_ENTITIES
    }
    parsed["entities"] = entities

    person_name = entities.get("person_name")
    if person_name:
        target = str(person_name).strip().lower()
        matches = df[df.Name.str.lower() == target]
        if matches.empty and "Nickname" in df.columns:
            matches = df[df.Nickname.str.lower() == target]
        if len(matches) == 1:
            entities["person_id"] = matches.iloc[0].Person_ID
            entities["person_name"] = matches.iloc[0].Name

    relationship = entities.get("relationship")
    if relationship:
        relationship_map = {
            value.lower(): value for value in df.Relationship.unique() if value
        }
        normalized = str(relationship).strip().lower()
        if normalized in relationship_map:
            entities["relationship"] = relationship_map[normalized]
        elif "Relationship_Group" in df.columns:
            group_map = {
                value.lower(): value
                for value in df.Relationship_Group.unique()
                if value
            }
            if normalized in group_map:
                entities["relationship_group"] = group_map[normalized]
                entities.pop("relationship", None)

    group = entities.get("relationship_group")
    if group and "Relationship_Group" in df.columns:
        group_map = {
            value.lower(): value for value in df.Relationship_Group.unique() if value
        }
        normalized = str(group).strip().lower()
        if normalized in group_map:
            entities["relationship_group"] = group_map[normalized]

    return parsed


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/chat")
def chat():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("message"), str):
        return jsonify(error="Send a JSON object with a text message."), 400
    message = payload["message"].strip()
    if not message:
        return jsonify(error="Please enter a message."), 400

    state = session.get("dialogue_state", {})
    nlu_source = "rule_fallback"
    notice = None
    if (
        os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    ):
        try:
            parsed = normalize_llm(parse_with_llm(message))
            nlu_source = "llm"
        except Exception as error:
            logger.warning("LLM parsing failed; using rule-based NLU: %s", error)
            parsed = rule_parse(message, df)
            notice = "AI parsing was unavailable; used rule-based parsing."
    else:
        parsed = rule_parse(message, df)

    parsed = enrich_with_context(parsed, state)
    entities = parsed["entities"]

    if "relationship" in entities and "person_id" not in entities:
        if "when is my" in message.lower():
            matches = df[
                df.Relationship.str.lower()
                == str(entities["relationship"]).lower()
            ]
            if len(matches) > 1:
                session["dialogue_state"] = update_state(
                    parsed, state, list(matches.Person_ID)
                )
                names = ", ".join(matches.Name.head(8).tolist())
                answer = (
                    f"I found {len(matches)} people with that relationship: "
                    f"{names}. Which one do you mean?"
                )
                return jsonify(
                    answer=answer,
                    debug={**parsed, "nlu_source": nlu_source},
                    notice=notice,
                )

    answer = execute(parsed, df)
    session["dialogue_state"] = update_state(parsed, state)
    return jsonify(
        answer=answer,
        debug={**parsed, "nlu_source": nlu_source},
        notice=notice,
    )


@app.post("/reset")
def reset():
    session.clear()
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG") == "1")
