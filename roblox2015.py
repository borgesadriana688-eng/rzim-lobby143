# -*- coding: utf-8 -*-
# Roblox 2015 private server (port do RobloxServer de RetiiAyo/101happy para Flask)
# Cliente: Roblox Studio 14/jan/2015 via redirecionamento Fiddler
import os
import time
import urllib.request
import json
from flask import Flask, request, jsonify, Response, redirect

app = Flask(__name__)
STORAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rbx2015_storage")
_score = {}

def log_line(msg):
    try:
        with open("requests.log", "a") as f:
            f.write(f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] RBX2015 {msg}\n")
    except Exception:
        pass

APPSETTINGS_BODY = {
    "FakeUserAgent": False,
    "FakeUserAgentString": "Roblox",
    "UserAgentSuffix": "v2.200.60733",
    "BaseUrl": "rzim-roblox.onrender.com/",
    "BaseMobileUrl": "rzim-roblox.onrender.com/",
}

@app.route("/Setting/QuietGet/AndroidAppSettings", methods=["GET"])
@app.route("/Setting/QuietGet/AndroidAppSettings/", methods=["GET"])
@app.route("/Setting/QuietGet/ClientSharedSettings", methods=["GET"])
@app.route("/Setting/QuietGet/ClientSharedSettings/", methods=["GET"])
@app.route("/Setting/QuietGet/ClientAppSettings", methods=["GET"])
@app.route("/Setting/QuietGet/ClientAppSettings/", methods=["GET"])
def _settings_quiet():
    log_line(f"GET {request.path}")
    return jsonify(APPSETTINGS_BODY)

@app.route("/mobileapi/check-app-version", methods=["GET"])
def _checkappversion():
    log_line(f"GET mobileapi/check-app-version Q={request.query_string.decode()[:60]}")
    return jsonify({"data": {"status": "Success"}})

@app.route("/mobileapi/login", methods=["GET", "POST"])
def _mobile_login():
    log_line(f"LOGIN2015 {request.method} Q={request.query_string.decode()[:80]} BODY={request.get_data()[:120]}")
    return jsonify({"data": {"UserID": 10000063, "UserName": "Rzim", "SessionKey": "rzim-session-key", "IsLoggedIn": True, "Status": "Success"}})

@app.route("/mobileapi/userinfo", methods=["GET", "POST"])
@app.route("/mobileapi/userinfo/", methods=["GET", "POST"])
def _mobile_userinfo():
    log_line(f"USERINFO2015 {request.path}")
    return jsonify({"data": {"UserID": 10000063, "UserName": "Rzim", "IsPremium": False}})

@app.route("/mobileapi/logout", methods=["GET", "POST"])
def _mobile_logout():
    log_line("LOGOUT2015")
    return jsonify({"data": {"Status": "Success"}})

@app.route("/mobileapi/securesignup", methods=["GET", "POST"])
def _mobile_signup():
    log_line(f"SIGNUP2015 BODY={request.get_data()[:120]}")
    return jsonify({"data": {"UserID": 10000063, "UserName": "Rzim", "SessionKey": "rzim-session-key", "Status": "Success"}})

@app.route("/game/<path:file>", methods=["GET"])
@app.route("/Game/<path:file>", methods=["GET"])
def _game_file(file):
    log_line(f"GET Game/{file} Q={request.query_string.decode()[:100]}")
    if file == "ClientPresence.ashx":
        return Response("", status=200)
    if file == "GetCurrentUser.ashx":
        return Response("null", status=200, mimetype="text/plain")
    if file == "logout.ashx":
        return Response("", status=200)
    fp = os.path.join(STORAGE, os.path.basename(file))
    if os.path.exists(fp):
        with open(fp, "r") as f:
            return Response(f.read(), status=200, mimetype="text/plain")
    return Response("", status=404)

@app.route("/game/visit.ashx", methods=["GET"])
@app.route("/Game/Visit.ashx", methods=["GET"])
@app.route("/game/Visit.ashx", methods=["GET"])
@app.route("/Game/visit.ashx", methods=["GET"])
def _visit():
    log_line(f"GET {request.path} Q={request.query_string.decode()[:120]}")
    with open(os.path.join(STORAGE, "visit.ashx"), "r") as f:
        return Response(f.read(), status=200, mimetype="text/plain")

def _fetch_asset_url(aid):
    cookie = os.environ.get("RBX_COOKIE", "").strip()
    urls = [
        f"https://assetdelivery.roblox.com/v2/assetId/{aid}?protocol=https",
        f"https://assetdelivery.roblox.com/v1/asset/?id={aid}&protocol=https",
    ]
    for base in urls:
        req = urllib.request.Request(base, headers={"User-Agent": "Roblox/WinInet; RobloxStudio/2015"})
        if cookie:
            req.add_header("Cookie", f".ROBLOSECURITY={cookie}")
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                out = json.load(r)
            if "locations" in out and out["locations"]:
                return out["locations"][0]["location"]
        except Exception as e:
            log_line(f"ASSET2015 try {base[:60]} ERRO {e}")
    return None

@app.route("/asset/", methods=["GET"])
@app.route("/Asset/", methods=["GET"])
@app.route("/asset", methods=["GET"])
@app.route("/Asset", methods=["GET"])
def _asset():
    aid = request.args.get("id", "")
    log_line(f"ASSET2015 id={aid} path={request.path}")
    url = _fetch_asset_url(aid)
    if url:
        return redirect(url, code=302)
    return jsonify({"error": "asset requires auth (defina RBX_COOKIE)"}), 401

@app.route("/Asset/CharacterFetch.ashx", methods=["GET"])
def _charfetch():
    return Response("http://www.roblox.com/Asset/BodyColors.ashx?userId=1;http://www.roblox.com/Asset/?versionid=21351761",
                   status=200, mimetype="text/plain")

@app.route("/Asset/BodyColors.ashx", methods=["GET"])
def _bodycolors():
    fp = os.path.join(STORAGE, "BodyColors.ashx")
    if os.path.exists(fp):
        with open(fp, "r") as f:
            return Response(f.read(), status=200, mimetype="text/plain")
    return Response("", status=404)

@app.route("/Error/Lua.ashx", methods=["GET"])
@app.route("/Error/Dmp.ashx", methods=["GET"])
def _error_sink():
    return Response("Thx", status=200, mimetype="text/plain")

@app.route("/Game/Wipeouts.ashx", methods=["GET"])
def _wipeouts():
    uid = request.args.get("UserID", "0")
    s = _score.setdefault(uid, {"Wipeouts": 0, "Knockouts": 0})
    s["Wipeouts"] += 1
    return jsonify({"status": "online"})

@app.route("/Game/Knockouts.ashx", methods=["GET"])
def _knockouts():
    uid = request.args.get("UserID", "0")
    s = _score.setdefault(uid, {"Wipeouts": 0, "Knockouts": 0})
    s["Knockouts"] += 1
    return jsonify({"status": "online"})
