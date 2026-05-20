#!/usr/bin/env python3
"""
Register Gmail push notifications to Pub/Sub.
Run once after initial deploy; Cloud Scheduler calls /renew weekly after that.

Usage (from project root):
    export GCP_PROJECT_ID=your-project-id
    python deploy/setup_watch.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from googleapiclient.discovery import build
from main import get_credentials

PROJECT_ID = os.environ["GCP_PROJECT_ID"]
TOPIC = os.environ.get("PUBSUB_TOPIC", "autoguard-gmail")


def main():
    creds = get_credentials()
    gmail_service = build("gmail", "v1", credentials=creds)
    resp = gmail_service.users().watch(
        userId="me",
        body={
            "labelIds": ["INBOX"],
            "topicName": f"projects/{PROJECT_ID}/topics/{TOPIC}",
        }
    ).execute()
    expiry_ms = int(resp["expiration"])
    expiry_days = expiry_ms / 1000 / 86400
    print(f"Gmail watch registered.")
    print(f"  Topic:     projects/{PROJECT_ID}/topics/{TOPIC}")
    print(f"  HistoryId: {resp['historyId']}")
    print(f"  Expires:   in ~{expiry_days:.1f} days (Cloud Scheduler renews weekly)")


if __name__ == "__main__":
    main()
