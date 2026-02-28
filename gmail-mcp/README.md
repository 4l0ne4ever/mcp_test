# Gmail MCP Server

Python MCP server tich hop Gmail API — cho phep tim kiem, doc, va reply email truc tiep qua Claude Code CLI.

---

## Cau truc thu muc

```
gmail-mcp/
├── gmail_mcp_server.py   <- MCP Server chinh
├── server_config.json    <- Tool descriptions, prompts, OAuth scopes
├── mcp_config.json       <- Template config tham chieu
├── requirements.txt      <- Python dependencies
├── .env                  <- Sensitive paths (gitignored)
├── .env.example          <- Template .env (safe to commit)
├── .gitignore
├── credentials.json      <- OAuth client (gitignored, tai tu GCloud)
└── token.json            <- OAuth token (gitignored, tu dong tao)
```

---

## Cai dat lan dau

### 1. Google Cloud credentials

1. Vao Google Cloud Console -> project cua ban
2. APIs & Services -> Gmail API -> bat neu chua co
3. Credentials -> OAuth 2.0 Client ID (Desktop app) -> tai JSON -> doi ten thanh `credentials.json`
4. Audience -> them email cua ban vao Test users
5. Data Access -> dam bao co 3 Gmail scopes:
   - `gmail.readonly`, `gmail.send`, `gmail.modify`

### 2. Cai dependencies

```bash
cd gmail-mcp
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Cau hinh `.env`

```bash
cp .env.example .env
# Chinh sua .env voi duong dan thuc te cua ban
```

Noi dung `.env`:
```bash
GMAIL_VENV_PYTHON=/absolute/path/to/gmail-mcp/venv/bin/python3
GMAIL_SERVER_PATH=/absolute/path/to/gmail-mcp/gmail_mcp_server.py
GMAIL_CREDENTIALS_FILE=/absolute/path/to/gmail-mcp/credentials.json
GMAIL_TOKEN_FILE=/absolute/path/to/gmail-mcp/token.json
```

### 4. Xac thuc OAuth (lan dau)

```bash
source venv/bin/activate
python3 gmail_mcp_server.py --stdio
```

Lan dau server se load token tu `token.json`. Neu token chua co, chay `test_connection.py` de tao.

### 5. Dang ky voi Claude Code CLI

```bash
claude mcp add gmail-mcp -- "$(pwd)/venv/bin/python3" "$(pwd)/gmail_mcp_server.py" --stdio
```

### 6. Kiem tra ket noi

```bash
claude mcp list
# Expected: gmail-mcp: ... Connected
```

---

## Cach su dung

Chi can 1 terminal:

```bash
cd gmail-mcp
claude
```

Trong Claude Code, go tu nhien:

### Tim email ung tuyen da gui
```
Tim email ung tuyen toi da gui trong hop thu Sent, tieu de chua keyword "intern"
```

### Doc chi tiet email (ngay gio + 10 tu dau)
```
Lay noi dung day du cua email ID <email_id>
```

### Reply email qua MCP (khong dung Gmail UI)
```
Reply email <email_id> voi noi dung: "Cam on ban da phan hoi..."
```

---

## Tools co san

| Tool | Tham so | Mo ta |
|------|---------|-------|
| `search_emails` | `query` (string), `max_results` (int, mac dinh 5) | Tim email theo Gmail search syntax |
| `get_email` | `email_id` (string) | Doc noi dung day du 1 email theo ID |
| `reply_email` | `email_id` (string), `reply_body` (string) | Reply email qua Gmail API, giu nguyen thread |

### Gmail search query huu ich

```
in:sent                        # Chi trong Sent Mail
subject:intern                 # Theo tieu de
to:recruiter@company.com       # Theo nguoi nhan
after:2024/01/01               # Sau ngay cu the
in:sent (CV OR resume OR apply) # Ket hop nhieu tu khoa
```

---

## Bao mat

| File | Commit duoc khong? | Ly do |
|------|--------------------|-------|
| `.env` | Khong | Chua duong dan tuyet doi |
| `credentials.json` | Khong | OAuth client secret |
| `token.json` | Khong | Access token |
| `server_config.json` | Co | Chi chua descriptions |
| `mcp_config.json` | Co | Chi chua template |
| `.env.example` | Co | Template khong co gia tri that |
