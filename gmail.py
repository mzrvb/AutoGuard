import base64

def read_emails(service, whitelist):
    relevant = []
    batch = service.new_batch_http_request()

    query = 'newer_than:1d -label:"AutoGuard C" -label:"AutoGuard R" from:(' + " OR ".join(whitelist) + ")"
    results = service.users().messages().list(userId="me", q=query).execute()
    messages = results.get("messages", [])

    if not messages:
        return []

    def callback(request_id, response, exception):
        if exception is None:
            relevant.append(response)

    for msg in messages:
        batch.add(
            service.users().messages().get(userId="me", id=msg["id"], format="full"),
            callback=callback
        )

    batch.execute()
    return relevant

def _extract_text(part):
    mime = part.get("mimeType", "")
    if mime == "text/plain":
        data = part.get("body", {}).get("data")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8")
    if mime.startswith("multipart/"):
        for subpart in part.get("parts", []):
            result = _extract_text(subpart)
            if result:
                return result
    return None

def get_body(message):
    return _extract_text(message["payload"])

def get_sender(message):
    headers = message["payload"]["headers"]
    for header in headers:
        if header["name"] == "From":
            return header["value"]
    return None

def get_subject(message):
    headers = message["payload"]["headers"]
    for header in headers:
        if header["name"] == "Subject":
            return header["value"]
    return None

def get_thread_id(message):
    return message["threadId"]

def get_message_id(message):
    headers = message["payload"]["headers"]
    for header in headers:
        if header["name"] == "Message-ID":
            return header["value"]
    return ""