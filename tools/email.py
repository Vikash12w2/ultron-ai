from __future__ import annotations

import re
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import quote, urlencode

from config import GMAIL_APP_PASSWORD_KEY, GMAIL_SMTP, MAX_EMAIL_RECIPIENTS
from core import secrets
from security.approvals import ApprovalGate, ApprovalRequest

EMAIL_RE = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")
MAX_LINK_BODY = 1800


def parse_recipients(to: str) -> list[str]:
    addresses = [a.strip() for a in re.split(r"[,;]", to or "") if a.strip()]
    if not addresses:
        raise ValueError("No recipient address.")
    bad = [a for a in addresses if not EMAIL_RE.match(a)]
    if bad:
        raise ValueError(f"Not valid email address(es): {', '.join(bad)}. Use find_contact or ask the user.")
    if len(addresses) > MAX_EMAIL_RECIPIENTS:
        raise ValueError(f"At most {MAX_EMAIL_RECIPIENTS} recipients.")
    return addresses


def find_contact(contacts: list[dict], name: str) -> dict:
    """contacts: [{"name": "Rahul", "email": "rahul@..."}] saved in Settings → Email."""
    wanted = (name or "").casefold().strip()
    if not wanted:
        raise ValueError("No name given.")
    matches = [c for c in contacts if wanted in c.get("name", "").casefold() or wanted == c.get("email", "").casefold()]
    if not matches:
        return {"matches": [], "note": f"No saved contact matches '{name}'. Ask the user for the address "
                                        "(they can save contacts in Settings → Email)."}
    return {"matches": matches[:5]}


class EmailTools:
    def __init__(self, gate: ApprovalGate, open_url, gmail_address: str = "", get_key=None, smtp_factory=None):
        self.gate = gate
        self.open_url = open_url
        self.gmail_address = gmail_address
        self.get_key = get_key or (lambda name: secrets.get_key(name))
        self.smtp_factory = smtp_factory or (lambda host, port: smtplib.SMTP(host, port, timeout=20))

    def compose_email(self, to: str, subject: str, body: str) -> dict:
        """Opens a prefilled Gmail compose window. Nothing is sent."""
        recipients = parse_recipients(to)
        note = ""
        if len(body) > MAX_LINK_BODY:
            body, note = body[:MAX_LINK_BODY], "The body was too long for a draft link and was cut; finish it in Gmail."
        query = urlencode({"tf": "cm", "to": ",".join(recipients), "su": subject, "body": body}, quote_via=quote)
        result = self.open_url(f"https://mail.google.com/mail/u/0/?{query}")
        return {"status": "draft_opened", "to": recipients, "browser": result.get("status"),
                "next": "The user can review and send it in Gmail, or ask ULTRON to press Ctrl+Enter in Chrome "
                        "(needs approval).", **({"note": note} if note else {})}

    def send_email(self, to: str, subject: str, body: str, reason: str = "") -> dict:
        password = self.get_key(GMAIL_APP_PASSWORD_KEY)
        if not self.gmail_address or not password:
            raise RuntimeError("Direct sending isn't set up (Settings → Email: Gmail address + app password). "
                               "Use compose_email to open a draft instead.")
        parse_recipients(to)
        req = self.gate.require(ApprovalRequest(
            "send_email", "Send an email", {"From": self.gmail_address, "To": to, "Subject": subject}, reason,
            preview=body, editable=("To", "Subject", "Preview"),
            warning="This sends a real email from your Gmail. Edit anything before approving."))
        final_to = parse_recipients(req.value("To"))
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.gmail_address, ", ".join(final_to), req.value("Subject")
        msg.set_content(req.value("Preview"))
        host, port = GMAIL_SMTP
        with self.smtp_factory(host, port) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(self.gmail_address, password)
            smtp.send_message(msg)
        return {"status": "sent", "to": final_to, "subject": req.value("Subject")}
