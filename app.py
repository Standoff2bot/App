import os, sys, time, threading, hashlib, socket, random, json, subprocess
import requests
import toga
from toga.style import Pack
from toga.style.pack import COLUMN
from flask import Flask, render_template_string, request, jsonify

# ---------- НАСТРОЙКИ ----------
SERVER_URL = "https://p2p-epg6.onrender.com"
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "klayines_id.json")
BRIDGES_FILE = os.path.expanduser("~/.klayines_bridges.txt")
TORRC_FILE   = os.path.expanduser("~/.klayines_torrc")
HS_DIR       = os.path.expanduser("~/.klayines_hidden_service")
# -------------------------------

# ==================== Tor Bridges Mode ====================
def load_bridges():
    default = [
        "obfs4 192.95.36.142:443 CDF2E852BF539B82BD10E27E9115A31734E378C2 cert=qUVQ0srL1JI/vO6V6m/24anYXiJD3QP2HgzUKQtQ7GRqqUvs7P+tG43RtAqdhLOALP7zaQ iat-mode=1",
        "obfs4 37.218.245.14:38224 D9A82D2F9C2F65A18407B1D2B764F130847F8B5D cert=3NRs8/khPGDolhbjj448EDxwne4O3uQcu8sD6ar2BWkVR2FkbgfAQufy82jDCCNsnCLpZQ iat-mode=0",
    ]
    if os.path.exists(BRIDGES_FILE):
        with open(BRIDGES_FILE) as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
            if lines:
                return lines
    return default

def wait_tor_bootstrap(timeout=200):
    for i in range(timeout):
        try:
            s = socket.socket(); s.settimeout(1)
            if s.connect_ex(('127.0.0.1',9050))==0:
                ctrl = socket.socket(); ctrl.settimeout(2)
                ctrl.connect(('127.0.0.1',9051))
                ctrl.send(b'AUTHENTICATE\r\n'); ctrl.recv(1024)
                ctrl.send(b'GETINFO status/bootstrap-phase\r\n')
                r = ctrl.recv(1024).decode(); ctrl.close()
                if 'PROGRESS=100' in r or 'TAG=done' in r:
                    return True
            s.close()
        except: pass
        time.sleep(1)
    return False

class TorP2P:
    def __init__(self, onion):
        self.onion = onion
        self.msgs = []
        self.lock = threading.Lock()
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(('127.0.0.1', 9878))
        self.srv.listen(5)
        threading.Thread(target=self._accept, daemon=True).start()
    def _accept(self):
        while True:
            try:
                c,_ = self.srv.accept()
                threading.Thread(target=self._handle, args=(c,), daemon=True).start()
            except: break
    def _handle(self, c):
        try:
            data = c.recv(8192)
            if data:
                m = json.loads(data.decode())
                with self.lock:
                    self.msgs.append(m)
        except: pass
        finally: c.close()
    def send(self, onion, text, nick=""):
        try:
            import socks
            m = json.dumps({"from":nick or "anon","text":text,"time":time.strftime("%H:%M:%S")})
            s = socks.socksocket()
            s.set_proxy(socks.SOCKS5, "127.0.0.1", 9050)
            s.settimeout(15)
            s.connect((onion, 9878))
            s.send(m.encode())
            s.close()
            return True
        except: return False

