#!/usr/bin/env python3
"""Captura em lote: sessao completa contra o servidor de referencia via ponte.

Fluxo: captcha -> login -> exchange -> MajorLogin -> /Login (ticket)
       -> todas as rotas de leitura do /signal/main.
Nao dispara endpoints que mudam o estado do jogador (Choose*/Change*).
"""
import base64, json, re, time, urllib.request, urllib.error, sys
from Crypto.Cipher import AES

K = bytes.fromhex("482a4a694f706a7a425e364a664c6e4a")
IV = bytes.fromhex("6b6e56705621264d79372371304d6948")
LOBBY = "https://rzim-lobby143.onrender.com"
MAIN = "https://rzim.onrender.com/signal/main"
UA = "Dalvik/2.1.0 (Linux; U; Android 16; 2312CRNCCL Build/BP2A.250605.031.A3)"

def http(url, data=None, headers=None, timeout=40, tries=3):
    for t in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=headers or {})
            r = urllib.request.urlopen(req, timeout=timeout)
            return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except Exception as e:
            if t == tries - 1:
                raise
            time.sleep(2)

def aes_dec(b):
    p = AES.new(K, AES.MODE_CBC, IV).decrypt(b)
    return p[:-p[-1]] if 0 < p[-1] <= 16 else p

def aes_enc(p):
    pad = 16 - (len(p) % 16)
    return AES.new(K, AES.MODE_CBC, IV).encrypt(p + bytes([pad]) * pad)

def pbf(b):  # varint lido simples
    def rd(bb, i):
        r_ = 0; s_ = 0
        while True:
            x = bb[i]; i += 1
            r_ |= (x & 0x7f) << s_; s_ += 7
            if not x & 0x80: return r_, i
    i = 0; out = {}
    while i < len(b):
        try: k, i = rd(b, i)
        except Exception: break
        f, w = k >> 3, k & 7
        if w == 0:
            v, i = rd(b, i); out.setdefault(f, v)
        elif w == 2:
            l, i = rd(b, i); out.setdefault(f, b[i:i+l]); i += l
        elif w == 5: i += 4
        elif w == 1: i += 8
        else: break
    return out

caps_l = [json.loads(x) for x in open('/tmp/caps_l.jsonl') if x.strip()]
caps_m = [json.loads(x) for x in open('/tmp/cap_rzim.onrender.com.jsonl') if x.strip()]
last = lambda cs, rota: [c for c in cs if c['rota'] == rota][-1]

print("[1/6] captcha...")
st, b = http(LOBBY + "/api/captcha")
j = json.loads(b)
svg = base64.b64decode(j['image'].split('base64,')[1]).decode()
txts = re.findall(r'>([^<>])</text>', svg)
eq = "".join(txts).replace('=', '').replace('?', '')
ans = str(eval(eq))
print("   captcha:", eq, "=", ans)

print("[2/6] login bryanzim...")
st, b = http(LOBBY + "/api/login", data=json.dumps({
    "username": "bryanzim", "password": "bryan2026",
    "captcha_token": j['token'], "captcha_answer": ans,
    "pair_id": "x"}).encode(),
    headers={"Content-Type": "application/json", "User-Agent": UA})
lj = json.loads(b)
if not lj.get('success'):
    print("   FALHOU:", b[:200]); sys.exit(1)
rurl = lj['data']['redirect_url']
sr = re.search(r'signed_request=([^&]+)', rurl).group(1)
payload = sr.split('.')[1]
payload += "=" * (-len(payload) % 4)
sj = json.loads(base64.urlsafe_b64decode(payload))
token = sj['code']
print("   token (%d chars):" % len(token), token[:12] + "...")
print("   token:", token[:12] + "...")

print("[3/6] exchange...")
st, b = http(LOBBY + "/oauth/token/facebook/exchange", data=json.dumps({
    "grant_type": "authorization_code", "facebook_access_token": token,
    "redirect_uri": "gop100067://auth/", "source": "2"}).encode(),
    headers={"Content-Type": "application/json", "User-Agent": UA})
ej = json.loads(b)
print("   ok:", ej.get('code') == 0)

print("[4/6] MajorLogin (token fresco no corpo)...")
ml_body = base64.b64decode(last(caps_l, '/MajorLogin')['req_b64'])
ml_dec = aes_dec(ml_body)

