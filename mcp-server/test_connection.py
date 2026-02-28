"""
Spotify OAuth — first-time authentication.
Run this once to generate .spotify_cache token file.
"""
# Force IPv4
import socket
_orig = socket.getaddrinfo
socket.getaddrinfo = lambda *a, **k: [r for r in _orig(*a, **k) if r[0] == socket.AF_INET]

import os
from pathlib import Path
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth

load_dotenv(Path(__file__).parent / ".env")

SCOPES = " ".join([
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
    "user-top-read",
    "playlist-read-private",
])

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=os.getenv("SPOTIFY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
    redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback"),
    scope=SCOPES,
    cache_path=str(Path(__file__).parent / ".spotify_cache"),
))

user = sp.current_user()
print(f"Authenticated as: {user['display_name']} ({user['id']})")
print("Token saved to .spotify_cache")
