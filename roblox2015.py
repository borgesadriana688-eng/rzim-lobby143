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

@app.route("/Setting/QuietGet/ClientSharedSettings", methods=["GET"])
@app.route("/Setting/QuietGet/ClientAppSettings", methods=["GET"])
def _settings_quiet():
    log_line(f"GET {request.path}")
    return jsonify({})

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

@app.route("/asset/", methods=["GET"])
@app.route("/Asset/", methods=["GET"])
@app.route("/asset", methods=["GET"])
@app.route("/Asset", methods=["GET"])
def _asset():
    aid = request.args.get("id", "")
    log_line(f"ASSET2015 id={aid} path={request.path}")
    try:
        req = urllib.request.Request(f"https://assetdelivery.roblox.com/v2/assetId/{aid}",
                                     headers={"User-Agent": "RobloxProxy/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            out = json.load(r)
        url = out["locations"][0]["location"]
        return redirect(url, code=302)
    except Exception as e:
        log_line(f"ASSET2015 ERRO {e}")
        return jsonify({"error": str(e)}), 502

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
