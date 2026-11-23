import calendar
import json
import os
import re
import urllib.parse
import urllib.request

SYSTEM = (
    "You are an NLU parser for a birthday assistant. "
    "Return JSON only with keys 'intent' and 'entities'. "
    "Allowed intents: birthday_search, count_birthdays, upcoming_birthdays, "
    "person_place, unknown. Allowed entities: person_name, relationship, "
    "relationship_group, month (integer 1-12), day_of_month (integer 1-31), "
    "relative_date ('tomorrow'), relative_month ('next'), place. "
    "Never answer the user's factual question and never invent birthdays."
)
MONTHS = {
    name.lower(): number
    for number, name in enumerate(calendar.month_name)
    if name
}


def _normalize_month(parsed):
    entities = parsed.setdefault("entities", {})
    if not isinstance(entities, dict):
        raise ValueError("The model returned invalid entities.")
    month = entities.get("month")
    if isinstance(month, str):
        month_value = month.strip().lower()
        if month_value in MONTHS:
            entities["month"] = MONTHS[month_value]
        elif month_value.isdigit():
            entities["month"] = int(month_value)
        else:
            raise ValueError("The model returned an invalid month.")
    if "month" in entities:
        month = entities["month"]
        if (
            not isinstance(month, int)
            or isinstance(month, bool)
            or not 1 <= month <= 12
        ):
            raise ValueError("The model returned an invalid month.")

    day = entities.get("day_of_month")
    if isinstance(day, str):
        day_value = day.strip().lower()
        match = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?", day_value)
        if match:
            entities["day_of_month"] = int(match.group(1))
        else:
            raise ValueError("The model returned an invalid day of month.")
    if "day_of_month" in entities:
        day = entities["day_of_month"]
        if (
            not isinstance(day, int)
            or isinstance(day, bool)
            or not 1 <= day <= 31
        ):
            raise ValueError("The model returned an invalid day of month.")
    return parsed


def _parse_with_gemini(message, api_key):
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
        f":generateContent?{urllib.parse.urlencode({'key': api_key})}"
    )
    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": message}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
        },
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        data = json.loads(response.read().decode("utf-8"))
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Gemini returned an invalid NLU response.")
    return _normalize_month(parsed)


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
    content = response.choices[0].message.content
    if not content:
        raise ValueError("OpenAI returned an empty NLU response.")
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("OpenAI returned an invalid NLU response.")
    return _normalize_month(parsed)


def parse_with_llm(message):
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    if gemini_key:
        return _parse_with_gemini(message, gemini_key)
    if openai_key and openai_key.startswith("AIza"):
        return _parse_with_gemini(message, openai_key)
    if openai_key:
        return _parse_with_openai(message, openai_key)
    raise RuntimeError("No GEMINI_API_KEY or OPENAI_API_KEY is set.")
