# Contas reais (registro/login) com a MESMA tela do pautavero. SQLite + PBKDF2 + captcha matematico assinado.
import os, sys, json, time, hmac, hashlib, base64, secrets, sqlite3, random, re, threading, urllib.request

APP_ID = "6002969496135738"
HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get("CONTA_DB", os.path.join(HERE, "contas.db"))
SECRET = (os.environ.get("CONTA_SECRET") or hashlib.sha256((os.environ.get("RENDER_SERVICE_ID", "rzim") + "conta-v1").encode()).hexdigest()).encode()
_lock = threading.Lock()
LOGIN_HTML = open(os.path.join(HERE, "login_pv.html"), "rb").read()

def _db():
    c = sqlite3.connect(DB, timeout=10)
    c.execute("CREATE TABLE IF NOT EXISTS conta (uid INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT UNIQUE COLLATE NOCASE, salt TEXT, hash TEXT, criado INTEGER)")
    return c

def _hash(senha, salt):
    return hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(salt), 120000).hex()

def _sig(msg):
    return base64.urlsafe_b64encode(hmac.new(SECRET, msg.encode(), hashlib.sha256).digest()).decode().rstrip("=")

# --- BANCO PERMANENTE: funcao Base44 (entidade ContaPv). SQLite so como fallback. ---
CONTA_URL = os.environ.get("CONTA_URL", "https://elio-43de708f.base44.app/functions/contaPv")
CONTA_CHAVE = os.environ.get("CONTA_CHAVE", "")

