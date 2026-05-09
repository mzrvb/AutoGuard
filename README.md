# AutoGuard
Automatic lifeguarding and swim instructing shift coverage for Gmail.

Claim shifts that correspond with your schedule and preferences, 
before anyone else does. More hours = more money.

![AutoGuard Logo](img/AutoGuard Logo.png)

## Architecture
**Language:** Python

**REST API's:** Gmail, Google Calendar, Claude, Google Cloud, Google Secret Manager, Google Cloud Build, Google Cloud Run, Google Cloud Scheduler

## Scripts
| File | Role | Key Responsibilities |
|------|------|---------------------|
| `main.py` | Local entrypoint | Builds Gmail/Calendar API services, loads the whitelist, drives the per-email loop. Only used when running locally. |
| `handler.py` | Cloud entrypoint | Flask web server that receives Pub/Sub push notifications and runs the same email pipeline as `main.py`. What Cloud Run actually executes. |
| `gmail.py` | Gmail interface | Fetches unread emails from the whitelist via single query + batch API requests, decodes email bodies (multipart MIME), marks emails as read. |
| `parser.py` | LLM extraction | Sends email subject + body to Claude Haiku, returns a JSON array of shift objects. Combined classify + extract in one API call. |
| `availability.py` | Conflict & preference checker | Checks Google Calendar for conflicts, applies preference rules: minimum notice, restricted cert levels, preferred roles, and minimum hours per location. |
| `respond.py` | Reply & booking | Sends threaded reply email, adds the AutoGuard label, creates a tentative calendar block for each covered shift. |

Other scripts that are not included are GCP-deployment specific.
## Optimizations
**Evalutes for:**
1. Conflicting schedules/events by checking google calendar
2. Last second coverage requests by checking if the time a shift starts is less than "min_notice_minutes", set in preferences
3. Teaching certification requirements by checking if levels mentioned in email are in "restricted", set in preferences
4. Undesired roles by checking "preferred_role", set in preferences
5. Undesired shifts by checking "min_hours" for different locations, set in preferences

## Lessons Learned:
**What I learned developing AutoGuard:**
1. Batch email fetching, optimize query to send `messages.get` in one batch request rather than for each individual email
2. How to read Googles horrendous documentation.
3. Use Claude Haiku instead of Sonnet, 3x cheaper tokens, high performance, fast response, simple classification
4. Program's that automate responses should be event driven, not polling. Pub/ Sub implementation addresses this as I initially began with a 60 second loop.
5. GCP. It was really hard.
6. OAuth token management in a serverless environment — refresh tokens, Secret Manager, and why you can't write back to disk in Cloud Run
7. Duplicate processing in event-driven systems — Pub/Sub delivers at-least-once, so concurrent invocations need idempotency guards (the AutoGuard label check)





