#!/usr/bin/env python3
"""
Klayines - P2P Messenger APK
"""
import hashlib
import socket
import json
import time
import threading
import os
import random
import requests

# Для Android WebView
try:
    from android.webview import WebView
    from android.runnable import run_on_ui_thread
    ON_ANDROID = True
except ImportError:
    ON_ANDROID = False

SERVER_URL = "https://p2p-epg6.onrender.com"

# Сохраняем ID на SD-карту
try:
    CONFIG_FILE = "/sdcard/klayines_id.json"
except:
    CONFIG_FILE = "klayines_id.json"

my_id = None
messages_list = []

HTML = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Klayines</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { background: #000; color: #0f0; font-family: monospace; height: 100vh; display: flex; flex-direction: column; }
        #header { background: #111; padding: 15px; text-align: center; border-bottom: 2px solid #0f0; }
        #header h2 { color: #0ff; font-size: 20px; }
        #id-text { color: #0f0; font-size: 12px; margin-top: 5px; }
        #chat { flex: 1; overflow-y: auto; padding: 10px; }
        .msg { margin: 8px 0; padding: 8px; border-radius: 5px; }
        .msg-in { background: #1a1a00; color: #ff0; border-left: 3px solid #ff0; }
        .msg-out { background: #001a1a; color: #0ff; border-left: 3px solid #0ff; }
        .time { color: #666; font-size: 10px; }
        #input-area { background: #111; padding: 10px; border-top: 2px solid #0f0; }
        input { width: 100%; padding: 12px; margin: 5px 0; background: #222; border: 1px solid #0f0; color: #0f0; font-size: 16px; border-radius: 5px; }
        button { width: 100%; padding: 14px; margin: 5px 0; border: none; font-size: 16px; font-weight: bold; border-radius: 5px; cursor: pointer; }
        .btn-send { background: #0f0; color: #000; }
        .btn-online { background: #44f; color: #fff; }
        button:active { opacity: 0.7; }
    </style>
</head>
<body>
    <div id="header">
        <h2>⚡ KLAYINES</h2>
        <div id="id-text">ID: LOADING...</div>
    </div>
    <div id="chat"></div>
    <div id="input-area">
        <input type="text" id="target" placeholder="Target ID">
        <input type="text" id="message" placeholder="Message...">
        <button class="btn-send" onclick="send()">[ SEND ]</button>
        <button class="btn-online" onclick="online()">[ ONLINE USERS ]</button>
    </div>
    <script>
        const SERVER = 'SERVER_URL_PLACEHOLDER';
        let myId = localStorage.getItem('klayines_id');
        
        if (!myId) {
            fetch('MY_ID_PLACEHOLDER')
                .then(r => r.text())
                .then(id => {
                    myId = id;
                    localStorage.setItem('klayines_id', id);
                    document.getElementById('id-text').textContent = 'ID: ' + id;
                });
        } else {
            document.getElementById('id-text').textContent = 'ID: ' + myId;
        }
        
        function send() {
            const target = document.getElementById('target').value.trim();
            const text = document.getElementById('message').value.trim();
            if (!target || !text) return;
            
            fetch(SERVER + '/send', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({from: myId, to: target, text: text})
            })
            .then(r => r.json())
            .then(d => {
                if (d.status === 'sent') {
                    document.getElementById('message').value = '';
                    addMsg('You', text, 'out');
                } else {
                    alert(d.error || 'Error');
                }
            })
            .catch(() => alert('Network error'));
        }
        
        function online() {
            fetch(SERVER + '/online')
                .then(r => r.json())
                .then(d => alert('Online (' + d.length + '):\n' + (d.join('\n') || 'none')))
                .catch(() => alert('Server unreachable'));
        }
        
        function addMsg(sender, text, type) {
            const chat = document.getElementById('chat');
            const time = new Date().toLocaleTimeString();
            chat.innerHTML += 
                '<div class="msg msg-' + type + '">' +
                '<span class="time">' + time + '</span><br>' +
                '<b>' + sender + '</b>: ' + text +
                '</div>';
            chat.scrollTop = chat.scrollHeight;
        }
        
        function check() {
            fetch(SERVER + '/check', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({id: myId})
            })
            .then(r => r.json())
            .then(d => {
                (d.messages || []).forEach(m => addMsg(m.from, m.text, 'in'));
            });
        }
        
        // Пинг
        setInterval(() => {
            fetch(SERVER + '/ping', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({id: myId})
            });
        }, 30000);
        
        setInterval(check, 2000);
        check();
    </script>
</body>
</html>
'''

def gen_id():
    hostname = socket.gethostname()
    unique = f"{hostname}_{random.randint(10000, 99999)}_{time.time()}"
    return hashlib.sha256(unique.encode()).hexdigest()[:8]

def load_id():
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)["id"]
    except:
        new_id = gen_id()
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump({"id": new_id}, f)
        except:
            pass
        return new_id

if __name__ == '__main__':
    my_id = load_id()
    
    # Заменяем URL в HTML
    html_content = HTML.replace('SERVER_URL_PLACEHOLDER', SERVER_URL)
    html_content = html_content.replace('MY_ID_PLACEHOLDER', my_id)
    
    if ON_ANDROID:
        # Запускаем в Android WebView
        @run_on_ui_thread
        def show_webview():
            webview = WebView()
            webview.load_html(html_content)
            webview.show()
        
        show_webview()
    else:
        # Для тестов на ПК — сохраняем HTML
        with open('klayines.html', 'w') as f:
            f.write(html_content)
        print(f"HTML saved to klayines.html")
        print(f"Your ID: {my_id}")
        print(f"Open in browser or serve with: python -m http.server")
