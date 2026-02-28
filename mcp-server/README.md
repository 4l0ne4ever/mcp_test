# Spotify MCP Server

Python MCP server ket noi Spotify Web API — cho phep tim kiem nhac, xem bai dang phat,
top tracks, va dieu khien playback qua Claude Code CLI.

## Tai sao chon Spotify MCP?

- Ket hop doc + ghi: tim kiem (doc) + dieu khien playback (ghi)
- Goi external API (Spotify Web API) — khong chi doc local
- Ca nhan hoa — AI biet ban nghe nhac gi, dang phat gi
- Thuc te va huu ich — dieu khien nhac bang ngon ngu tu nhien

## Cau truc thu muc

```
mcp-server/
├── spotify_mcp_server.py <- MCP Server chinh
├── server_config.json    <- Tool descriptions, scopes, prompts
├── test_connection.py    <- First-time OAuth auth
├── requirements.txt
├── .env                  <- Spotify credentials (gitignored)
├── .env.example          <- Template
├── .spotify_cache        <- OAuth token (gitignored, auto-generated)
├── .gitignore
└── README.md
```

## Cai dat

### 1. Tao Spotify Developer App

1. Vao https://developer.spotify.com/dashboard
2. Create App
3. App name: "MCP Server" (bat ky)
4. Redirect URI: `http://localhost:8888/callback`
5. APIs: chon "Web API"
6. Copy Client ID va Client Secret

### 2. Cai dependencies

```bash
cd mcp-server
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Cau hinh .env

```bash
cp .env.example .env
# Dien SPOTIFY_CLIENT_ID va SPOTIFY_CLIENT_SECRET
```

### 4. Xac thuc OAuth (lan dau)

```bash
python3 test_connection.py
# Mo browser, dang nhap Spotify, cho phep quyen
```

### 5. Dang ky voi Claude Code CLI

```bash
claude mcp add spotify-mcp -- "$(pwd)/venv/bin/python3" "$(pwd)/spotify_mcp_server.py"
```

## Tools

| Tool | Mo ta |
|------|-------|
| `search_tracks` | Tim bai hat, artist, album |
| `get_now_playing` | Bai dang phat hien tai |
| `get_top_tracks` | Top bai hat nghe nhieu nhat |
| `control_playback` | Play/pause/next/previous |
