#!/usr/bin/env python3
# AISAKA/CAELUS SERVER v0.1 — emulador de API Roblox 2.463 (2021) para o cliente Aisaka
# Redirecionamento do APK: todos os servicos caelus.lol -> web-production-115c6.up.railway.app
#   www.<dominio>/...           -> https://<host>/...           (raiz)
#   clientsettings/clientsettingscdn -> https://<host>/v1|v2/settings/...
#   j-services (auth, chat, thumbnails, ...) -> https://<host>/<servico>/...
# Padrao de iteracao: before_request loga TUDO em requests.log; endpoints nao
# implementados vao pro unknown_endpoints.log p/ mapearmos a proxima rodada.
import json, time, uuid, threading, os
from datetime import datetime
from flask import Flask, request, jsonify, Response

APP_VERSION = "0.1.0"
LOG_LOCK = threading.Lock()
LOG_DIR = os.environ.get("LOG_DIR", ".")

app = Flask(__name__)
app.json.sort_keys = False

def log_line(fname, msg):
    try:
        with LOG_LOCK:
            with open(os.path.join(LOG_DIR, fname), "a") as f:
                f.write(f"[{datetime.utcnow().isoformat()}Z] {msg}\n")
    except Exception:
        pass

def log_json(label, obj):
    try:
        log_line("response_samples.log", label + ": " + json.dumps(obj)[:4000])
    except Exception:
        pass

@app.before_request
def before_request():
    body = ""
    try:
        body = request.get_data(as_text=True)[:2000]
    except Exception:
        pass
    log_line("requests.log", f"{request.method} {request.full_path} UA={request.user_agent.string[:120]} BODY={body}")

# ---------------- clientsettings (bootstrap, o cliente trava sem isso) --------
CS_SETTINGS = {
    "FFlagDebugDisableTelemetryEphemeralCounter": "True",
    "FFlagDebugDisableTelemetryEphemeralStat": "True",
    "FFlagDebugDisableTelemetryEventIngest": "True",
    "FFlagDebugDisableTelemetryPoint": "True",
    "FFlagDebugDisableTelemetryV2Counter": "True",
    "FFlagDebugDisableTelemetryV2Event": "True",
    "FFlagDebugDisableTelemetryV2Stat": "True",
    "DFIntDefaultFramebufferQuality": "5",
}

def cs_v1(app_name="AndroidApp"):
    # formato v1 classico: {"applicationName": ..., "settings": {...}}
    return {"applicationName": app_name, "settings": dict(CS_SETTINGS)}

def cs_v2(app_name="AndroidApp"):
    # formato v2 (lista de settings com tipo)
    settings = [{"name": k, "type": "DynamicFlag" if k.startswith("FFlag") else "DynamicInt", "value": v}
                for k, v in CS_SETTINGS.items()]
    return {"data": {"applicationName": app_name,
                     "lastUpdated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                     "isDefaults": False,
                     "schemaVersion": 1,
                     "settings": settings}}

@app.route("/v1/settings/application", methods=["GET", "POST"])
def cs_v1_route():
    name = request.args.get("applicationName", "AndroidApp")
    obj = cs_v1(name)
    log_json("cs_v1", obj)
    return jsonify(obj)

@app.route("/v2/settings/application/<app_name>", methods=["GET", "POST"])
@app.route("/v2/settings/application/<app_name>/bucket/<bucket>", methods=["GET", "POST"])
def cs_v2_route(app_name, bucket=None):
    obj = cs_v2(app_name)
    log_json("cs_v2", obj)
    return jsonify(obj)

# formato alternativo de bucket (alguns clientes pedem assim)
@app.route("/clientsettings.api/v1/settings/application", methods=["GET", "POST"])
def cs_api_v1():
    return cs_v1_route()

@app.route("/clientsettings.api/v2/settings/application/<app_name>", methods=["GET", "POST"])
@app.route("/clientsettings.api/v2/settings/application/<app_name>/bucket/<bucket>", methods=["GET", "POST"])
def cs_api_v2(app_name, bucket=None):
    return cs_v2_route(app_name)

# ---------------- helpers de resposta generica --------------------------------
def empty_list(key="data"):
    return jsonify({key: []})

# ---------------- auth ---------------------------------------------------------
# 2021 mobile: login anonimo por device. Respondemos um "usuario convidado".
def guest_user():
    return {
        "id": 1, "name": "Player1", "displayName": "Player1",
        "description": "", "created": "2020-01-01T00:00:00Z",
        "isGuest": True, "hasVerifiedBadge": False,
    }

