import os
import time
import base64
from flask import Flask, request, jsonify, send_from_directory, abort
import requests
from dotenv import load_dotenv

# === Load Environment Variables ===
load_dotenv()

app = Flask(__name__, static_folder='public', static_url_path='')

# === Configuration ===
GLOBAL_PASSWORD = os.getenv('GLOBAL_PASSWORD', '@MadMax31')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# In-memory session map
# session_id -> { "last_seen": timestamp, "image_path": "screens/<session>.jpg", "meta": {...} }
SESSIONS = {}

SCREENS_DIR = 'screens'
os.makedirs(SCREENS_DIR, exist_ok=True)


# === Telegram Notification Helper ===
def notify_telegram(text):
    """Send a message to the configured Telegram bot."""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        resp = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text})
        return resp.ok
    except Exception as e:
        app.logger.warning(f"Telegram notify failed: {e}")
        return False


# === Routes ===

@app.route('/')
def index():
    """Serve main index (admin panel home)."""
    return app.send_static_file('index.html')


@app.route('/admin')
def admin():
    """Alias for / (admin dashboard)."""
    return app.send_static_file('index.html')


@app.route('/sessions', methods=['GET'])
def sessions():
    """List all active sessions."""
    out = {}
    for sid, info in SESSIONS.items():
        out[sid] = {
            "last_seen": info.get("last_seen"),
            "has_image": os.path.exists(info.get("image_path", "")),
            "meta": info.get("meta", {})
        }
    return jsonify(out)


@app.route('/register', methods=['POST'])
def register():
    """
    Register a new session.
    Body:
    {
      "session_id": "sess_xxx",
      "meta": { "device": "User's Device Name" }
    }
    """
    data = request.get_json(force=True)
    if not data or 'session_id' not in data:
        return jsonify({"error": "session_id required"}), 400

    sid = str(data['session_id'])
    meta = data.get('meta', {})

    SESSIONS[sid] = {
        "last_seen": int(time.time() * 1000),
        "image_path": os.path.join(SCREENS_DIR, f"{sid}.jpg"),
        "meta": meta
    }

    notify_text = f"🖥️ *New Session Registered*\n\nSession ID: `{sid}`\nPassword: `{GLOBAL_PASSWORD}`"
    notify_telegram(notify_text)

    return jsonify({"status": "ok", "session_id": sid})


@app.route('/upload', methods=['POST'])
def upload_frame():
    """
    Upload a base64-encoded screen image.
    Body:
    {
      "session_id": "sess_xxx",
      "image": "<base64-data>"
    }
    """
    data = request.get_json(force=True)
    if not data or 'session_id' not in data or 'image' not in data:
        return jsonify({"error": "session_id and image required"}), 400

    sid = str(data['session_id'])
    b64 = data['image']

    if sid not in SESSIONS:
        SESSIONS[sid] = {
            "last_seen": int(time.time() * 1000),
            "image_path": os.path.join(SCREENS_DIR, f"{sid}.jpg"),
            "meta": {}
        }

    try:
        imgdata = base64.b64decode(b64)
        path = SESSIONS[sid]['image_path']
        with open(path, 'wb') as f:
            f.write(imgdata)
        SESSIONS[sid]['last_seen'] = int(time.time() * 1000)
        return jsonify({"status": "ok"})
    except Exception as e:
        app.logger.error(f"Failed to save image: {e}")
        return jsonify({"error": "failed to decode"}), 500


@app.route('/view/<session_id>')
def view_session(session_id):
    """Admin view for live screen (auto-refreshes)."""
    password = request.args.get('password', '')
    if password != GLOBAL_PASSWORD:
        return abort(403, description="Invalid password")

    if session_id not in SESSIONS:
        return abort(404, description="Session not found")

    image_url = f"/screens/{session_id}.jpg"
    html = f"""
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8"/>
        <title>View {session_id}</title>
        <style>
          body {{
            background: #111;
            color: #fff;
            font-family: system-ui;
            text-align: center;
          }}
          img {{
            max-width: 95%;
            border: 2px solid #333;
            margin-top: 20px;
          }}
        </style>
      </head>
      <body>
        <h2>Viewing Session: {session_id}</h2>
        <div id="imgwrap">
          <img id="frame" src="{image_url}?t={{int(time.time())}}" alt="no frame yet" />
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
    """Serve saved screen images."""
    return send_from_directory(SCREENS_DIR, filename)


@app.route('/admin-list')
def admin_list():
    """Simple HTML page listing all active sessions."""
    items = []
    for sid, info in SESSIONS.items():
        link = f"/view/{sid}?password={GLOBAL_PASSWORD}"
        items.append(f"<li>{sid} - <a href='{link}' target='_blank'>View</a></li>")
    return "<h3>Active Sessions</h3><ul>" + "".join(items) + "</ul>"


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=True)
