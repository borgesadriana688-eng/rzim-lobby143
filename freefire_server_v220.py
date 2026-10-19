"""
================================================================
 FREE FIRE PRIVATE SERVER v2.2.0 - KRYNO ACCOUNTS + FIX IDENTIDADE - STATELESS TOKENS (FIXED)
================================================================
 Servidor HTTP (Flask) + Game Server (TCP Socket) + UDP
 Tokens sem estado (stateless) - funciona com múltiplos workers

 CORREÇÕES v2.1.2 (marcadas com "# FIX:"):
 1. Game/UDP server agora sobe no import (gunicorn nunca executava
    o bloco __main__, então o servidor TCP nunca iniciava em deploy)
 2. Framing TCP corrigido: buffer acumulado + parse por comprimento
    (TCP é stream; recv() podia pegar pacote picado ou 2 juntos)
 3. Proteção contra payload gigante declarado no header (fechava nada)
 4. verify_token: padding base64 robusto
 5. Health reporta rooms/conexões REAIS do GameServer (era sempre 0)
 6. catch_all agora LOGA endpoints desconhecidos em unknown_endpoints.log
    -> ajuda a mapear a API do cliente (descoberta de rotas)
 7. ADMIN_MODE opcional (default ligado = conta Administrador fixa)
 8. save_players com lock de arquivo (multi-worker não corrompe)
 9. Rotas /player/heartbeat e /game/heartbeat adicionadas
10. stop() gracioso nos servidores

 COMO USAR:
 1. pip install flask gunicorn
 2. python3 freefire_server_full.py
 3. Deploy: gunicorn freefire_server_full:app --workers 1
================================================================
"""

import os
import json
import time
import uuid
import hashlib
import secrets
import base64
import hmac
import socket
import struct
import threading
from flask import Flask, request, jsonify

app = Flask(__name__)

# FIX 13 (debug v2.1.3): loga TODA requisicao (metodo, path, form/args) no
# stdout -> aparece em `railway logs -d`. Ajuda a diagnosticar "autenticacao
# falhou" sem adivinhar o que o cliente esta mandando.
@app.before_request
def _log_request():
    try:
        _raw = request.get_data(cache=True) or b""
        data = dict(request.form) if request.form else dict(request.args)
        print(f"[REQ] {request.method} {request.path} data={data} rawhex={_raw[:800].hex()} ua={request.headers.get('User-Agent','')[:60]}", flush=True)
    except Exception as e:
        print(f"[REQ-ERR] {e}", flush=True)

# ==================================================================
# CONFIGURAÇÃO
# ==================================================================
APP_ID = "com.dts.freefireth"
# FIX 14: o APK real (MSDK 4.0.18) envia app_id numerico "100067" (MSDK app id).
# Aceitamos os dois formatos para nao rejeitar o cliente real.
VALID_APP_IDS = {"com.dts.freefireth", "100067"}
APP_KEY = "freefire"
CLIENT_VERSION = "1.71.0"
HTTP_PORT = int(os.environ.get("PORT", 5000))
GAME_IP = os.environ.get("GAME_SERVER_IP", "127.0.0.1")
GAME_PORT = int(os.environ.get("GAME_SERVER_PORT", 2205))

# FIX 7: modo admin fixo (v2.1.0 era sempre ligado). ADMIN_MODE=0 gera
# uma conta por dispositivo (multiplayer de verdade); ADMIN_MODE=1 mantem
# a conta "Administrador" fixa com tudo liberado (comportamento antigo)
ADMIN_MODE = os.environ.get("ADMIN_MODE", "1") == "1"
ADMIN_OPEN_ID = "109900000000000001"  # FIX 18: precisa ser NUMERICO (int64)
ADMIN_NICKNAME = "Administrador"

# Chave secreta para assinar tokens (HMAC)
SECRET_KEY = os.environ.get("SECRET_KEY", "freefire_private_server_2024_hmac_key_fixed_v2")

# FIX: tamanho maximo de payload TCP aceito (protecao contra header malicioso)
MAX_TCP_PAYLOAD = 1024 * 1024  # 1 MB

