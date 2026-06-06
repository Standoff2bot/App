#!/usr/bin/env python3
"""
Klayines - P2P Messenger (WebView версия)
"""
import hashlib
import socket
import json
import time
import threading
import os
import random
import requests
from flask import Flask, render_template_string, request, jsonify

SERVER_URL = "https://p2p-epg6.onrender.com"
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "klayines_config.json")

app = Flask(__name__)
my_id = None
nickname = ""
messages_list = []

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Klayines</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: #0a0a0a;
            color: #00ff00;
            font-family: monospace;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        #header {
            background: #111;
            padding: 10px;
            text-align: center;
            border-bottom: 2px solid #00ff00;
        }
        #id-text { color: #00ffff; font-size: 12px; }
        #chat {
            flex: 1;
            overflow-y: auto;
            padding: 10px;
            background: #000;
        }
        .msg-in { color: #ffff00; margin: 5px 0; }
        .msg-out { color: #00ffff; margin: 5px 0; }
        .msg-time { color: #666; font-size: 10px; }
        #input-area {
            background: #111;
            padding: 10px;
            border-top: 2px solid #00ff00;
        }
        input {
            width: 100%;
            padding: 10px;
            margin: 5px 0;
            background: #222;
            border: 1px solid #00ff00;
            color: #00ff00;
            font-family: monospace;
            font-size: 14px;
        }
        button {
            width: 100%;
            padding: 12px;
            background: #003300;
            border: 2px solid #00ff00;
            color: #00ff00;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            margin: 3px 0;
        }
        button:active { background: #005500; }
        #users-btn { background: #1a1a3a; border-color: #4444ff; color: #8888ff; }
    </style>
</head>
<body>
    <div id="header">
        <h2>⚡ KLAYINES v1.0</h2>
        <p id="id-text">ID: {{ my_id }}</p>
    </div>
    
    <div id="chat">
        {% for msg in messages %}
            <div class="{{ 'msg-out' if msg.type == 'out' else 'msg-in' }}">
                <span class="msg-time">{{ msg.time }}</span>
                <b>{{ msg.sender }}</b>: {{ msg.text }}
            </div>
        {% endfor %}
    </div>
    
    <div id="input-area">
        <input type="text" id="target" placeholder="Target ID">
        <input type="text" id="message" placeholder="Message...">
        <button onclick="sendMessage()">[ SEND ]</button>
        <button id="users-btn" onclick="showOnline()">[ ONLINE USERS ]</button>
    </div>
    
    <script>
        function sendMessage() {
            const target = document.getElementById('target').value.trim();
            const text = document.getElementById('message').value.trim();
            if (!target || !text) return;
            
            fetch('/send', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({target: target, text: text})
            })
            .then(r => r.json())
            .then(data => {
                if (data.status === 'ok') {
                    document.getElementById('message').value = '';
                    loadMessages();
                } else {
                    alert('Error: ' + data.error);
                }
            });
        }
        
        function showOnline() {
            fetch('/online')
                .then(r => r.json())
                .then(data => {
                    const users = data.users || [];
                    alert('Online (' + users.length + '):\\n' + users.join('\\n'));
                });
        }
        
        function loadMessages() {
            fetch('/messages')
                .then(r => r.json())
                .then(data => {
                    const chat = document.getElementById('chat');
                    chat.innerHTML = data.messages.map(msg => 
                        '<div class="' + (msg.type === 'out' ? 'msg-out' : 'msg-in') + '">' +
                        '<span class="msg-time">' + msg.time + '</span> ' +
                        '<b>' + msg.sender + '</b>: ' + msg.text +
                        '</div>'
                    ).join('');
                    chat.scrollTop = chat.scrollHeight;
                });
        }
        
        // Обновление каждые 2 секунды
        setInterval(loadMessages, 2000);
        loadMessages();
    </script>
</body>
</html>
'''

def generate_id():
    hostname = socket.gethostname()
    unique = f"{hostname}_{random.randint(10000, 99999)}_{time.time()}"
    return hashlib.sha256(unique.encode()).hexdigest()[:8]

def load_or_create_id():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
            return config.get("id", generate_id())
    new_id = generate_id()
    with open(CONFIG_FILE, "w") as f:
        json.dump({"id": new_id}, f)
    return new_id

def ping_loop():
    while True:
        try:
            requests.post(f"{SERVER_URL}/ping", json={"id": my_id}, timeout=10)
        except:
            pass
        time.sleep(30)

def check_loop():
    while True:
        try:
            resp = requests.post(f"{SERVER_URL}/check", json={"id": my_id}, timeout=5)
            if resp.status_code == 200:
                for msg in resp.json().get("messages", []):
                    sender = msg.get("from_nick", msg.get("from"))
                    text = msg.get("text")
                    tm = msg.get("time", "")
                    messages_list.append({
                        "type": "in",
                        "sender": sender,
                        "text": text,
                        "time": tm
                    })
        except:
            pass
        time.sleep(2)

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, my_id=my_id, messages=messages_list[-20:])

@app.route('/messages')
def get_messages():
    return jsonify({"messages": messages_list[-50:]})

@app.route('/send', methods=['POST'])
def send():
    data = request.json
    target = data.get('target')
    text = data.get('text')
    
    if not target or not text:
        return jsonify({"status": "error", "error": "Missing fields"})
    
    try:
        resp = requests.post(
            f"{SERVER_URL}/send",
            json={"from": my_id, "to": target, "text": text},
            timeout=10
        )
        if resp.status_code == 200:
            messages_list.append({
                "type": "out",
                "sender": "Me",
                "text": text,
                "time": time.strftime("%H:%M:%S")
            })
            return jsonify({"status": "ok"})
        return jsonify({"status": "error", "error": resp.json().get("error", "Failed")})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)})

@app.route('/online')
def online():
    try:
        resp = requests.get(f"{SERVER_URL}/online", timeout=10)
        if resp.status_code == 200:
            return jsonify({"users": resp.json()})
    except:
        pass
    return jsonify({"users": []})

if __name__ == '__main__':
    my_id = load_or_create_id()
    
    threading.Thread(target=ping_loop, daemon=True).start()
    threading.Thread(target=check_loop, daemon=True).start()
    
    print(f"Klayines running on http://localhost:5000")
    print(f"Your ID: {my_id}")
    app.run(host='0.0.0.0', port=5000, debug=False)
