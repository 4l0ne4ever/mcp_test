"""
Gmail MCP Server (Python)
All tool descriptions, prompts, scopes, and server metadata
are loaded from server_config.json.
All sensitive paths are loaded from .env.
"""

# Force IPv4 — Python defaults to IPv6 which may timeout on some networks
import socket
_orig_getaddrinfo = socket.getaddrinfo
def _ipv4_getaddrinfo(*args, **kwargs):
    return [r for r in _orig_getaddrinfo(*args, **kwargs) if r[0] == socket.AF_INET]
socket.getaddrinfo = _ipv4_getaddrinfo

import asyncio
import base64
import json
import logging
import os
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

# ── Logging (stderr only — stdout is reserved for MCP stdio protocol) ──────────
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s │ %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("gmail-mcp")

from dotenv import load_dotenv

# ── Load .env ──────────────────────────────────────────────────────────────────
_BASE_DIR = Path(__file__).parent
load_dotenv(dotenv_path=_BASE_DIR / ".env")

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

# Google libs are imported lazily in _init_gmail_service() to speed up startup

# ── Load server_config.json ────────────────────────────────────────────────────
_CONFIG_PATH = _BASE_DIR / "server_config.json"
with open(_CONFIG_PATH, "r", encoding="utf-8") as _f:
    _CFG = json.load(_f)

# Aliases for clarity
_SERVER_CFG  = _CFG["server"]
_SCOPES      = _CFG["gmail"]["scopes"]
_TOOLS_CFG   = _CFG["tools"]
_PROMPTS     = _CFG["prompts"]

# ── Sensitive paths from .env ──────────────────────────────────────────────────
CREDENTIALS_FILE = os.getenv("GMAIL_CREDENTIALS_FILE", str(_BASE_DIR / "credentials.json"))
TOKEN_FILE       = os.getenv("GMAIL_TOKEN_FILE",       str(_BASE_DIR / "token.json"))

# ── Gmail auth (initialized once at startup) ──────────────────────────────────

def _init_gmail_service():
    """Build and return Gmail service, refreshing token if needed.
    Google libs imported HERE (not at module level) so MCP handshake completes fast.
    """
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    log.info("Initializing Gmail auth...")
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, _SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            log.info("Token expired — refreshing...")
            creds.refresh(Request())
            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
            log.info("Token refreshed successfully")
        else:
            raise RuntimeError(
                "No valid token found. Run test_connection.py first to authenticate."
            )
    service = build(
        "gmail", "v1",
        credentials=creds,
        cache_discovery=True,
    )
    log.info("Gmail service ready")
    return service

# Background pre-loading: starts init in a thread so it happens DURING MCP handshake,
# not BEFORE it (blocking) and not AFTER first tool call (timeout).
import threading

log.info("Gmail MCP Server starting...")
_SERVICE = None
_SERVICE_LOCK = threading.Lock()
_SERVICE_ERROR = None

def _bg_init():
    """Run in background thread: import Google libs + authenticate."""
    global _SERVICE, _SERVICE_ERROR
    try:
        svc = _init_gmail_service()
        with _SERVICE_LOCK:
            _SERVICE = svc
        log.info("Background init complete — Gmail service ready")
    except Exception as e:
        _SERVICE_ERROR = e
        log.error("Background init failed: %s", e)

# Start background init immediately (runs while MCP handshake happens)
_init_thread = threading.Thread(target=_bg_init, daemon=True)
_init_thread.start()

def get_gmail_service():
    """Wait for background init to finish, then return cached service."""
    _init_thread.join(timeout=30)
    if _SERVICE_ERROR:
        raise _SERVICE_ERROR
    if _SERVICE is None:
        raise RuntimeError("Gmail service not initialized")
    return _SERVICE




# ── Helpers ────────────────────────────────────────────────────────────────────

def decode_body(payload):
    """Recursively extract plain text body from email payload."""
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    for part in payload.get("parts", []):
        result = decode_body(part)
        if result:
            return result
    return ""


def parse_headers(headers: list) -> dict:
    return {h["name"]: h["value"] for h in headers}


def format_email_summary(msg: dict) -> str:
    payload = msg.get("payload", {})
    headers = parse_headers(payload.get("headers", []))
    body = decode_body(payload)
    first_10_words = " ".join(body.split()[:10]) if body else "(no body)"
    return (
        f"ID: {msg['id']}\n"
        f"From: {headers.get('From', 'Unknown')}\n"
        f"To: {headers.get('To', 'Unknown')}\n"
        f"Subject: {headers.get('Subject', '(no subject)')}\n"
        f"Date: {headers.get('Date', 'Unknown')}\n"
        f"First 10 words: {first_10_words}\n"
        f"Snippet: {msg.get('snippet', '')}"
    )


# ── MCP Server ─────────────────────────────────────────────────────────────────

