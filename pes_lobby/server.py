# -*- coding: utf-8 -*-
"""
MONTROY PES LAB - servidor de lobby para estudo do eFootball/PES 4.6.2.

Objetivo: responder os endpoints descobertos no libUE4.so (32 bits) e
registrar tudo que o cliente pedir, para mapear o formato real das mensagens.

Endpoints mapeados no binario:
  /ntl/api/GateInfo.php                     (descoberta de servidor)
  /ntl/api/CmdLogin.php                     (login)
  /ntl/api/CmdCreateUser.php                (criacao de conta)
  /ntl/api/CmdGetServerEnv.php              (ambiente/manutencao)
  /ntl/api/CmdGetMaintenanceInfo.php
  ... mais 127 comandos Cmd*.php

Nada aqui e dado real de terceiros: tudo e resposta inventada para estudo.
"""
import json
import os
import threading
import time
from datetime import datetime

from flask import Flask, request, jsonify, make_response

app = Flask(__name__)

HOST_PUBLICO = os.environ.get("LOBBY_HOST", "127.0.0.1")
LOG_PATH = os.environ.get("LOG_PATH", "pes_requests.jsonl")
LOCK = threading.Lock()

# estado em memoria (some quando o servico reinicia)
USUARIOS = {}
SESSOES = {}
CONTADOR = {"total": 0, "por_rota": {}}


def registra(rota, corpo, headers):
    """Guarda toda requisicao: e o material que falta para o formato real."""
    with LOCK:
        CONTADOR["total"] += 1
        CONTADOR["por_rota"][rota] = CONTADOR["por_rota"].get(rota, 0) + 1
        item = {
            "hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "metodo": request.method,
            "rota": rota,
            "query": dict(request.args),
            "corpo": corpo[:4000],
            "ua": headers.get("User-Agent", "")[:120],
            "content_type": headers.get("Content-Type", ""),
        }
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return item


def corpo_texto():
    """O cliente as vezes manda JSON, as vezes form, as vezes binario."""
    try:
        if request.is_json:
            return json.dumps(request.get_json(silent=True) or {}, ensure_ascii=False)
        if request.form:
            return json.dumps(dict(request.form), ensure_ascii=False)
        return (request.get_data() or b"")[:6000].decode("latin-1")
    except Exception:
        return ""


def resposta(payload, status=200):
    r = make_response(json.dumps(payload, ensure_ascii=False), status)
    r.headers["Content-Type"] = "application/json; charset=utf-8"
    r.headers["Server"] = "MONTROY"
    return r


# ---------------------------------------------------------------- descoberta
@app.route("/ntl/api/GateInfo.php", methods=["GET", "POST"])
@app.route("/ntl/api/GateInfo.php/", methods=["GET", "POST"])
def gate_info():
    """
    O jogo chama isso primeiro para saber onde ficam os servidores.
    Formato real ainda nao capturado: devolvemos os campos que apareceram
    nas strings do binario (server_list, address, tls_port, nat_type...).
    """
    registra("/ntl/api/GateInfo.php", corpo_texto(), request.headers)
    return resposta({
        "result": 0,
        "server_list": [
            {
                "address": HOST_PUBLICO,
                "port": 443,
                "tls_port": 443,
                "region": "BR",
                "name": "MONTROY-LAB",
                "use_new_http": 1,
            }
        ],
        "turn_server_list": [],
        "nat_type": 1,
        "notification_url": "https://%s/ntl/api/CmdGetMaintenanceInfo.php" % HOST_PUBLICO,
        "server_certificate": "",
    })


