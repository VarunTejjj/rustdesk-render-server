# RustDesk-like Render Server (Admin + Session Bridge)

This small Flask app provides:
- Session registration endpoint (`/register`)
- Image upload endpoint (`/upload`)
- Admin UI at `/admin` where you can enter session ID + password and view live screen (auto-refresh)
- Sessions list: `/sessions` (JSON)

## Deploy
1. Create repo, push to GitHub.
2. Connect repo to Render (Web Service) and set environment variables:
   - `GLOBAL_PASSWORD` (default `@MadMax31`)
   - `TELEGRAM_BOT_TOKEN` (optional)
   - `TELEGRAM_CHAT_ID` (optional)

Render start command uses `gunicorn server:app`.

## API (for clients)
- `POST /register` with JSON `{ "session_id": "sess_xxx" }` → registers session (server will notify Telegram).
- `POST /upload` with JSON `{ "session_id": "sess_xxx", "image": "<base64-jpg-or-png>" }` → saves latest image for that session.
- `GET /sessions` → returns sessions JSON.
- Admin UI: `/admin`

## Notes
- This is a simple HTTP-based prototype (image polling). For true low-latency streaming use WebRTC and TURN.
- Protect your secrets. Do not embed `TELEGRAM_BOT_TOKEN` in a client.