def _remote(acao, **campos):
    payload = json.dumps({"acao": acao, "chave": CONTA_CHAVE, **campos}).encode()
    req = urllib.request.Request(CONTA_URL, data=payload, headers={"Content-Type": "application/json", "User-Agent": "MontroyLobby/1.0"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        # 409 existe / 404 nao_existe vem com corpo JSON valido — devolver, nao estourar
        corpo = e.read().decode()[:200]
        try:
            return json.loads(corpo)
        except Exception:
            raise


def _cria_remoto(user, senha):
    salt = secrets.token_hex(16)
    resp = _remote("registrar", usuario=user, salt=salt, hash=_hash(senha, salt))
    if not resp.get("ok"):
        return resp.get("erro", "erro")
    return int(resp["uid"])

def _busca_remoto(user):
    resp = _remote("login", usuario=user)
    if not resp.get("ok"):
        return None
    return int(resp["uid"]), resp["salt"], resp["hash"]

def _captcha():
    a, b = random.randint(2, 19), random.randint(2, 9)
    op = random.choice(["+", "-", "x"])
    r = a + b if op == "+" else (a - b if op == "-" else a * b)
    exp = int(time.time() * 1000) + 5 * 60 * 1000
    nonce = secrets.token_urlsafe(9)
    payload = "%s.%d" % (nonce, exp)
    h = hashlib.sha256((str(r) + "|" + nonce).encode()).hexdigest()[:20]
    token = "%s.%s.%s" % (payload, h, _sig(payload + h))
    linhas = "".join('<line x1="%d" y1="%d" x2="%d" y2="%d" opacity="0.18"/>' % (random.randint(0, 220), random.randint(0, 70), random.randint(0, 220), random.randint(0, 70)) for _ in range(7))
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="220" height="70" viewBox="0 0 220 70">'
           '<rect width="220" height="70" rx="14" fill="#090507"/><g stroke="#ff5353" stroke-width="1">%s</g>'
           '<text x="110" y="45" font-family="Arial" font-size="30" font-weight="bold" fill="#ffd0d0" text-anchor="middle" letter-spacing="3">%d %s %d = ?</text></svg>') % (linhas, a, op, b)
    return {"token": token, "image": "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()}

def _captcha_ok(token, resp):
    try:
        nonce, exp, h, sg = token.split(".")
        if int(exp) < time.time() * 1000: return False
        if not hmac.compare_digest(sg, _sig("%s.%s%s" % (nonce, exp, h))): return False
        return hmac.compare_digest(hashlib.sha256((str(int(str(resp).strip())) + "|" + nonce).encode()).hexdigest()[:20], h)
    except Exception:
        return False

def _token(uid):
    exp = int(time.time()) + 60 * 86400
    p = "%d.%d" % (uid, exp)
    return "RZIM%s.%s" % (p, _sig("tok" + p)[:24])

def token_valido(tok):
    try:
        p, s = tok[4:].rsplit(".", 1)
        uid, exp = p.split(".")
        return int(exp) > time.time() and hmac.compare_digest(s, _sig("tok" + p)[:24]) and int(uid)
    except Exception:
        return None

def _data(uid):
    tok = _token(uid)
    ex = 60 * 86400
    frag = "granted_scopes=email%%2Copenid%%2Cpublic_profile&denied_scopes=&access_token=%s&expires_in=%d&open_id=local%%3A%d&uid=%d" % (tok, ex, uid, uid)
    return {"app_id": APP_ID, "access_token": tok, "open_id": "local:%d" % uid, "uid": str(uid), "user_id": str(uid), "expires_in": ex,
            "redirect_url": "fb%s://authorize/#%s" % (APP_ID, frag)}

def _json(code, obj, pair="rzim-pair"):
    return code, json.dumps(obj, separators=(",", ":")).encode(), "application/json"

def tratar(rota, metodo, corpo):
    """devolve (status, bytes, content_type) ou None se a rota nao e de conta"""
    if rota in ("/access", "/login") or rota.startswith("/access?"):
        return 200, LOGIN_HTML, "text/html; charset=utf-8"
    if rota == "/api/captcha":
        return _json(200, _captcha())
    if rota not in ("/api/login", "/api/register"):
        return None
    if metodo != "POST":
        return _json(200, {"success": False, "message": "Use POST.", "pair_id": "rzim-pair"})
    try:
        d = json.loads(corpo or b"{}")
    except Exception:
        d = {}
    user = str(d.get("username", "")).strip()
    senha = str(d.get("password", ""))
    if rota == "/api/register":
        if not _captcha_ok(str(d.get("captcha_token", "")), d.get("captcha_answer", "")):
            return _json(400, {"success": False, "message": "Captcha inválido ou expirado. Tente novamente.", "pair_id": "rzim-pair"})
        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,20}", user):
            return _json(400, {"success": False, "message": "Usuário deve ter 3 a 20 letras, números, _ . ou -.", "pair_id": "rzim-pair"})
        if len(senha) < 4 or len(senha) > 64:
            return _json(400, {"success": False, "message": "A senha deve ter entre 4 e 64 caracteres.", "pair_id": "rzim-pair"})
        if senha != str(d.get("password_confirmation", senha)):
            return _json(400, {"success": False, "message": "As senhas não conferem.", "pair_id": "rzim-pair"})
        try:
            r = _cria_remoto(user, senha)
        except Exception as _e:
            import traceback as _tb
            print("[conta] FALHA remoto registro:", repr(_e), file=sys.stderr)
            _tb.print_exc()
            r = None
        if r == "existe":
            return _json(409, {"success": False, "message": "Esse usuário já existe.", "pair_id": "rzim-pair"})
        if isinstance(r, int):
            return _json(200, {"success": True, "data": _data(r), "pair_id": "rzim-pair"})
        # fallback SQLite local (Base44 fora do ar)
        salt = secrets.token_hex(16)
        with _lock:
            c = _db()
            try:
                cur = c.execute("INSERT INTO conta(usuario,salt,hash,criado) VALUES(?,?,?,?)", (user, salt, _hash(senha, salt), int(time.time())))
                c.commit(); uid = 10000000 + cur.lastrowid
            except sqlite3.IntegrityError:
                return _json(409, {"success": False, "message": "Esse usuário já existe.", "pair_id": "rzim-pair"})
            finally:
                c.close()
        return _json(200, {"success": True, "data": _data(uid), "pair_id": "rzim-pair"})
    # login: banco permanente primeiro
    try:
        achou = _busca_remoto(user)
    except Exception as _e:
        print("[conta] FALHA remoto login:", repr(_e), file=sys.stderr)
        achou = None
    if achou:
        uid, salt, hh = achou
        if hmac.compare_digest(_hash(senha, salt), hh):
            return _json(200, {"success": True, "data": _data(uid), "pair_id": "rzim-pair"})
        return _json(401, {"success": False, "message": "Usuário ou senha incorretos.", "pair_id": "rzim-pair"})
    with _lock:
        c = _db()
        try:
            r = c.execute("SELECT uid,salt,hash FROM conta WHERE usuario=?", (user,)).fetchone()
        finally:
            c.close()
    if not r or not hmac.compare_digest(_hash(senha, r[1]), r[2]):
        return _json(401, {"success": False, "message": "Usuário ou senha incorretos.", "pair_id": "rzim-pair"})
    return _json(200, {"success": True, "data": _data(10000000 + r[0]), "pair_id": "rzim-pair"})

def application(environ, start_response):
    rota = environ.get("PATH_INFO", "")
    try:
        n = int(environ.get("CONTENT_LENGTH") or 0)
        corpo = environ["wsgi.input"].read(min(n, 8192)) if n else b""
    except Exception:
        corpo = b""
    r = tratar(rota, environ.get("REQUEST_METHOD", "GET"), corpo)
    if r is None:
        r = (404, b'{"status":"not_found"}', "application/json")
    cod, body, ct = r
    start_response("%d OK" % cod if cod == 200 else "%d X" % cod, [("Content-Type", ct), ("Content-Length", str(len(body))), ("Cache-Control", "no-store")])
    return [body]
