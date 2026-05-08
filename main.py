# AutoGuard functions
from gmail import get_subject, get_body, get_sender, get_thread_id, get_message_id, read_emails, mark_as_read
from parser import process_email
from availability import final_check
from respond import send_reply, get_or_create_label

# config, data, and env
import json
import os
from dotenv import load_dotenv
from datetime import datetime

# google python quickstart
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# anthropic claude
import anthropic
client = anthropic.Anthropic()

load_dotenv()
TOKEN_PATH = os.getenv("TOKEN_PATH", "config/token.json")
PREFERENCES_PATH = "staff/preferences.json"
WHITELIST_PATH = os.getenv("WHITELIST_PATH", "staff/emails.json")

# Get credentials for services
def get_credentials():
    with open(TOKEN_PATH) as file:
        token_data = json.load(file)

    creds = Credentials.from_authorized_user_info(token_data)

    # creds expired, refresh
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_PATH, "w") as file:
            file.write(creds.to_json())

    return creds

# Get staff emails
def get_whitelist():
    with open(WHITELIST_PATH) as file:
        return json.load(file)["staff_emails"]

def main():
    # use credentials to build services
    creds = get_credentials()
    gmail_service = build("gmail", "v1", credentials=creds)
    calendar_service = build("calendar", "v3", credentials=creds)

    # check if any unread emails from whitelist senders
    whitelist = get_whitelist()
    emails = read_emails(gmail_service, whitelist)

    if not emails:
        print("No emails")
        return

    label_id = get_or_create_label(gmail_service)

    results = []
    for email in emails:
        try:
            # scrape the following information for each email
            body = get_body(email)
            subject = get_subject(email)
            sender = get_sender(email)
            thread_id = get_thread_id(email)
            message_id = get_message_id(email)

            # determine if shift using claude parser, return bool
            shift = process_email(client, subject, body)
            mark_as_read(gmail_service, email["id"])

            if shift:
                results.append({
                    "sender": sender,
                    "subject": subject,
                    "thread_id": thread_id,
                    "message_id": message_id,
                    "shifts": shift
                })
        except Exception as e:
            print(f"Error processing email {email['id']}: {e}")

    for result in results: # loop through emails
        try:
            # valid: a list of all shifts from all emails checked
            valid = [s for s in result["shifts"] if s.get("date")
                      and s.get("start_time") and s.get("end_time")]

            # coverable: a subset of valid shifts that pass final_check
            coverable = [s for s in valid if final_check(calendar_service, PREFERENCES_PATH, s)]

            if coverable:
                is_subset = len(coverable) < len(valid) # bool, determines specific responses or easy "I can cover!"
                send_reply(gmail_service, calendar_service, label_id, 
                           result["thread_id"], result["message_id"], result["subject"], 
                           result["sender"], coverable, is_subset)
        except Exception as e:
            print(f"Error handling result for {result['sender']}: {e}")

if __name__ == "__main__":
    start_time = datetime.now()
    main()
    end_time = datetime.now()

    elapsed_time = end_time - start_time
    print(f"Execution time: {elapsed_time}")