@app.route("/auth/v1/credentials", methods=["GET", "POST"])
@app.route("/auth/v2/credentials", methods=["GET", "POST"])
def auth_credentials():
    return jsonify({"errors": [{"code": 1, "message": "Unauthorized"}]}), 401

@app.route("/auth/v2/logout", methods=["POST"])
def auth_logout():
    return jsonify({})

@app.route("/auth/v1/authentication/anonymous", methods=["POST"])
@app.route("/auth/v2/authentication/anonymous", methods=["POST"])
def auth_anon():
    obj = {"session": str(uuid.uuid4()), "user": guest_user()}
    log_json("auth_anon", obj)
    return jsonify(obj)

# ---------------- servicos j- (prefixo como caminho) ---------------------------
# Respostas vazias validas para o cliente nao quebrar; tudo logado pra iterar.

@app.route("/accountinformation/v1/<path:sub>", methods=["GET", "POST"])
def acct_info(sub):
    return jsonify(guest_user())

@app.route("/accountsettings/v1/<path:sub>", methods=["GET", "POST"])
def acct_settings(sub):
    return empty_list()

@app.route("/friends/v1/<path:sub>", methods=["GET", "POST"])
@app.route("/friends/v2/<path:sub>", methods=["GET", "POST"])
def friends(sub):
    return empty_list()

@app.route("/chat/v2/<path:sub>", methods=["GET", "POST"])
@app.route("/chat/v1/<path:sub>", methods=["GET", "POST"])
def chat(sub):
    return empty_list()

@app.route("/notifications/v1/<path:sub>", methods=["GET", "POST"])
@app.route("/notifications/v2/<path:sub>", methods=["GET", "POST"])
def notifications(sub):
    return empty_list("data")

@app.route("/translations/v1/<path:sub>", methods=["GET"])
def translations(sub):
    return jsonify({})

@app.route("/locale/v1/locales", methods=["GET"])
def locales():
    return jsonify({"supportedLocales": [{"locale": "en-us", "language": {"language": "en", "name": "English", "nativeName": "English"}}],
                    "defaultLocale": "en_us"})

@app.route("/thumbnails/v1/batch", methods=["GET", "POST"])
def thumbs_batch():
    ids = request.args.get("userIds", "1")
    data = [{"targetId": int(x) if x.isdigit() else 1,
             "state": "Completed",
             "imageUrl": "https://tr.rbxcdn.com/30DAY-AvatarHeadshot-Placeholder-png"}
            for x in ids.split(",")[:10]]
    return jsonify({"data": data})

@app.route("/thumbnails/v1/<path:sub>", methods=["GET", "POST"])
def thumbs(sub):
    return empty_list("data")

@app.route("/ephemeralcounters/v1.1/Counters/Increment/", methods=["POST"])
@app.route("/ephemeralcounters/v1.0/SequenceStatistics/AddToSequence", methods=["POST"])
def counters():
    return jsonify({})

@app.route("/ecsv2/mobile/pbe", methods=["GET", "POST"])
def ecsv2():
    return jsonify({})

@app.route("/metrics/v1/performance/send-measurement", methods=["POST"])
def metrics():
    return jsonify({})

@app.route("/abtesting/v1/<path:sub>", methods=["GET", "POST"])
def abtesting(sub):
    return empty_list("data")

@app.route("/abtesting/v1/ab-test", methods=["GET"])
def abtest():
    return empty_list("data")

@app.route("/contacts/v1/<path:sub>", methods=["GET", "POST"])
def contacts(sub):
    return empty_list()

# ---------------- catch-all: mapa de descoberta -------------------------------
@app.route("/", methods=["GET"])
@app.route("/<path:sub>", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
def catch_all(sub=""):
    body = ""
    try:
        body = request.get_data(as_text=True)[:1500]
    except Exception:
        pass
    log_line("unknown_endpoints.log",
             f"{request.method} /{sub} Q={request.query_string.decode()[:500]} BODY={body}")
    # JSON generico e seguro
    return jsonify({"data": [], "errors": None})

if __name__ == "__main__":
    print(f"* AISAKA/CAELUS SERVER v{APP_VERSION} *")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# --- ROTA DE LOGS (para o agente monitorar o trafego remotamente) ---
@app.route("/_logs", methods=["GET"])
def _dump_logs():
    import os as _os
    out = {}
    for fn in ("requests.log", "unknown_endpoints.log", "response_samples.log"):
        try:
            with open(_os.path.join(LOG_DIR, fn)) as f:
                out[fn] = f.read()[-8000:]
        except Exception as e:
            out[fn] = f"erro: {e}"
    return jsonify(out)