class TorBridgesMode:
    def __init__(self):
        self.onion = None
        self.net = None
        if not self._start_tor(): raise RuntimeError("Tor failed")
        self._wait_hidden_service()
        if self.onion:
            self.net = TorP2P(self.onion)
    def _start_tor(self):
        os.makedirs(HS_DIR, exist_ok=True)
        bridges = load_bridges()
        torrc = f"SocksPort 9050\nControlPort 9051\nUseBridges 1\nClientTransportPlugin obfs4 exec /data/data/com.termux/files/usr/bin/obfs4proxy\n"
        torrc += "\n".join([f"Bridge {b}" for b in bridges])
        torrc += f"\nHiddenServiceDir {HS_DIR}\nHiddenServicePort 9878 127.0.0.1:9878"
        with open(TORRC_FILE, 'w') as f: f.write(torrc)
        try:
            self.tor = subprocess.Popen(["tor", "-f", TORRC_FILE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except: return False
        return wait_tor_bootstrap()
    def _wait_hidden_service(self):
        for _ in range(30):
            hf = os.path.join(HS_DIR, "hostname")
            if os.path.exists(hf):
                with open(hf) as f:
                    addr = f.read().strip()
                    if addr.endswith(".onion"):
                        self.onion = addr
                        return
            time.sleep(1)
    def check(self):
        if self.net:
            with self.net.lock:
                m = self.net.msgs[:]; self.net.msgs.clear()
            return m
        return []
    def send(self, _, target, text, nick=""):
        if self.net:
            return (True, None) if self.net.send(target, text, nick) else (False, "fail")
        return (False, "offline")

# ==================== Flask Web App ====================
flask_app = Flask(__name__)
my_id = None
nickname = ""
active_mode = None
chat = []

HTML = r"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Klayines</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#000;color:#0f0;font-family:monospace;height:100vh;display:flex;flex-direction:column}
#head{background:#111;padding:10px;text-align:center;border-bottom:2px solid #0f0}
#chat{flex:1;overflow-y:auto;padding:10px}
.msg{margin:8px 0;padding:5px;border-left:3px solid #0f0}
#input{background:#111;padding:10px;border-top:2px solid #0f0}
input,button{width:100%;padding:12px;margin:5px 0;background:#222;border:1px solid #0f0;color:#0f0;font-family:monospace;font-size:16px;border-radius:5px}
button{background:#030;cursor:pointer} button:active{opacity:.7}
</style></head>
<body>
<div id="head"><h2>⚡ KLAYINES</h2><p id="id">ID: loading...</p></div>
<div id="chat"></div>
<div id="input">
<input id="target" placeholder="Target ID / .onion">
<input id="text" placeholder="Message...">
<button onclick="send()">[SEND]</button>
</div>
<script>
let myId=localStorage.getItem('klayines_id')||'';
if(!myId){fetch('/myid').then(r=>r.text()).then(id=>{myId=id;localStorage.setItem('klayines_id',id);document.getElementById('id').textContent='ID: '+id})}
else document.getElementById('id').textContent='ID: '+myId;
function send(){
 const t=document.getElementById('target').value.trim();
 const m=document.getElementById('text').value.trim();
 if(!t||!m)return;
 fetch('/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({target:t,text:m})})
 .then(r=>r.json()).then(d=>{if(d.ok){document.getElementById('text').value='';load()}})
}
function load(){
 fetch('/messages').then(r=>r.json()).then(d=>{
  const c=document.getElementById('chat');
  c.innerHTML=d.map(m=>'<div class="msg"><b>'+m.from+'</b>: '+m.text+'</div>').join('');
  c.scrollTop=c.scrollHeight
 })
}
setInterval(load,2000);load()
</script>
</body></html>"""

@flask_app.route('/')
def index():
    return render_template_string(HTML)

@flask_app.route('/myid')
def myid():
    return my_id or "???"

@flask_app.route('/messages')
def messages():
    if active_mode:
        for m in active_mode.check():
            chat.append(m)
    return jsonify(chat[-50:])

@flask_app.route('/send', methods=['POST'])
def send():
    data = request.json
    target = data.get('target','').strip()
    text = data.get('text','').strip()
    if not target or not text:
        return jsonify({"ok":False})
    ok, _ = active_mode.send(my_id, target, text, nick=nickname)
    if ok:
        chat.append({"from":"You","text":text})
    return jsonify({"ok":ok})

def load_or_create_id():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f).get("id", "")
    hostname = socket.gethostname()
    unique = f"{hostname}_{random.randint(10000,99999)}_{time.time()}"
    new_id = hashlib.sha256(unique.encode()).hexdigest()[:8]
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump({"id":new_id}, f)
    return new_id

# ==================== Toga App (WebView) ====================
class KlayinesApp(toga.App):
    def startup(self):
        self.webview = toga.WebView(
            url='http://localhost:5000',
            style=Pack(flex=1)
        )
        self.main_window = toga.MainWindow(title="Klayines")
        self.main_window.content = self.webview
        self.main_window.show()

def start_flask():
    global my_id, active_mode
    my_id = load_or_create_id()
    try:
        active_mode = TorBridgesMode()
        print(f"Onion: {active_mode.onion}")
    except Exception as e:
        print(f"Tor error: {e}")
        sys.exit(1)
    flask_app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

def main():
    # Запускаем Flask в фоне
    threading.Thread(target=start_flask, daemon=True).start()
    time.sleep(2)
    # Запускаем Toga интерфейс (WebView)
    app = KlayinesApp('Klayines', 'com.klayines')
    return app.main_loop()