# ---------------------------------------------------------------- comandos
@app.route("/ntl/api/<cmd>", methods=["GET", "POST"])
def comando(cmd):
    corpo = corpo_texto()
    registra("/ntl/api/" + cmd, corpo, request.headers)

    if cmd == "CmdLogin.php":
        dados = _json(corpo)
        uid = str(dados.get("uid") or dados.get("user_id") or "1000")
        token = "montroy-%s-%d" % (uid, int(time.time()))
        u = USUARIOS.setdefault(uid, {
            "uid": uid,
            "nick": dados.get("nick") or "Jogador",
            "nivel": 1,
            "gp": 100000,
            "moedas": 5000,
            "time_id": 1,
        })
        SESSOES[token] = uid
        return resposta({
            "result": 0,
            "session_id": token,
            "user": u,
            "server_time": int(time.time()),
            "maintenance": 0,
        })

    if cmd == "CmdCreateUser.php":
        dados = _json(corpo)
        uid = str(dados.get("uid") or len(USUARIOS) + 1000)
        USUARIOS[uid] = {
            "uid": uid,
            "nick": dados.get("nick") or "Jogador",
            "nivel": 1,
            "gp": 100000,
            "moedas": 5000,
            "time_id": 1,
        }
        return resposta({"result": 0, "user": USUARIOS[uid], "session_id": "montroy-%s" % uid})

    if cmd == "CmdGetServerEnv.php":
        return resposta({
            "result": 0,
            "maintenance": 0,
            "notice": "",
            "use_new_http": 1,
            "dl_low_bps": 0,
            "check_low_bps": 0,
            "intro_dl_timeout_sec": 60,
            "server_time": int(time.time()),
        })

    if cmd == "CmdGetMaintenanceInfo.php":
        return resposta({"result": 0, "maintenance": 0, "start": "", "end": "", "message": ""})

    if cmd == "CmdGetCountryList.php":
        return resposta({"result": 0, "countries": [{"code": "BR", "name": "Brazil"}]})

    if cmd == "CmdGetUserInfoList.php":
        return resposta({"result": 0, "users": list(USUARIOS.values())})

    if cmd == "CmdSendHeartbeat.php":
        return resposta({"result": 0, "server_time": int(time.time())})

    if cmd == "CmdGetPunchingData.php":
        return resposta({"result": 0, "address": HOST_PUBLICO, "port": 12100, "session_id": ""})

    if cmd == "CmdGetTurnServerList.php":
        return resposta({"result": 0, "turn_server_list": []})

    # qualquer outro dos 131 comandos: resposta neutra + registro
    return resposta({"result": 0, "data": {}, "echo": {"comando": cmd}})


def _json(corpo):
    try:
        return json.loads(corpo) if corpo else {}
    except Exception:
        return {}


# ---------------------------------------------------------------- painel
@app.route("/health")
def health():
    return resposta({"ok": True, "servico": "MONTROY PES LAB", "uptime": int(time.time())})


@app.route("/requests")
def requests_json():
    itens = []
    try:
        with open(LOG_PATH, encoding="utf-8") as f:
            itens = [json.loads(l) for l in f.readlines()[-200:]]
    except Exception:
        pass
    return resposta({"total": CONTADOR["total"], "por_rota": CONTADOR["por_rota"], "ultimos": itens})


@app.route("/")
def painel():
    return """<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MONTROY PES LAB</title>
<style>
body{margin:0;background:#0d0d10;color:#e8e8ec;font:15px/1.55 system-ui,sans-serif}
header{padding:18px 20px;border-bottom:1px solid #24242c;display:flex;align-items:center;gap:10px}
.logo{font-weight:800;letter-spacing:2px;font-size:19px}
.logo span{color:#ff6b4a}
.tag{font-size:12px;color:#8a8a99;border:1px solid #2a2a33;padding:2px 8px;border-radius:20px}
main{max-width:900px;margin:0 auto;padding:20px}
h2{font-size:15px;text-transform:uppercase;letter-spacing:1px;color:#9a9aa8}
pre{background:#141419;border:1px solid #24242c;border-radius:10px;padding:12px;overflow:auto;font-size:12.5px}
.k{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #1d1d24;font-size:14px}
.k b{color:#ff6b4a}
</style></head><body>
<header><div class="logo">MONTROY<span>·</span>PES LAB</div><div class="tag">lobby de estudo</div></header>
<main>
<h2>Resumo</h2><div id="resumo">carregando…</div>
<h2>Últimos pedidos do jogo</h2><pre id="log">carregando…</pre>
</main>
<script>
async function atualiza(){
  const d = await (await fetch('/requests')).json();
  document.getElementById('resumo').innerHTML =
    '<div class="k"><span>Requisições recebidas</span><b>'+d.total+'</b></div>' +
    Object.entries(d.por_rota).map(([k,v]) => '<div class="k"><span>'+k+'</span><b>'+v+'</b></div>').join('');
  document.getElementById('log').textContent =
    d.ultimos.slice(-15).map(x => x.hora+'  '+x.rota+'\\n'+(x.corpo ? '   '+x.corpo.slice(0,300) : '   (sem corpo)')).join('\\n\\n') || 'nada ainda';
}
atualiza(); setInterval(atualiza, 4000);
</script></body></html>"""


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8099)))
