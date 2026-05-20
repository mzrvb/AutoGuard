'''
    Claude is CARRYING email analysis.

    Coverage request emails vary in structure and formality.

    Claude performs two operations (was formerly two api calls) in an API call to determine:
        1. If the email is even coverage related
        2. And if so, extract information about the shift(s)

    With the only prerequisite being the current date in order to properly return JSON.
'''

from datetime import date, datetime
import anthropic
import json

def process_email(client: anthropic.Anthropic, subject: str, body: str) -> list[dict]:
    today = date.today().isoformat()
    now = datetime.now().strftime("%H:%M")
    message = client.messages.create(
        model="claude-haiku-4-5", # 90% of Sonnet 4.5 performance at 1/3 the $$$
        max_tokens=1024, # 
        messages=[ # messages expected as list to represent conversation/exchange history
            {
                "role": "user",
                "content": f"""Is this email requesting shift coverage? If not, return an empty JSON array [].

If yes, extract all shift coverage requests. Today's date is {today} and the current time is {now}.

Subject: {subject}
Body: {body}

Return ONLY a JSON array. No preamble, no markdown, no explanation. If this is not a coverage request, return [].

Each shift object must have:
- "date": "YYYY-MM-DD" (infer year from context, use today's year if not specified)
- "start_time": "HH:MM" (24hr format)
- "end_time": "HH:MM" (24hr format, if ambiguous infer PM so the shift does not end before it starts — e.g. "10:30-1:30" means end_time is "13:30")
- "location": "SCC" | "MLC" | "MSC" | null
  (SCC = Sherwood Community Centre or any variation like "Sherwood", "SCC"
   MLC = Milton Leisure Centre or "Milton Leisure", "MLC"
   MSC = Milton Sports Centre or "Milton Sports", "MSC")
- "role": "instructor" | "guard" | "both" | null
- "level": the specific course or certification level being taught (e.g. "bronze medallion", "bronze cross", "national lifeguard", "aquafit"), or null if none mentioned or if it is a guard shift. Normalize abbreviations to their full name (e.g. "BM" → "bronze medallion", "BC" → "bronze cross", "NL" or "NLS" → "national lifeguard").
- "female_only": true if the shift is explicitly restricted to female staff (e.g. "female only", "females only", "women only"), false otherwise.

If multiple shifts exist, return all of them. If a field cannot be determined, use null."""
            }
        ]
    )

    raw = message.content[0].text.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError: # if claude returned more than just a json, try again
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start != -1 and end > start:
            return json.loads(raw[start:end])
        print(f"Failed to parse response: {raw}")
        return []