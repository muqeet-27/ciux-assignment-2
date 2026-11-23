import calendar
import json
import os

from google import genai
from google.genai import types


SYSTEM = (
    "You are an NLU parser for a birthday assistant. "
    "Return JSON only with keys 'intent' and 'entities'. "
    "Allowed intents: birthday_search, count_birthdays, upcoming_birthdays, person_place, unknown. "
    "Allowed entities: person_name, relationship, relationship_group, month (integer 1-12), "
    "relative_date ('tomorrow'), relative_month ('next'), place. "
    "Never answer the user's factual question and never invent birthdays."
)


def parse_with_llm(message):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set.")

    client = genai.Client(api_key=api_key)
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    response = client.models.generate_content(
        model=model,
        contents=message,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM,
            response_mime_type="application/json",
            temperature=0,
        ),
    )
    if not response.text:
        raise ValueError("Gemini returned an empty NLU response.")
    parsed = json.loads(response.text)

    entities = parsed.setdefault("entities", {})
    if isinstance(entities.get("month"), str):
        month_names = {
            name.lower(): number
            for number, name in enumerate(calendar.month_name)
            if name
        }
        month_value = entities["month"].strip().lower()
        if month_value in month_names:
            entities["month"] = month_names[month_value]
        elif month_value.isdigit():
            entities["month"] = int(month_value)

    return parsed