app = Server(_SERVER_CFG["name"])


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    """Build tool list dynamically from server_config.json."""
    return [
        types.Tool(
            name=tool_name,
            description=tool_def["description"],
            inputSchema=tool_def["inputSchema"],
        )
        for tool_name, tool_def in _TOOLS_CFG.items()
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    log.info("Tool called: %s | args: %s", name, arguments)
    service = get_gmail_service()

    # ── search_emails ──────────────────────────────────────────────────────────
    if name == "search_emails":
        query = arguments["query"]
        max_results = arguments.get("max_results", 5)
        log.info("Searching: query='%s', max=%d", query, max_results)

        result = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )
        messages = result.get("messages", [])
        if not messages:
            log.info("No emails found for query: '%s'", query)
            return [types.TextContent(type="text", text=_PROMPTS["no_emails_found"])]

        log.info("Found %d email(s) — fetching metadata...", len(messages))
        summaries = []
        for m in messages:
            # metadata only: headers + snippet, no body — much faster
            msg = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=m["id"],
                    format="metadata",
                    metadataHeaders=["Subject", "From", "To", "Date"],
                )
                .execute()
            )
            headers = parse_headers(msg.get("payload", {}).get("headers", []))
            summaries.append(
                f"ID: {m['id']}\n"
                f"Subject: {headers.get('Subject', '(no subject)')}\n"
                f"From: {headers.get('From', '')}\n"
                f"To: {headers.get('To', '')}\n"
                f"Date: {headers.get('Date', '')}\n"
                f"Snippet: {msg.get('snippet', '')}"
            )

        log.info("search_emails done — returned %d result(s)", len(summaries))
        return [types.TextContent(type="text", text="\n\n---\n\n".join(summaries))]

    # ── get_email ──────────────────────────────────────────────────────────────
    elif name == "get_email":
        email_id = arguments["email_id"]
        log.info("Fetching email ID: %s", email_id)
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=email_id, format="full")
            .execute()
        )
        payload = msg.get("payload", {})
        headers = parse_headers(payload.get("headers", []))
        body = decode_body(payload)

        text = (
            f"ID: {msg['id']}\n"
            f"Thread ID: {msg['threadId']}\n"
            f"From: {headers.get('From', '')}\n"
            f"To: {headers.get('To', '')}\n"
            f"Subject: {headers.get('Subject', '')}\n"
            f"Date: {headers.get('Date', '')}\n"
            f"Message-ID: {headers.get('Message-ID', '')}\n\n"
            f"Body:\n{body}"
        )
        log.info("get_email done — subject: '%s'", headers.get('Subject', ''))
        return [types.TextContent(type="text", text=text)]

    # ── reply_email ────────────────────────────────────────────────────────────
    elif name == "reply_email":
        email_id = arguments["email_id"]
        reply_body = arguments["reply_body"]
        log.info("Replying to email ID: %s", email_id)

        original = (
            service.users()
            .messages()
            .get(userId="me", id=email_id, format="full")
            .execute()
        )
        orig_headers = parse_headers(original["payload"].get("headers", []))
        thread_id = original["threadId"]

        from email.utils import parseaddr
        raw_from = orig_headers.get("From", "")
        _, to_addr = parseaddr(raw_from)
        if not to_addr:
            to_addr = raw_from
        subject = orig_headers.get("Subject", "")
        message_id_header = orig_headers.get("Message-ID", "")

        reply = MIMEMultipart()
        reply["To"] = to_addr
        reply["Subject"] = f"Re: {subject}" if not subject.startswith("Re:") else subject
        reply["In-Reply-To"] = message_id_header
        reply["References"] = message_id_header
        reply.attach(MIMEText(reply_body, "plain"))

        raw = base64.urlsafe_b64encode(reply.as_bytes()).decode()
        sent = (
            service.users()
            .messages()
            .send(userId="me", body={"raw": raw, "threadId": thread_id})
            .execute()
        )
        log.info("Reply sent! Message ID: %s", sent['id'])
        return [
            types.TextContent(
                type="text",
                text=(
                    f"{_PROMPTS['reply_success']}\n"
                    f"Message ID: {sent['id']}\n"
                    f"Thread ID: {sent['threadId']}"
                ),
            )
        ]

    else:
        log.warning("Unknown tool: %s", name)
        return [
            types.TextContent(
                type="text",
                text=_PROMPTS["unknown_tool"].format(tool_name=name),
            )
        ]


# ── Entry point ────────────────────────────────────────────────────────────────

async def main():
    """Run as stdio transport."""
    log.info("MCP server listening on stdin/stdout...")
    try:
        async with stdio_server() as (read_stream, write_stream):
            log.info("Connected — server is RUNNING")
            await app.run(read_stream, write_stream, app.create_initialization_options())
    except Exception as e:
        log.error("Server error: %s", e)
        raise
    finally:
        log.info("Server STOPPED")


if __name__ == "__main__":
    asyncio.run(main())


