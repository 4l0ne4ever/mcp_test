"""
Spotify MCP Server
Provides Spotify control and search via MCP tools.
All tool descriptions and prompts loaded from server_config.json.
All sensitive credentials loaded from .env.
"""

# Force IPv4 — Python may try IPv6 first causing timeout on some networks
import socket
_orig_getaddrinfo = socket.getaddrinfo
def _ipv4_getaddrinfo(*args, **kwargs):
    return [r for r in _orig_getaddrinfo(*args, **kwargs) if r[0] == socket.AF_INET]
socket.getaddrinfo = _ipv4_getaddrinfo

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

# ── Logging (stderr only) ─────────────────────────────────────────────────────
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("spotify-mcp")

# ── Load .env & config ────────────────────────────────────────────────────────
_BASE_DIR = Path(__file__).parent
load_dotenv(_BASE_DIR / ".env")

with open(_BASE_DIR / "server_config.json", "r", encoding="utf-8") as _f:
    _CFG = json.load(_f)

_SERVER_CFG = _CFG["server"]
_TOOLS_CFG = _CFG["tools"]
_PROMPTS = _CFG["prompts"]
_SCOPES = " ".join(_CFG["spotify"]["scopes"])

# ── Spotify auth (lazy loaded in background thread) ───────────────────────────
import threading

log.info("Spotify MCP Server starting...")
_SP = None
_SP_LOCK = threading.Lock()
_SP_ERROR = None

def _init_spotify():
    """Import spotipy and authenticate."""
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth

    log.info("Initializing Spotify auth...")
    auth = SpotifyOAuth(
        client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
        redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback"),
        scope=_SCOPES,
        cache_path=str(_BASE_DIR / ".spotify_cache"),
    )
    sp = spotipy.Spotify(auth_manager=auth)
    log.info("Spotify service ready")
    return sp

def _bg_init():
    global _SP, _SP_ERROR
    try:
        sp = _init_spotify()
        with _SP_LOCK:
            _SP = sp
        log.info("Background init complete")
    except Exception as e:
        _SP_ERROR = e
        log.error("Background init failed: %s", e)

_init_thread = threading.Thread(target=_bg_init, daemon=True)
_init_thread.start()

def get_spotify():
    _init_thread.join(timeout=30)
    if _SP_ERROR:
        raise _SP_ERROR
    if _SP is None:
        raise RuntimeError("Spotify not initialized")
    return _SP


# ── MCP Server ────────────────────────────────────────────────────────────────

app = Server(_SERVER_CFG["name"])


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name=name,
            description=tool["description"],
            inputSchema=tool["inputSchema"],
        )
        for name, tool in _TOOLS_CFG.items()
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    log.info("Tool called: %s | args: %s", name, arguments)
    sp = get_spotify()

    # ── search_tracks ─────────────────────────────────────────────────────────
    if name == "search_tracks":
        query = arguments["query"]
        search_type = arguments.get("search_type", "track")
        limit = arguments.get("limit", 5)

        results = sp.search(q=query, type=search_type, limit=limit)

        key = search_type + "s"
        items = results.get(key, {}).get("items", [])

        if not items:
            return [types.TextContent(type="text", text=_PROMPTS["no_results"])]

        lines = [f"=== Search: '{query}' ({search_type}) ==="]
        for i, item in enumerate(items, 1):
            if search_type == "track":
                artists = ", ".join(a["name"] for a in item["artists"])
                lines.append(
                    f"{i}. {item['name']} — {artists}\n"
                    f"   Album: {item['album']['name']}\n"
                    f"   URI: {item['uri']}"
                )
            elif search_type == "artist":
                genres = ", ".join(item.get("genres", [])[:3]) or "N/A"
                lines.append(
                    f"{i}. {item['name']}\n"
                    f"   Followers: {item['followers']['total']:,}\n"
                    f"   Genres: {genres}\n"
                    f"   URI: {item['uri']}"
                )
            elif search_type == "album":
                artists = ", ".join(a["name"] for a in item["artists"])
                lines.append(
                    f"{i}. {item['name']} — {artists}\n"
                    f"   Released: {item.get('release_date', 'N/A')}\n"
                    f"   Tracks: {item.get('total_tracks', '?')}\n"
                    f"   URI: {item['uri']}"
                )

        text = "\n".join(lines)
        log.info("search_tracks done — %d results", len(items))
        return [types.TextContent(type="text", text=text)]

    # ── get_now_playing ───────────────────────────────────────────────────────
    elif name == "get_now_playing":
        current = sp.current_playback()

        if not current or not current.get("item"):
            return [types.TextContent(type="text", text=_PROMPTS["no_playback"])]

        track = current["item"]
        artists = ", ".join(a["name"] for a in track["artists"])
        progress_ms = current.get("progress_ms", 0)
        duration_ms = track.get("duration_ms", 0)

        def ms_to_time(ms):
            s = ms // 1000
            return f"{s // 60}:{s % 60:02d}"

        device = current.get("device", {})
        text = (
            f"=== Now Playing ===\n"
            f"Track: {track['name']}\n"
            f"Artist: {artists}\n"
            f"Album: {track['album']['name']}\n"
            f"Progress: {ms_to_time(progress_ms)} / {ms_to_time(duration_ms)}\n"
            f"Device: {device.get('name', 'Unknown')} ({device.get('type', 'Unknown')})\n"
            f"Shuffle: {'On' if current.get('shuffle_state') else 'Off'}\n"
            f"URI: {track['uri']}"
        )
        log.info("get_now_playing done — %s by %s", track['name'], artists)
        return [types.TextContent(type="text", text=text)]

    # ── get_top_tracks ────────────────────────────────────────────────────────
    elif name == "get_top_tracks":
        time_range = arguments.get("time_range", "medium_term")
        limit = arguments.get("limit", 10)

        results = sp.current_user_top_tracks(limit=limit, time_range=time_range)
        items = results.get("items", [])

        range_labels = {
            "short_term": "4 weeks",
            "medium_term": "6 months",
            "long_term": "all time",
        }

        lines = [f"=== Top {limit} Tracks ({range_labels.get(time_range, time_range)}) ==="]
        for i, track in enumerate(items, 1):
            artists = ", ".join(a["name"] for a in track["artists"])
            lines.append(f"{i}. {track['name']} — {artists}")

        text = "\n".join(lines)
        log.info("get_top_tracks done — %d tracks", len(items))
        return [types.TextContent(type="text", text=text)]

    # ── control_playback ──────────────────────────────────────────────────────
    elif name == "control_playback":
        action = arguments["action"]

        try:
            if action == "play":
                sp.start_playback()
            elif action == "pause":
                sp.pause_playback()
            elif action == "next":
                sp.next_track()
            elif action == "previous":
                sp.previous_track()
            else:
                return [types.TextContent(type="text", text=f"Unknown action: {action}")]

            text = f"{_PROMPTS['playback_success']}\nAction: {action}"
            log.info("control_playback done — action: %s", action)
            return [types.TextContent(type="text", text=text)]

        except Exception as e:
            error_msg = str(e)
            if "NO_ACTIVE_DEVICE" in error_msg or "404" in error_msg:
                return [types.TextContent(type="text", text=_PROMPTS["no_playback"])]
            raise

    else:
        log.warning("Unknown tool: %s", name)
        return [
            types.TextContent(
                type="text",
                text=_PROMPTS["unknown_tool"].format(tool_name=name),
            )
        ]


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
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
