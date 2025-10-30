# server.py
import os
import time
import base64
import re
from flask import Flask, request, jsonify, send_from_directory, abort
import requests
import logging

# --- App setup ---
app = Flask(__name__, static_folder='public', static_url_path='')
logging.basicConfig(level=logging.INFO)

# --- Config (use env vars; provide safe defaults for local dev) ---
GLOBAL_PASSWORD = os.environ.get('GLOBAL_PASSWORD', '@MadMax31')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '').strip()

# Upload limits
MAX_IMAGE_BYTES = int(os.environ.get('MAX_IMAGE_BYTES', 5 * 1024 * 1024))  # 5 MB default

# Allowed session id pattern (keep simple & safe)
SESSION_ID_RE = re.compile(r'^[A-Za-z0-9_\-]{3,64}$')

# In-memory sessions map:
# session_id -> { "last_seen": ts, "image_path": "screens/<session>.jpg", "meta": {...} }
SESSIONS = {}

SCREENS_DIR = 'screens'
os.makedirs(SCREENS_DIR, exist_ok=True)


def notify_telegram(text):
    """Send a Telegram notification if credentials are configured."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        app.logger.debug("Telegram not configured; skipping notify")
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        resp = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text})
        if not resp.ok:
            app.logger.warning("Telegram responded with status %s: %s", resp.status_code, resp.text)
        return resp.ok
    except Exception as e:
        app.logger.warning("Telegram notify failed: %s", e)
        return False


@app.route('/')
def index():
    return app.send_static_file('index.html')


@app.route('/admin')
def admin():
    return app.send_static_file('index.html')


@app.route('/sessions', methods=['GET'])
def list_sessions():
    out = {}
    for sid, info in SESSIONS.items():
        out[sid] = {
            "last_seen": info.get("last_seen"),
            "has_image": bool(os.path.exists(info.get("image_path", ""))),
            "meta": info.get("meta", {})
        }
    return jsonify(out)


def safe_session_id(raw):
    """Validate & normalize session id; returns None if invalid."""
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip()
    if SESSION_ID_RE.match(raw):
        return raw
    return None


@app.route('/register', methods=['POST'])
def register():
    data = request.get_json(force=True, silent=True)
    if not data or 'session_id' not in data:
        return jsonify({"error": "session_id required"}), 400

    sid = safe_session_id(str(data['session_id']))
    if not sid:
        return jsonify({"error": "invalid session_id format (allowed: A-Z a-z 0-9 _ -)"}), 400

    meta = data.get('meta', {}) if isinstance(data.get('meta', {}), dict) else {}

    SESSIONS[sid] = {
        "last_seen": int(time.time() * 1000),
        "image_path": os.path.join(SCREENS_DIR, f"{sid}.jpg"),
        "meta": meta
    }

    notify_text = f"🖥️ New session: `{sid}`\nPassword: `{GLOBAL_PASSWORD}`"
    notify_telegram(notify_text)
    app.logger.info("Registered session %s", sid)
    return jsonify({"status": "ok", "session_id": sid})


@app.route('/upload', methods=['POST'])
def upload_frame():
    data = request.get_json(force=True, silent=True)
    if not data or 'session_id' not in data or 'image' not in data:
        return jsonify({"error": "session_id and image required"}), 400

    sid = safe_session_id(str(data['session_id']))
    if not sid:
        return jsonify({"error": "invalid session_id"}), 400

    b64 = data['image']
    if not isinstance(b64, str):
        return jsonify({"error": "image must be base64 string"}), 400

    # Quick size check on base64 length -> approximate bytes
    approx_bytes = (len(b64) * 3) // 4
    if approx_bytes > MAX_IMAGE_BYTES:
        return jsonify({"error": "image too large"}), 413

    if sid not in SESSIONS:
        SESSIONS[sid] = {
            "last_seen": int(time.time() * 1000),
            "image_path": os.path.join(SCREENS_DIR, f"{sid}.jpg"),
            "meta": {}
        }

    try:
        imgdata = base64.b64decode(b64, validate=True)
    except Exception as e:
        app.logger.warning("Bad base64 for session %s: %s", sid, e)
        return jsonify({"error": "failed to decode base64"}), 400

    if len(imgdata) > MAX_IMAGE_BYTES:
        return jsonify({"error": "decoded image too large"}), 413

    path = SESSIONS[sid]['image_path']
    try:
        with open(path, 'wb') as f:
            f.write(imgdata)
        SESSIONS[sid]['last_seen'] = int(time.time() * 1000)
        app.logger.debug("Saved image for %s (%d bytes)", sid, len(imgdata))
        return jsonify({"status": "ok"})
    except Exception as e:
        app.logger.error("Failed to save image for %s: %s", sid, e)
        return jsonify({"error": "failed to save image"}), 500


@app.route('/view/<session_id>')
def view_session(session_id):
    password = request.args.get('password', '')
    if password != GLOBAL_PASSWORD:
        return abort(403, description="Invalid password")

    sid = safe_session_id(session_id)
    if not sid or sid not in SESSIONS:
        return abort(404, description="Session not found")

    image_url = f"/screens/{sid}.jpg"
    html = f"""
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8"/>
        <title>View {sid}</title>
        <style>body{{background:#111;color:#fff;font-family:system-ui;text-align:center}} img{{max-width:95%;border:1px solid #333}}</style>
      </head>
      <body>
        <h2>Viewing: {sid}</h2>
        <div id="imgwrap">
          <img id="frame" src="{image_url}?t={{timestamp}}" alt="no frame yet" />
        </div>
        <script>
          function reload() {{
            var img = document.getElementById('frame');
            img.src = '{image_url}?t=' + Date.now();
          }}
          setInterval(reload, 1000);
        </script>
      </body>
    </html>
    """
    return html


@app.route('/screens/<path:filename>')
def serve_screens(filename):
    # only serve safe filenames (no ..)
    safe_name = os.path.basename(filename)
    return send_from_directory(SCREENS_DIR, safe_name)


@app.route('/admin-list')
def admin_list():
    items = []
    for sid in SESSIONS.keys():
        items.append(f"<li>{sid} - <a href='/view/{sid}?password={GLOBAL_PASSWORD}' target='_blank'>View</a></li>")
    return "<h3>Active Sessions</h3><ul>" + "".join(items) + "</ul>"


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)), debug=True)