def rdvar(bb, i):
    r_ = 0; s_ = 0
    while True:
        x = bb[i]; i += 1
        r_ |= (x & 0x7f) << s_; s_ += 7
        if not x & 0x80: return r_, i

def wrvar(n):
    out = b""
    while True:
        x = n & 0x7f; n >>= 7
        out += bytes([x | (0x80 if n else 0)])
        if not n: return out

def rebuild(msg, newtok):
    out = b""; i = 0; trocou = False
    while i < len(msg):
        k, i = rdvar(msg, i)
        f, w = k >> 3, k & 7
        if w == 0:
            v, i = rdvar(msg, i)
            out += wrvar(k) + wrvar(v)
        elif w == 2:
            l, i = rdvar(msg, i); v = msg[i:i+l]; i += l
            if not trocou and re.fullmatch(rb'[0-9a-f]{96}', v):
                v = newtok; trocou = True
            out += wrvar(k) + wrvar(len(v)) + v
        elif w == 5:
            out += msg[i-2:i+4] if False else wrvar(k) + msg[i:i+4]; i += 4
        elif w == 1:
            out += wrvar(k) + msg[i:i+8]; i += 8
        else:
            return msg
    assert trocou, "token antigo nao achado no corpo"
    return out

novo = rebuild(ml_dec, token.encode())
st, ml_resp = http(LOBBY + "/MajorLogin", data=aes_enc(novo),
    headers={"Content-Type": "application/octet-stream", "User-Agent": UA})
print("   status:", st, "| resp:", len(ml_resp), "B")

print("[5/6] /Login (ticket)...")
lg_body = base64.b64decode(last(caps_l, '/Login')['req_b64'])
st, lg_resp = http(LOBBY + "/Login", data=lg_body,
    headers={"Content-Type": "application/octet-stream", "User-Agent": UA})
print("   status:", st, "| resp:", len(lg_resp), "B")
campos = pbf(lg_resp)
ticket = None
for k, v in campos.items():
    if isinstance(v, bytes) and len(v) in (96, 48) and re.fullmatch(rb'[0-9a-f]+', v):
        ticket = v.decode()
print("   uid:", campos.get(1), "| ticket:", (ticket or '?')[:12] + "...")
if not ticket:
    for k, v in campos.items():
        if isinstance(v, bytes): print("    campo", k, v[:50].hex())
    sys.exit(1)

HDRS = {"Content-Type": "application/octet-stream", "User-Agent": UA,
        "Authorization": "Bearer " + ticket,
        "X-Unity-Version": "2018.4.11f1", "X-GA": "v1 1"}

# rotas de leitura (ordem do cliente); pula mutaveis e logs
PULA = {"ChangeClothes", "ChooseEmote", "ChooseSlots", "ChooseShow", "ChooseBanner",
        "ChooseHeadPic", "ChooseGameBagShow", "UnlockFittingSlot", "EPClaimReward",
        "EPPurchaseBadge", "ActivityTrigger", "LogEvent", "NetworkLogEvent",
        "GetStore"}
seq_por_rota = {}
for c in caps_m:
    nome = c['rota'].split('/')[-1]
    seq_por_rota.setdefault(nome, base64.b64decode(c['req_b64']))

rotas = []
for nome in seq_por_rota:
    if nome not in PULA:
        rotas.append(nome)
rotas = sorted(rotas)
# ordem: GetLoginData primeiro (corpo de dispositivo), depois resto
rotas.sort(key=lambda n: 0 if n == "GetLoginData" else 1)

print("[6/6] disparando %d rotas..." % len(rotas))
ok = vazias = erro = 0
for n in rotas:
    body = seq_por_rota[n]
    try:
        st, resp = http(MAIN + "/" + n, data=body, headers=HDRS, tries=2)
        if st == 200:
            ok += 1
            if not resp: vazias += 1
            print("   %-42s %d %6dB" % (n, st, len(resp)))
        else:
            erro += 1
            print("   %-42s %d FALHA" % (n, st))
    except Exception as e:
        erro += 1
        print("   %-42s ERRO %s" % (n, str(e)[:40]))
    time.sleep(0.35)
print("resumo: ok=%d (vazias=%d) erro=%d" % (ok, vazias, erro))