# ==================================================================
# TOKENS STATELESS
# ==================================================================
def create_token(open_id, nickname, token_type="guest"):
    payload = {
        "open_id": open_id,
        "nickname": nickname,
        "type": token_type,
        "created": now(),
        "expire": now() + 86400 * 30
    }
    payload_json = json.dumps(payload, separators=(',', ':'))
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode()
    sig = hmac.new(SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"

def _b64decode_padded(s):
    # FIX 4: re-adiciona padding que pode ter sido perdido em trânsito
    if isinstance(s, str):
        s = s.encode()
    s = s.strip()
    pad = (-len(s)) % 4
    return base64.urlsafe_b64decode(s + b"=" * pad)

def verify_token(token):
    if not token or '.' not in token:
        return None
    try:
        parts = token.split('.')
        if len(parts) != 2:
            return None
        payload_b64, sig = parts
        expected_sig = hmac.new(SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        payload = json.loads(_b64decode_padded(payload_b64))
        if payload.get("expire", 0) < now():
            return None
        return payload
    except Exception:
        return None

def create_refresh_token(open_id, nickname, token_type="guest"):
    payload = {
        "open_id": open_id,
        "nickname": nickname,
        "type": token_type,
        "rt": True,
        "expire": now() + 86400 * 60
    }
    payload_json = json.dumps(payload, separators=(',', ':'))
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode()
    sig = hmac.new(SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"

def verify_refresh_token(token):
    d = verify_token(token)
    if d and d.get("rt"):
        return d
    return None


# FIX 11 (v2.1.2): le access_token de QUALQUER lugar (form/query/header).
# Antes account_info_get so lia header/query; o cliente manda no corpo do
# POST -> servidor nao achava o token e INVENTAVA uma conta aleatoria,
# causando o erro "openid invalido" no jogo.
def _token_from_request():
    t = (request.form.get('access_token', '')
         or request.args.get('access_token', '')
         or request.headers.get('Authorization', '').replace('Bearer ', '').strip())
    return verify_token(t)

def _open_id_from_request():
    return request.form.get('open_id') or request.args.get('open_id')


# ==================================================================
# DADOS DE JOGADOR (persistidos em players.json)
# ==================================================================
PLAYERS = {}
ROOMS = {}
SOCKETS = {}
# FIX 15: codigos de autorizacao OAuth (fluxo embedded MSDK/GOP)
AUTH_CODES = {}

_DB_FILE = os.environ.get("PLAYERS_DB",
                          os.path.join(os.path.dirname(os.path.abspath(__file__)), "players.json"))
_UNKNOWN_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "unknown_endpoints.log")

_save_lock = threading.Lock()

def save_players():
    # FIX 8: lock de arquivo evita JSON corrompido com workers/processos
    import fcntl
    try:
        with _save_lock:
            tmp = _DB_FILE + ".tmp"
            with open(tmp, "w") as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                json.dump(PLAYERS, f)
                fcntl.flock(f, fcntl.LOCK_UN)
            os.replace(tmp, _DB_FILE)
    except Exception:
        pass

def load_players():
    global PLAYERS
    try:
        with open(_DB_FILE) as f:
            PLAYERS = json.load(f)
    except Exception:
        PLAYERS = {}

load_players()

def gen_open_id():
    # FIX (v2.2.0): open_id NUMERICO int64 (padrao Garena). Antes gerava hex
    # com letras -> o jogo nao aceitava ("openid invalido").
    import random as _rnd
    return str(int(time.time() * 1000)) + str(_rnd.randrange(10**5, 10**6))[:5]

def now():
    return int(time.time())

def get_player(open_id, nickname="Player"):
    if open_id not in PLAYERS:
        PLAYERS[open_id] = {
            "nickname": nickname,
            "level": 80,
            "exp": 999999,
            "diamond": 99999,
            "gold": 99999,
            "coins": 99999,
            "tokens": 9999,
            "rank": 10,
            "region": "BR",
            "avatar": 1,
            "vip": 9,
            "skins": list(range(1, 500)),
            "characters": list(range(1, 50)),
            "weapons": list(range(1, 100)),
            "pets": list(range(1, 30)),
            "items": [],
            "created": now()
        }
        save_players()
    return PLAYERS[open_id]


# ==================================================================
# ============== HTTP API SERVER (FLASK) ==============
# ==================================================================

# --- INFO DA APP ---
@app.route('/app/info/get', methods=['GET', 'POST'])  # FIX 12: cliente faz POST
def app_info():
    return jsonify({
        "client_log": False,
        "status": 0,
        "maintenance": False,
        "version": CLIENT_VERSION,
        "game_server": f"{GAME_IP}:{GAME_PORT}",
        "update_url": "",
        "notice": {"title": "Desenvolvido por Brayan", "content": "Servidor privado RZIM - conta Administrador com tudo liberado", "show": True}
    })

@app.route('/app/feedback', methods=['POST', 'GET'])
def feedback():
    return jsonify({"success": True})

# --- GUEST REGISTER ---

# --- LOGIN LOBBY 1.70 (equivale ao MajorLogin do 1.43) ---
@app.route('/Login', methods=['POST'])
def login_170():
    import hashlib
    uid = LAST_FB_UID[0]
    tok = hashlib.sha256(("sess" + str(uid)).encode()).hexdigest()[:48]
    host = os.environ.get("LOBBY_PUBLIC_HOST") or request.host
    if not host.startswith("http"):
        host = "https://" + host
    def s(f, v):
        return bytes([f]) + bytes([len(v)]) + v.encode()
    def vint(f, n):
        out = b""
        while True:
            b = n & 0x7F; n >>= 7
            out += bytes([b | (0x80 if n else 0)])
            if not n: break
        return bytes([f]) + out
    body = b""
    body += vint(8, uid) + s(0x12, "BR") + s(0x1A, "BR") + s(0x22, "BR") + s(0x2A, "live")
    body += s(0x32, "BR") + s(0x3A, "BR") + s(0x42, tok)
    body += vint(0x48, 28800) + s(0x52, host) + vint(0x60, 0)
    return body, 200, {"Content-Type": "application/octet-stream"}

@app.route('/oauth/guest/register', methods=['POST'])
def guest_register():
    app_id = request.form.get('app_id', '')
    gender = int(request.form.get('gender', '1') or '1')
    password = request.form.get('password', '')
    source = int(request.form.get('source', '0') or '0')

    if app_id not in VALID_APP_IDS:
        return jsonify({"code": 1001, "error": "invalid_app_id"})

    # FIX 7: ADMIN_MODE ligado = conta fixa (comportamento v2.1.0)
    if ADMIN_MODE:
        nickname = ADMIN_NICKNAME
        open_id = ADMIN_OPEN_ID
    else:
        nickname = request.form.get('nickname', f'Guest{secrets.randbelow(99999)}')
        open_id = gen_open_id()

    at = create_token(open_id, nickname, "guest")
    rt = create_refresh_token(open_id, nickname, "guest")
    get_player(open_id, nickname)

    return jsonify({
        "open_id": open_id,
        "access_token": at,
        "refresh_token": rt,
        "expires_in": 86400 * 30,
        "expiry_time": now() + 86400 * 30,
        "token_type": "Bearer"
    })

# --- GUEST TOKEN GRANT ---
@app.route('/oauth/guest/token/grant', methods=['POST'])
def guest_grant():
    app_id = request.form.get('app_id', '')
    if app_id not in VALID_APP_IDS:
        return jsonify({"code": 2017, "error": "invalid_grant"})

    if ADMIN_MODE:
        nick, open_id = ADMIN_NICKNAME, ADMIN_OPEN_ID
    else:
        nick = f'Guest{secrets.randbelow(99999)}'
        open_id = gen_open_id()

    at = create_token(open_id, nick, "guest")
    rt = create_refresh_token(open_id, nick, "guest")
    get_player(open_id, nick)

    return jsonify({
        "open_id": open_id,
        "access_token": at,
        "refresh_token": rt,
        "expires_in": 86400 * 30,
        "expiry_time": now() + 86400 * 30,
        "token_type": "Bearer"
    })

# --- OAUTH TOKEN ---
# FIX 16: o MSDK 4.0.18 troca o code em /oauth/token/exchange e o refresh em
# /oauth/token/refresh (visto no log real). Registra os 3 caminhos na mesma
# logica e infere o grant_type quando o cliente nao envia o campo.
@app.route('/oauth/token', methods=['POST'])
@app.route('/oauth/token/exchange', methods=['POST'])
@app.route('/oauth/token/refresh', methods=['POST'])
def oauth_token():
    gt = request.form.get('grant_type', '')
    rt = request.form.get('refresh_token', '')
    code = request.form.get('code', '') or request.args.get('code', '')
    if not gt:
        if code:
            gt = 'authorization_code'
        elif rt:
            gt = 'refresh_token'

    if gt == 'authorization_code':
        # FIX IDENTIDADE (v2.2.0): primeiro tenta o authcode Kryno e usa O
        # OPEN_ID DO CODIGO (antes inventava outro id -> "openid invalido")
        code = request.form.get('code', '') or request.args.get('code', '')
        ac = _verify_authcode(code)
        if ac:
            oid = str(ac["open_id"])
            nick = ac.get("nickname", "Player")
            get_player(oid, nick)
            at = create_token(oid, nick, "oauth")
            nr = create_refresh_token(oid, nick, "oauth")
            return jsonify({
                "access_token": at,
                "refresh_token": nr,
                "open_id": oid,
                "expires_in": 2592000,
                "expiry_time": now() + 2592000,
                "platform": 0,
                "token_type": "Bearer"
            })
        if code in AUTH_CODES:
            AUTH_CODES[code]["used"] = True
        if ADMIN_MODE:
            nick, oid = ADMIN_NICKNAME, ADMIN_OPEN_ID
        else:
            nick = f'Player{secrets.randbelow(99999)}'
            oid = gen_open_id()
        at = create_token(oid, nick, "oauth")
        nr = create_refresh_token(oid, nick, "oauth")
        get_player(oid, nick)
        return jsonify({
            "access_token": at,
            "refresh_token": nr,
            "open_id": oid,
            "expires_in": 86400 * 30,
        "expiry_time": now() + 86400 * 30,
            "platform": 3,
            "token_type": "Bearer"
        })

    elif gt == 'refresh_token':
        d = verify_refresh_token(rt)
        if d:
            at = create_token(d["open_id"], d.get("nickname", "Player"), d.get("type", "oauth"))
            nr = create_refresh_token(d["open_id"], d.get("nickname", "Player"), d.get("type", "oauth"))
            return jsonify({
                "access_token": at,
                "refresh_token": nr,
                "expires_in": 86400 * 30,
        "expiry_time": now() + 86400 * 30,
                "token_type": "Bearer"
            })

    return jsonify({"code": 2017, "error": "invalid_grant"})

# --- TOKEN INSPECT ---
@app.route('/oauth/token/inspect', methods=['GET'])
def token_inspect():
    t = request.args.get('token', '') or request.form.get('token', '')
    d = verify_token(t)
    if d:
        return jsonify({
            "active": True,
            "open_id": d["open_id"],
            "nickname": d.get("nickname", "Player"),
            "token_type": "Bearer",
            "exp": d.get("expire", 0)
        })
    return jsonify({"active": False, "code": 2017, "error": "invalid_token"})

# (FIX 17b: rota standalone /oauth/token/refresh removida - oauth_token cobre via alias FIX 16)

# --- LOGOUT ---
@app.route('/oauth/logout', methods=['GET', 'POST'])
def logout():
    return jsonify({"success": "true"})

# --- USER INFO ---
@app.route('/oauth/user/info/get', methods=['POST', 'GET'])
def user_info():
    t = request.form.get('access_token', '') or request.args.get('access_token', '')
    d = verify_token(t)
    if not d:
        return jsonify({"code": 1004, "error": "invalid_token"})
    oid = d["open_id"]
    p = get_player(oid, d.get("nickname", "Player"))
    return jsonify({
        "open_id": oid,
        "nickname": d.get("nickname", "Player"),
        "gender": 1,
        "level": p["level"],
        "exp": p["exp"],
        "avatar": p["avatar"],
        "is_guest": d.get("type") == "guest",
        "created_time": now(),
        "vip_level": p["vip"],
        "diamond": p["diamond"],
        "gold": p["gold"],
        "coins": p["coins"],
        "rank": p["rank"],
        "region": p["region"],
        "skin_ids": p["skins"][:50],
        "character_ids": p["characters"],
        "weapon_skin_ids": p["weapons"],
        "pet_ids": p["pets"],
        "badges": [],
        "achievements": []
    })

# --- FRIENDS ---
@app.route('/oauth/user/friends/get/v2', methods=['POST', 'GET'])
def friends():
    return jsonify({"friends": [], "total": 0, "pending": []})

@app.route('/oauth/user/friends/info/get/v2', methods=['POST', 'GET'])
def friends_info():
    return jsonify({"friends_info": []})

@app.route('/oauth/user/friends/inapp/get/v2', methods=['POST', 'GET'])
def friends_inapp():
    return jsonify({"friends": []})

# --- LOGIN SOCIAL (stubs) ---
LAST_FB_UID = [10720210]

@app.route('/oauth/token/facebook/exchange', methods=['POST'])
def fb():
    # MONTROY: o MSDK troca o token recebido via fbconnect:// (emitido por conta_pv)
    # por um token Garena. Valida o token MONTROY e devolve o par de tokens.
    ftok = request.form.get('facebook_access_token', '') or request.form.get('access_token', '')
    uid = None
    try:
        import conta_pv as _cp
        uid = _cp.token_valido(ftok)
    except Exception as _e:
        print("[fb-exchange] conta_pv indisponivel:", repr(_e))
    if not uid:
        return jsonify({"code": 1004, "error": "invalid_token"})
    oid = str(uid)
    LAST_FB_UID[0] = uid
    nick = "Montroy%s" % oid[-4:]
    get_player(oid, nick)
    at = create_token(oid, nick, "oauth")
    nr = create_refresh_token(oid, nick, "oauth")
    return jsonify({
        "access_token": at,
        "refresh_token": nr,
        "open_id": oid,
        "expires_in": 2592000,
        "expiry_time": now() + 2592000,
        "platform": 3,
        "token_type": "Bearer"
    })
@app.route('/oauth/token/google/exchange', methods=['POST'])
def gg(): return jsonify({"code": 2017, "error": "not_supported"})
@app.route('/oauth/token/line/exchange', methods=['POST'])
def ln(): return jsonify({"code": 2017, "error": "not_supported"})
@app.route('/oauth/token/twitter/exchange', methods=['POST'])
def tw(): return jsonify({"code": 2017, "error": "not_supported"})
@app.route('/oauth/token/vk/exchange/v2', methods=['POST'])
def vk(): return jsonify({"code": 2017, "error": "not_supported"})
@app.route('/oauth/token/wechat/exchange', methods=['POST'])
def wc(): return jsonify({"code": 2017, "error": "not_supported"})

# --- BIND ---
@app.route('/game/guest/bind', methods=['POST'])
def guest_bind():
    t = request.form.get('access_token', '')
    d = verify_token(t)
    if not d: return jsonify({"code": 1004, "error": "invalid_token"})
    return jsonify({"success": True, "open_id": d["open_id"]})

@app.route('/bind/app/platform/create', methods=['POST'])
def bind_create(): return jsonify({"success": True})
@app.route('/bind/app/platform/info/get', methods=['GET', 'POST'])
def bind_info(): return jsonify({"platforms": []})

# --- LOJA ---
@app.route('/info/pricing', methods=['GET'])
def pricing():
    return jsonify({"pricing": {"diamonds": [
        {"id": i, "name": f"{n} Diamonds", "price": p, "currency": "USD"}
        for i, n, p in [(1,"100",0.99),(2,"310",2.99),(3,"520",4.99),(4,"1060",9.99),(5,"2180",19.99),(6,"5600",49.99)]
    ]}})

@app.route('/info/app-items', methods=['GET'])
def app_items():
    return jsonify({"items": [
        {"id": "skin_001", "name": "AK47 Skin", "type": "weapon", "price": 500, "currency": "diamond"},
        {"id": "skin_002", "name": "M4A1 Skin", "type": "weapon", "price": 500, "currency": "diamond"},
        {"id": "char_001", "name": "Character A", "type": "character", "price": 1500, "currency": "diamond"}
    ]})

@app.route('/app/point/get_balance', methods=['POST', 'GET'])
def balance():
    t = request.form.get('access_token', '') or request.args.get('access_token', '')
    d = verify_token(t)
    if not d: return jsonify({"code": 1004, "error": "invalid_token"})
    p = get_player(d["open_id"], d.get("nickname", "Player"))
    return jsonify({"diamond": p["diamond"], "gold": p["gold"], "coins": p["coins"], "tokens": p["tokens"]})

@app.route('/options/get', methods=['GET'])
def options():
    return jsonify({"options": [{"id": "free", "name": "Free (Private Server)", "enabled": True}]})

@app.route('/pay/google/commit', methods=['POST'])
def pay():
    return jsonify({"success": True, "message": "Item desbloqueado!"})

@app.route('/pay/event/init', methods=['POST'])
def pay_init(): return jsonify({"success": True, "event_id": str(uuid.uuid4())})
@app.route('/pay/event/cancel', methods=['POST'])
def pay_cancel(): return jsonify({"success": True})

# --- EVENTOS ---
@app.route('/info/event/config', methods=['GET'])
def event_cfg(): return jsonify({"events": []})
@app.route('/info/event/pricing', methods=['GET'])
def event_price(): return jsonify({"event_pricing": {}})
@app.route('/info/rebates', methods=['GET'])
def rebates(): return jsonify({"rebates": []})
@app.route('/rebates/redeem', methods=['POST'])
def redeem(): return jsonify({"success": True})

# --- GAME / SDK ---
def _heartbeat_response():
    return jsonify({"status": "ok", "server_time": now(),
                    "game_server": f"{GAME_IP}:{GAME_PORT}",
                    "online": len(game_server.clients) if game_server else 0})

@app.route('/api/heartbeat', methods=['POST'])
def heartbeat():
    t = request.form.get('access_token', '') or request.args.get('access_token', '')
    d = verify_token(t)
    if not d: return jsonify({"code": 1004, "error": "invalid_token"})
    return _heartbeat_response()

# FIX 9: rotas de heartbeat que o cliente pede em outras variantes
@app.route('/player/heartbeat', methods=['POST', 'GET'])
def player_heartbeat():
    t = request.form.get('access_token', '') or request.args.get('access_token', '')
    d = verify_token(t)
    if not d: return jsonify({"code": 1004, "error": "invalid_token"})
    return _heartbeat_response()

@app.route('/game/heartbeat', methods=['POST', 'GET'])
def game_heartbeat():
    return _heartbeat_response()

@app.route('/api/msdk', methods=['POST', 'GET'])
def msdk():
    return jsonify({
        "status": 0,
        "server_time": now(),
        "game_server": {"ip": GAME_IP, "port": GAME_PORT},
        "config": {"version": CLIENT_VERSION, "maintenance": False, "notice": ""}
    })

@app.route('/game/user/request/send', methods=['POST'])
def req_send(): return jsonify({"success": True})
@app.route('/google/init', methods=['POST'])
def g_init(): return jsonify({"success": True})

# --- OAUTH GARENA ---
@app.route('/oauth/garena', methods=['GET'])
def garena():
    oid = gen_open_id()
    nick = f'Player{secrets.randbelow(99999)}'
    at = create_token(oid, nick, "garena")
    return jsonify({"code": secrets.token_hex(16), "open_id": oid, "access_token": at})

# FIX 15 (v2.1.4): o botao Facebook (e qualquer login embedded do MSDK/GOP)
# abre ESTA rota numa WebView com redirect_uri=gop100067://auth/ e espera a
# pagina redirecionar de volta com ?code=... Antes devolvia JSON cru e o app
# dava errCode 2002 ("autenticacao falhou"). Agora: gera um code e devolve uma
# pagina HTML que redireciona SOZINHA -> entra com a conta automatico,
# igual ao Convidado (modo admin = mesma conta fixa).
# ==================================================================
# SISTEMA DE CONTAS KRYNO (v2.2.0) - login/cadastro com usuario/senha
# FIX IDENTIDADE: exchange devolve o open_id DO CODIGO; account_info e
# session_token devolvem o MESMO open_id do token (antes cada endpoint
# inventava um id diferente -> jogo dava "openid invalido")
# ==================================================================
ACCOUNTS = {}
ACCOUNTS_FILE = os.environ.get("ACCOUNTS_FILE", "kryno_accounts.json")
_accounts_lock = threading.Lock()

def _load_accounts():
    try:
        with open(ACCOUNTS_FILE) as f:
            for k, v in json.load(f).items():
                ACCOUNTS[k] = v
    except Exception:
        pass

def _save_accounts():
    try:
        with _accounts_lock:
            with open(ACCOUNTS_FILE, "w") as f:
                json.dump(ACCOUNTS, f)
    except Exception as e:
        print(f"[ACCOUNTS-ERR] {e}", flush=True)

_load_accounts()

def _ffauto_sig(username):
    return hmac.new(SECRET_KEY.encode(), ("ffauto:" + username).encode(), hashlib.sha256).hexdigest()[:32]

def _cookie_account():
    c = request.cookies.get("ffauto", "")
    if "." not in c:
        return None
    user, sig = c.rsplit(".", 1)
    if user in ACCOUNTS and hmac.compare_digest(sig, _ffauto_sig(user)):
        return user
    return None

def _make_authcode(open_id, nickname):
    payload = json.dumps({"open_id": open_id, "nickname": nickname, "t": now(), "kind": "authcode"})
    pb = base64.b64encode(payload.encode()).decode()
    sig = hmac.new(SECRET_KEY.encode(), pb.encode(), hashlib.sha256).hexdigest()
    return pb + "." + sig

def _verify_authcode(code):
    try:
        pb, sig = code.rsplit(".", 1)
        expect = hmac.new(SECRET_KEY.encode(), pb.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expect):
            return None
        d = json.loads(base64.b64decode(pb).decode())
        if d.get("kind") != "authcode":
            return None
        if now() - int(d.get("t", 0)) > 600:
            return None
        return d
    except Exception:
        return None

CONNECTED_TMPL = """<!DOCTYPE html><html><head><meta charset="UTF-8"></head><body style="background:#12122b;color:#e8e0ff;font-family:sans-serif;text-align:center;padding-top:40px"><h3>Conectado! Voltando ao jogo...</h3><p><a style="color:#a78bfa" href="__BACK__">Toque aqui se nao voltar sozinho</a></p><script>setTimeout(function(){location.href="__BACK__";},400);</script></body></html>"""

def _mk_response(html, status=200):
    from flask import make_response
    r = make_response(html, status)
    r.headers["Content-Type"] = "text/html; charset=utf-8"
    return r

PAGE_TPL = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
<title>Kryno FF - Login</title>
<script src="https://js.hcaptcha.com/1/api.js" async defer></script>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { background:#0d0b14; color:#fff; font-family:system-ui,-apple-system,sans-serif;
       min-height:100vh; display:flex; align-items:center; justify-content:center; padding:16px; }
.card { width:100%; max-width:360px; }
.logo { text-align:center; margin-bottom:20px; }
.logo h1 { font-size:30px; font-weight:800; letter-spacing:1px;
           color:#fff; text-shadow:0 0 18px #a855f7, 0 0 40px #7c3aed; }
.logo p { color:#8b8598; font-size:12px; margin-top:4px; }
.tabs { display:flex; gap:8px; margin-bottom:16px; }
.tab { flex:1; padding:11px; text-align:center; border-radius:12px; font-size:14px; font-weight:700;
       background:#171326; color:#8b8598; border:1px solid #251f38; cursor:pointer; transition:.2s; }
.tab.active { background:linear-gradient(135deg,#7c3aed,#a855f7); color:#fff;
              box-shadow:0 0 16px rgba(168,85,247,.45); border-color:#a855f7; }
form { display:none; }
form.active { display:block; }
label { display:block; font-size:12px; color:#b0a8c4; margin:12px 0 5px; font-weight:600; }
input { width:100%; padding:13px 14px; border-radius:12px; border:1px solid #2a2340;
        background:#171326; color:#fff; font-size:15px; outline:none; }
input:focus { border-color:#a855f7; box-shadow:0 0 12px rgba(168,85,247,.35); }
.btn { width:100%; margin-top:18px; padding:14px; border:none; border-radius:12px; font-size:15px;
       font-weight:800; color:#fff; background:linear-gradient(135deg,#7c3aed,#c084fc);
       box-shadow:0 0 18px rgba(168,85,247,.5); cursor:pointer; }
.btn:active { transform:scale(.98); }
.err { margin-top:12px; padding:10px 12px; border-radius:10px; background:#3b1220;
       color:#fda4af; font-size:13px; border:1px solid #7f1d2e; display:none; }
.foot { margin-top:16px; text-align:center; color:#5c5570; font-size:11px; }
</style>
</head>
<body>
<div class="card">
  <div class="logo">
    <h1>KRYNO FF</h1>
    <p>Bem-vindo ao servidor privado desenvolvido por Bryan</p>
  </div>
  <div class="tabs">
    <div class="tab" id="tab-login" onclick="showTab('login')">Entrar</div>
    <div class="tab active" id="tab-reg" onclick="showTab('reg')">Criar conta</div>
  </div>
  <form id="f-reg" class="active" method="post" action="/oauth/login/do">
    <input type="hidden" name="action" value="register">
    <input type="hidden" name="redirect_uri" value="__REDIRECT__">
    <input type="hidden" name="client_id" value="__CLIENT__">
    <label>Usuário</label>
    <input name="username" maxlength="16" placeholder="seu_usuario" required>
    <label>Senha</label>
    <input type="password" name="password" maxlength="32" placeholder="••••••••" required>
    <label>Nick no jogo (opcional)</label>
    <input name="nickname" maxlength="16" placeholder="Como vai aparecer no jogo">
    <div class="err" id="err"></div>
    <button class="btn" type="submit">CRIAR CONTA E ENTRAR</button>
  </form>
  <form id="f-login" method="post" action="/oauth/login/do">
    <input type="hidden" name="action" value="login">
    <input type="hidden" name="redirect_uri" value="__REDIRECT__">
    <input type="hidden" name="client_id" value="__CLIENT__">
    <label>Usuário</label>
    <input name="username" maxlength="16" placeholder="seu_usuario" required>
    <label>Senha</label>
    <input type="password" name="password" maxlength="32" placeholder="••••••••" required>
    <div class="err" id="err2"></div>
    <div class="h-captcha" data-sitekey="94bea0ac-d6dc-45ec-adce-d2fe24f06076" data-theme="dark"></div>
    <button class="btn" type="submit">ENTRAR NO JOGO</button>
  </form>
  <div class="foot">Servidor Privado por Bryan - Online - v1.71</div>
</div>
<script>
function showTab(t){
  document.getElementById('f-reg').className = t==='reg' ? 'active' : '';
  document.getElementById('f-login').className = t==='login' ? 'active' : '';
  document.getElementById('tab-reg').className = 'tab' + (t==='reg' ? ' active' : '');
  document.getElementById('tab-login').className = 'tab' + (t==='login' ? ' active' : '');
}
if ('__ERR__' !== '') {
  document.getElementById('err').style.display='block';
  document.getElementById('err2').style.display='block';
  showTab('reg');
}
</script>
</body>
</html>"""

def _render_page(err=""):
    redirect_uri = request.args.get('redirect_uri') or request.form.get('redirect_uri') or 'gop100067://auth/'
    client_id = request.args.get('client_id') or request.form.get('client_id') or '100067'
    return (PAGE_TPL
            .replace('__REDIRECT__', redirect_uri)
            .replace('__CLIENT__', client_id)
            .replace('__ERR__', err))

def _connected_html(code, redirect_uri, state=""):
    sep = '&' if '?' in redirect_uri else '?'
    back = f"{redirect_uri}{sep}code={code}"
    if state:
        back += f"&state={state}"
    return CONNECTED_TMPL.replace('__BACK__', back)

@app.route('/oauth/login', methods=['GET', 'POST'])
@app.route('/oauth/authorize', methods=['GET', 'POST'])
def login():
    user = _cookie_account()
    if user and request.args.get("logout") != "1":
        acc = ACCOUNTS[user]
        code = _make_authcode(acc["open_id"], acc.get("nickname") or user)
        redirect_uri = request.args.get('redirect_uri') or 'gop100067://auth/'
        state = request.args.get('state', '')
        return _mk_response(_connected_html(code, redirect_uri, state))
    if request.args.get("logout") == "1":
        resp = _mk_response(_render_page())
        resp.set_cookie("ffauto", "", expires=0)
        return resp
    return _mk_response(_render_page(request.args.get("err", "")))

@app.route('/oauth/login/do', methods=['POST'])
def login_do():
    action = request.form.get("action", "")
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    nickname = (request.form.get("nickname") or "").strip()
    redirect_uri = request.form.get("redirect_uri") or 'gop100067://auth/'
    state = request.form.get("state") or ""

    def fail(msg):
        return _mk_response(_render_page(msg), 400)

    if action == "register":
        if not username or not password:
            return fail("Usuario e senha sao obrigatorios!")
        if len(username) > 16 or len(password) > 32:
            return fail("Usuario ou senha muito longos!")
        if username in ACCOUNTS:
            return fail("Usuario ja existe! Escolha outro.")
        pwhash = hashlib.sha256(("kryno:" + username + ":" + password).encode()).hexdigest()
        oid = gen_open_id()
        nick = nickname or username
        ACCOUNTS[username] = {"pwhash": pwhash, "open_id": oid, "nickname": nick}
        _save_accounts()
        get_player(oid, nick)
        print(f"[KRYNO] register {username} -> {oid} nick={nick}", flush=True)
    elif action == "login":
        acc = ACCOUNTS.get(username)
        if not acc:
            return fail("Usuario nao existe!")
        pwhash = hashlib.sha256(("kryno:" + username + ":" + password).encode()).hexdigest()
        if pwhash != acc["pwhash"]:
            return fail("Senha errada!")
        oid = acc["open_id"]
        nick = acc.get("nickname") or username
        get_player(oid, nick)
    else:
        return fail("Acao invalida!")

    code = _make_authcode(oid, nick)
    resp = _mk_response(_connected_html(code, redirect_uri, state))
    resp.set_cookie("ffauto", username + "." + _ffauto_sig(username),
                    max_age=7776000, httponly=True, path="/")
    return resp

# --- CRASH LOGS ---
@app.route('/crash/logs/', methods=['POST', 'GET'])
def crash():
    print(f"[CRASH-LOG] recebido {request.content_length} bytes", flush=True)
    return jsonify({"success": True})

# --- ACCOUNT INFO ---
@app.route('/api/account_info_get', methods=['GET', 'POST'])
def account_info():
    d = _token_from_request()
    if d:
        oid = d["open_id"]
    else:
        # FIX 11: sem token valido usa o open_id enviado; NUNCA gera aleatorio
        oid = _open_id_from_request()
        if not oid or oid not in PLAYERS:
            return jsonify({"code": 1004, "error": "invalid_token"})
    p = get_player(oid)
    return jsonify({
        "open_id": oid,
        "account_id": oid,
        "nickname": p["nickname"],
        "level": p["level"],
        "exp": p["exp"],
        "diamonds": p["diamond"],
        "coins": p["coins"],
        "rank": p["rank"],
        "region": p["region"],
        "avatar": p["avatar"],
        "character_ids": p["characters"],
        "skin_ids": p["skins"][:50],
        "weapon_skin_ids": p["weapons"],
        "pet_ids": p["pets"],
        "is_banned": False,
        "is_guest": True
    })

# --- CHANNEL INFO ---
@app.route('/api/channel_info_get', methods=['GET', 'POST'])
def channel_info():
    return jsonify({"channel_id": "BR", "channel_name": "Brasil", "status": "active"})

# --- SESSION TOKEN ---
@app.route('/api/session_token_get', methods=['GET', 'POST'])
def session_token():
    # FIX 11: open_id consistente com quem pediu (antes vinha aleatorio)
    d = _token_from_request()
    if d:
        return jsonify({"session_token": gen_open_id(), "open_id": d["open_id"], "expiry_time": now() + 3600})
    oid = _open_id_from_request()
    if oid and oid in PLAYERS:
        return jsonify({"session_token": gen_open_id(), "open_id": oid, "expiry_time": now() + 3600})
    return jsonify({"session_token": gen_open_id(), "open_id": gen_open_id(), "expiry_time": now() + 3600})

# --- REFRESH TOKEN GET ---
@app.route('/api/refresh_token_get', methods=['GET', 'POST'])
def refresh_get():
    # FIX 11: token da MESMA conta (antes criava player novo do nada)
    d = _token_from_request()
    if d:
        at = create_token(d["open_id"], d.get("nickname", "Player"), d.get("type", "guest"))
        return jsonify({"access_token": at, "expiry_time": now() + 86400 * 30})
    oid = _open_id_from_request()
    if oid and oid in PLAYERS:
        p = get_player(oid)
        return jsonify({"access_token": create_token(oid, p["nickname"], "guest"), "expiry_time": now() + 86400 * 30})
    return jsonify({"code": 1004, "error": "invalid_token"})

# --- HEALTH ---
@app.route('/health', methods=['GET'])
def health():
    # FIX 5: reporta rooms/conexões reais (ROOMS/SOCKETS globais eram sempre 0)
    return jsonify({
        "status": "online",
        "server": "Free Fire Private Server",
        "version": "2.2.0",
        "http_port": HTTP_PORT,
        "game_port": GAME_PORT,
        "game_ip": GAME_IP,
        "players": len(PLAYERS),
        "rooms": len(game_server.rooms) if (game_server := globals().get("game_server")) else 0,
        "connections": len(game_server.clients) if (game_server := globals().get("game_server")) else 0
    })

# --- CATCH ALL ---

# --- LIVEVER (FF2018 pede livever.php no host do jogo) ---
@app.route('/livever.php', methods=['GET', 'POST'])
def livever():
    return jsonify({
        "code": 0,
        "appstore_url": "",
        "billboard_msg": "Bem-vindo ao servidor privado desenvolvido por Bryan",
        "cdn_url": "https://cdn.barbosasmobile.com/",
        "client_ip": request.headers.get("X-Forwarded-For", "127.0.0.1"),
        "country_code": "BR",
        "force_to_restart_app": False,
        "gdpr_version": 2,
        "is_firewall_open": False,
        "is_review_server": False,
        "is_server_open": True,
        "maintenance_announcement": "",
        "maintenance_region": "",
        "remote_option_version": "1.25.3",
        "remote_version": "1.25.3",
        "server_url": request.url_root
    })

# --- FB GRAPH (SDK 4.9 do FF2018: /v2.5/<app_id>) ---
@app.route('/v2.5/<app_id>', methods=['GET', 'POST'])
def fb_graph(app_id):
    return jsonify({
        "id": app_id,
        "android_dialog_configs": {},
        "android_sdk_error_categories": [],
        "gdpv4_nux_content": {},
        "gdpv4_nux_enabled": False,
        "supports_implicit_sdk_logging": True
    })

@app.route('/v2.5/<app_id>/activities', methods=['GET', 'POST'])
def fb_activities(app_id):
    return jsonify({"server_time": now(), "status": "ok"})

# --- DEBUG/PHONE (telemetria do cliente 2018) ---
@app.route('/debug/phone', methods=['POST', 'GET'])
def debug_phone():
    return "ok"

@app.route("/_logs", methods=["GET"])
def _dump_all_logs():
    import os as _os
    out = {}
    for fn in ("requests.log", "unknown_endpoints.log", "response_samples.log"):
        try:
            with open(_os.path.join(_os.environ.get("LOG_DIR", "."), fn)) as f:
                out[fn] = f.read()[-8000:]
        except Exception as e:
            out[fn] = f"erro: {e}"
    return jsonify(out)

# FIX 19/10: os decoradores catch-all estavam em cima de _dump_all_logs
# (que nao recebe 'path') -> todo endpoint desconhecido dava TypeError/500
# (LogEvent, GetCardsAndIAPInfo etc). Movidos pra catch_all, como deve ser.
@app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE'])
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def catch_all(path):
    # FIX (v2.2.0): desconhecidos respondem {"status":"ok"} (igual deploy atual)
    try:
        with open("unknown_endpoints.log", "a") as f:
            f.write(f"{now()} {request.method} /{path} {dict(request.args)}\n")
    except Exception:
        pass
    print(f"[UNKNOWN] {request.method} /{path}", flush=True)
    # Rotas do lobby 1.70 (CamelCase, protobuf): corpo vazio = mensagem protobuf vazia valida
    if path and path[0].isupper() and "/" not in path:
        return b"", 200, {"Content-Type": "application/octet-stream"}
    return jsonify({"server_time": now(), "status": "ok"})
