import os
import json
import base64
import flask
from googleapiclient.discovery import build

from main import get_credentials, get_whitelist, PREFERENCES_PATH, client
from gmail import read_emails, get_body, get_subject, get_sender, get_thread_id, get_message_id
from parser import process_email
from availability import final_check
from respond import send_reply, get_labels, apply_label

app = flask.Flask(__name__)


@app.route("/", methods=["POST"])
def handle_push():
    envelope = flask.request.get_json(silent=True)
    if not envelope or "message" not in envelope:
        return "Bad Request", 400

    try:
        data = json.loads(base64.b64decode(envelope["message"]["data"]).decode())
        print(f"Gmail notification for {data.get('emailAddress')}, historyId={data.get('historyId')}")
    except Exception as e:
        print(f"Could not decode notification data: {e}")

    try:
        creds = get_credentials()
        gmail_service = build("gmail", "v1", credentials=creds)
        calendar_service = build("calendar", "v3", credentials=creds)
        whitelist = get_whitelist()
        emails = read_emails(gmail_service, whitelist)

        if not emails:
            print("No emails from whitelist")
            return "OK", 200

        labels = get_labels(gmail_service)

        results = []
        for email in emails:
            try:
                body = get_body(email)
                subject = get_subject(email)
                sender = get_sender(email)
                thread_id = get_thread_id(email)
                message_id = get_message_id(email)
                shift = process_email(client, subject, body)
                results.append({
                    "sender": sender,
                    "subject": subject,
                    "thread_id": thread_id,
                    "message_id": message_id,
                    "shifts": shift,
                })
            except Exception as e:
                print(f"Error processing email {email['id']}: {e}")

        for result in results:
            try:
                # skip if another invocation already labelled this thread
                thread = gmail_service.users().threads().get(
                    userId="me", id=result["thread_id"], format="minimal"
                ).execute()
                thread_label_ids = {lid for msg in thread.get("messages", []) for lid in msg.get("labelIds", [])}
                if labels["covered"] in thread_label_ids or labels["read"] in thread_label_ids:
                    print(f"Skipping already-processed thread {result['thread_id']}")
                    continue

                shifts = result["shifts"] or []
                valid = [s for s in shifts if s.get("date") and s.get("start_time") and s.get("end_time")]
                coverable = [s for s in valid if final_check(calendar_service, PREFERENCES_PATH, s)]

                if coverable:
                    is_subset = len(coverable) < len(valid)
                    send_reply(
                        gmail_service, calendar_service, labels["covered"],
                        result["thread_id"], result["message_id"], result["subject"],
                        result["sender"], coverable, is_subset,
                    )
                    print(f"Covered: {result['sender']}")
                else:
                    apply_label(gmail_service, result["thread_id"], labels["read"])
                    print(f"Rejected: {result['sender']}")

            except Exception as e:
                print(f"Error handling result for {result['sender']}: {e}")

        return "OK", 200

    except Exception as e:
        print(f"Fatal error in handler: {e}")
        return "Internal Server Error", 500


@app.route("/renew", methods=["POST"])
def renew_watch():
    project_id = os.environ["GCP_PROJECT_ID"]
    topic = os.environ.get("PUBSUB_TOPIC", "autoguard-gmail")
    try:
        creds = get_credentials()
        gmail_service = build("gmail", "v1", credentials=creds)
        resp = gmail_service.users().watch(
            userId="me",
            body={
                "labelIds": ["INBOX"],
                "topicName": f"projects/{project_id}/topics/{topic}",
            }
        ).execute()
        print(f"Watch renewed. Expiration: {resp['expiration']}, HistoryId: {resp['historyId']}")
        return "OK", 200
    except Exception as e:
        print(f"Watch renewal failed: {e}")
        return "Error", 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)