import base64
from email.mime.text import MIMEText
from email.utils import parseaddr
from datetime import datetime
from availability import to_datetime_str

# "May 8th" from "2026-05-08"
def _format_date(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    day = dt.day
    suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return dt.strftime(f"%B {day}{suffix}")

# "5:00 PM" from "17:00"
def _format_time(time_str: str) -> str:
    dt = datetime.strptime(time_str, "%H:%M")
    return dt.strftime("%I:%M %p").lstrip("0")

def _get_or_create(gmail_service, name: str) -> str:
    labels = gmail_service.users().labels().list(userId="me").execute()
    for label in labels.get("labels", []):
        if label["name"] == name:
            return label["id"]
    created = gmail_service.users().labels().create(
        userId="me", body={"name": name}
    ).execute()
    return created["id"]

def get_labels(gmail_service) -> dict:
    return {
        "covered": _get_or_create(gmail_service, "AutoGuard C"),
        "read":    _get_or_create(gmail_service, "AutoGuard R"),
    }

def apply_label(gmail_service, thread_id: str, label_id: str):
    gmail_service.users().threads().modify(
        userId="me", id=thread_id,
        body={"addLabelIds": [label_id]}
    ).execute()

def _add_calendar_event(calendar_service, shift: dict, sender: str):
    # build event title from role and location
    role_map = {"guard": "Guarding", "instructor": "Instructing", "both": "Both"}
    role_label = role_map.get(shift.get("role"), "")
    location = shift.get("location") or ""

    title = "AutoGuard"
    if role_label:
        title += f" ({role_label})"
    if location:
        title += f" @{location}"

    # extract display name from "Name <email>" format
    name, _ = parseaddr(sender)
    description = f"Covering: {name or sender}"

    # insert tentative event — confirmed manually once sender selects you
    calendar_service.events().insert(
        calendarId="primary",
        body={
            "summary": title,
            "description": description,
            "start": {"dateTime": to_datetime_str(shift["date"], shift["start_time"])},
            "end": {"dateTime": to_datetime_str(shift["date"], shift["end_time"])},
            "colorId": "9",  # blueberry
            "status": "tentative",
        }
    ).execute()

def send_reply(gmail_service, calendar_service, label_id: str, thread_id: str, message_id: str, subject: str, sender: str, shifts: list, is_subset: bool):
    # prefix subject with Re: for threading
    if not subject.startswith("Re:"):
        subject = "Re: " + subject

    # full coverage: simple reply. partial: list only the shifts we can cover
    if not is_subset:
        body = "I can cover!"
    else:
        lines = ["I can cover"]
        for s in shifts:
            lines.append(f"- {_format_date(s['date'])} {_format_time(s['start_time'])}–{_format_time(s['end_time'])}")
        body = "\n".join(lines)

    # build and encode the MIME email
    msg = MIMEText(body)
    msg["To"] = sender
    msg["Subject"] = subject
    msg["In-Reply-To"] = message_id
    msg["References"] = message_id

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    # send reply in the original thread
    gmail_service.users().messages().send(
        userId="me",
        body={"raw": raw, "threadId": thread_id}
    ).execute()

    apply_label(gmail_service, thread_id, label_id)

    # add a tentative calendar block for each covered shift
    for s in shifts:
        _add_calendar_event(calendar_service, s, sender)