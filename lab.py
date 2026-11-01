# -*- coding: utf-8 -*-
"""
MONTROY LAB - alvo de treino.
Sistema ficticio (Banco Aurora) com falhas de proposito para estudo.
Tudo em memoria: nenhum dado real, nenhum comando real executado.
"""
import base64
import os
import random
import re
import urllib.parse

from flask import Flask, request, make_response, redirect

app = Flask(__name__)

# ---------------------------------------------------------------- dados
USUARIOS = [
    {"id": 1, "email": "admin@aurora.local", "senha": "Aurora@2026", "nome": "Rita Alencar",
     "papel": "admin", "segredo": "cofre 12 / PIN de 4 digitos na API /api/pin"},
    {"id": 2, "email": "brayan@aurora.local", "senha": "senha123", "nome": "Brayan Borges",
     "papel": "user", "segredo": "saldo 2.400 / limite 5.000"},
    {"id": 3, "email": "carla@aurora.local", "senha": "carla2026", "nome": "Carla Nunes",
     "papel": "user", "segredo": "conta em analise"},
]

ARQUIVOS = {
    "publico/aviso.txt": "Manutencao programada domingo 03h.",
    "publico/termos.txt": "Termos de uso do Banco Aurora (ficticio).",
    "privado/segredo.txt": "MONTROY{tr4v3rs4l_d3_p4st4}",
}

PIN = "7391"
API_KEY = "aurora_live_9f3a77c1d2"


# ---------------------------------------------------------------- mini SQL
def _cond(row, expr):
    """Avalia condicao simples: campo = 'valor' ou 'x' = 'y' (inclusive literal = literal)."""
    expr = expr.strip()
    m = re.match(r"^([\w.]+|'[^']*')\s*=\s*(.+)$", expr)
    if not m:
        return False

    def limpa(t):
        t = t.strip()
        if len(t) >= 2 and t[0] == "'" and t[-1] == "'":
            return t[1:-1]
        return t

    esq = m.group(1).strip()
    dir_ = limpa(m.group(2))
    if not esq.startswith("'") and esq in row:
        return str(row[esq]) == dir_
    return limpa(esq) == dir_


def run_sql(q):
    """Interpretador minimo de SELECT ... WHERE (vulneravel de proposito)."""
    q = q.strip()
    m = re.match(r"^select\s+(.+?)\s+from\s+(\w+)(?:\s+where\s+(.+))?$", q, re.I | re.S)
    if not m:
        return None, "erro de sintaxe perto de %r" % q[:40]
    cols, tabela, where = m.group(1), m.group(2).lower(), m.group(3)

    tabela_map = {"usuarios": USUARIOS}
    if tabela not in tabela_map:
        return None, "tabela %s nao existe" % tabela
    linhas = tabela_map[tabela]

    if where:
        where = where.split("--")[0].strip()
        # OR tem precedencia de avaliacao aqui (suficiente para a aula)
        grupos = re.split(r"\s+or\s+", where, flags=re.I)
        filtradas = []
        for row in linhas:
            ok = False
            for g in grupos:
                ands = re.split(r"\s+and\s+", g, flags=re.I)
                if all(_cond(row, a) for a in ands):
                    ok = True
                    break
            if ok:
                filtradas.append(row)
        linhas = filtradas

    sel = [c.strip() for c in cols.split(",")]
    if sel == ["*"]:
        out = [dict(r) for r in linhas]
    else:
        out = [{c: r.get(c) for c in sel} for r in linhas]
    return out, None


# ---------------------------------------------------------------- layout
CSS = """
*{box-sizing:border-box}
body{margin:0;background:#0d0d10;color:#e8e8ec;font:15px/1.55 -apple-system,Segoe UI,Roboto,sans-serif}
a{color:#ff6b4a}
.wrap{max-width:900px;margin:0 auto;padding:18px 14px 60px}
header{border-bottom:1px solid #24242c;padding:14px 0;margin-bottom:18px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.logo{font-weight:800;letter-spacing:1.5px;color:#ff6b4a}
.tag{font-size:11px;border:1px solid #3a3a46;color:#9a9aa8;padding:2px 7px;border-radius:99px}
h1{font-size:22px;margin:14px 0 6px}
h2{font-size:17px;margin:22px 0 8px}
p,li{color:#c9c9d4}
code,pre{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
code{background:#17171d;border:1px solid #26262f;padding:1px 6px;border-radius:5px;font-size:13px;color:#ffd9a0}
pre{background:#12121a;border:1px solid #26262f;padding:12px;border-radius:10px;overflow:auto;font-size:13px;color:#d5d5e0}
.card{background:#121218;border:1px solid #24242c;border-radius:14px;padding:14px 16px;margin:12px 0}
.card.ok{border-color:#2f6b45;background:#0f1a14}
.dica{background:#151a22;border-left:3px solid #4a7dff;padding:10px 12px;border-radius:8px;margin:8px 0;font-size:14px}
.missao{display:flex;gap:10px;align-items:flex-start}
.num{width:26px;height:26px;flex:0 0 26px;border-radius:8px;background:#ff6b4a;color:#12121a;font-weight:800;display:flex;align-items:center;justify-content:center;font-size:13px}
button{background:#ff6b4a;color:#12121a;border:0;padding:9px 14px;border-radius:9px;font-weight:700;font-size:14px;cursor:pointer}
button.ghost{background:#1c1c24;color:#c9c9d4;border:1px solid #2c2c36}
input{background:#0f0f14;border:1px solid #2c2c36;color:#e8e8ec;padding:9px 11px;border-radius:9px;font-size:14px;width:100%}
.row{display:flex;gap:8px;flex-wrap:wrap}
.flags{font-size:12px;color:#8b8b99}
.warn{background:#241012;border:1px solid #5a2228;color:#ffb3b3;padding:10px 12px;border-radius:10px;font-size:13px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{border-bottom:1px solid #24242c;padding:7px 6px;text-align:left}
th{color:#9a9aa8;font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.5px}
footer{margin-top:30px;border-top:1px solid #24242c;padding-top:14px;font-size:12px;color:#7a7a88}

.topo{text-align:center;margin:6px 0 14px}
.marca{font-weight:900;letter-spacing:2px;font-size:20px;color:#ff6b4a}
.marca span{color:#e8e8ec}
.sub{font-size:12px;color:#8b8b99;letter-spacing:1px;text-transform:uppercase}
.aviso{background:#141821;border:1px solid #2a3242;border-radius:12px;padding:12px 14px;font-size:14px;color:#c9c9d4;margin:10px 0}
.placar{position:sticky;top:0;z-index:5;background:#0d0d10;border-bottom:1px solid #24242c;padding:10px 0;text-align:center;font-weight:700;color:#5fd08a;font-size:14px}
.cartao{background:#121218;border:1px solid #24242c;border-radius:14px;padding:14px 16px;margin:14px 0}
.titulo{font-weight:800;font-size:17px;margin-bottom:6px}
.ideia{color:#b9b9c6;font-size:14px;margin:6px 0 12px}
.passo{border-top:1px dashed #26262f;padding-top:10px;margin-top:10px}
.ptxt{font-size:14px;margin-bottom:8px}
.btn{width:100%;margin-bottom:8px}
.out{display:none;white-space:pre-wrap;background:#0b0b10;border:1px solid #26262f;border-radius:10px;padding:10px;font-size:12.5px;color:#d5d5e0;margin:0}
.out.bom{border-color:#2f6b45;background:#0e1712;color:#bdf0cf}
.ok{background:#0f1a14;border:1px solid #2f6b45;color:#bdf0cf;border-radius:10px;padding:10px 12px;font-size:14px;margin-top:10px}
.dic{font-size:14px;padding-left:18px}
.dic li{margin:6px 0}
.rodape{text-align:center;margin:28px 0 10px;font-size:13px}
"""

MISSOES = [
    {
        "id": "sql", "titulo": "Entrar sem senha",
        "alvo": "POST /entrar",
        "resumo": "O login monta a consulta colando o que voce digita. Veja se da para virar a pergunta contra o sistema.",
        "dicas": [
            "O servidor monta: SELECT ... WHERE email = '<seu texto>' AND senha = '<seu texto>'.",
            "Se voce fechar a aspa e escrever uma condicao que e sempre verdadeira, o AND inteiro deixa de importar.",
            "Tente no campo email: <code>' OR '1'='1' --</code> e qualquer senha. O <code>--</code> comenta o resto.",
            "Furou? Entao o sistema acreditou em voce sem conferir a senha. O erro e concatenar texto na consulta em vez de usar parametros (<code>?</code>).",
        ],
        "fix": "cursor.execute('SELECT id, nome, papel FROM usuarios WHERE email = ? AND senha = ?', (email, senha))",
    },
    {
        "id": "idor", "titulo": "Ler a conta do vizinho",
        "alvo": "GET /conta?id=2",
        "resumo": "Sua conta e a 2. O sistema mostra a conta 1 se voce pedir? Ele checa se a conta e sua?",
        "dicas": [
            "Olhe a URL da sua pagina de conta. Tem um numero ali. Tente trocar.",
            "Nada impede voce de pedir outro id: o servidor nao compara com quem esta logado.",
            "Acesse <code>/conta?id=1</code>: e o admin, e a ficha dele traz a flag.",
            "Falha classica: IDOR. A correcao e autorizar por recurso, nao so autenticar: se o id pedido != id da sessao e o usuario nao e admin, negue.",
        ],
        "fix": "if pedido_id != sessao['usuario_id'] and sessao['papel'] != 'admin': abort(403)",
    },
    {
        "id": "admin", "titulo": "Virar admin",
        "alvo": "GET /admin",
        "resumo": "O papel do usuario vem num cookie que voce pode editar. O servidor confia nele?",
        "dicas": [
            "Depois de entrar, olhe os cookies da pagina (no navegador ou com o print do servidor).",
            "O cookie <code>acesso</code> guarda <code>papel=user</code> codificado em base64. Base64 nao e criptografia.",
            "Monte <code>papel=admin</code>, codifique em base64 e mande no cookie <code>acesso</code>. Da para fazer no proprio navegador ou com um comando.",
            "Deu certo porque o cliente decide o proprio nivel de acesso. Nunca confie em dado que o usuario controla: guarde o papel no servidor e assine o cookie (ou use sessao).",
        ],
        "fix": "papel = db.usuarios[sessao['id']]['papel']  # sempre do servidor",
    },
    {
        "id": "traversal", "titulo": "Sair da pasta",
        "alvo": "GET /arquivos?nome=publico/aviso.txt",
        "resumo": "O leitor de arquivos aceita um caminho. Ele aceita tambem caminho que sobe pastas?",
        "dicas": [
            "O parametro <code>nome</code> vai direto para o leitor de arquivos, sem limpeza.",
            "Para subir de pasta em caminho relativo usa-se <code>..</code>.",
            "Peca <code>/arquivos?nome=../privado/segredo.txt</code> ou <code>../segredo.txt</code>.",
            "E path traversal. Correcao: resolver o caminho e conferir se ele continua dentro da pasta permitida (<code>os.path.realpath</code> + <code>startswith</code>).",
        ],
        "fix": "alvo = os.path.realpath(os.path.join(BASE, nome))\nif not alvo.startswith(os.path.realpath(BASE)): abort(403)",
    },
    {
        "id": "xss", "titulo": "Fazer a pagina executar o que voce escreve",
        "alvo": "GET /busca?q=...",
        "resumo": "A busca devolve o que voce digitou. Ela devolve escapado ou cru?",
        "dicas": [
            "Digite algo com <code><b>teste</b></code> na busca e veja se o negrito aparece.",
            "Se aparece formatado, o servidor nao escapa HTML: da para injetar <code><script></code>.",
            "Mande <code>/busca?q=<script>alert(1)</script></code>. O laudo aparece com a flag.",
            "Isso e XSS refletido. Correcao: escapar saida (<code>{{ q }}</code> no Jinja ja escapa) e usar cabeçalhos de CSP.",
        ],
        "fix": "return render_template('busca.html', q=q)  # Jinja escapa por padrao",
    },
    {
        "id": "chave", "titulo": "Achar a chave escondida",
        "alvo": "GET /api/saldo?key=...",
        "resumo": "A API de saldo pede uma chave. Desenvolvedor esquecido deixou ela em algum lugar do site.",
        "dicas": [
            "Procure em arquivos que o site entrega: script, comentario no HTML, fonte.",
            "Os scripts do site sao servidos por <code>/static/app.js</code>.",
            "La tem um comentario com <code>aurora_live_...</code>. Use: <code>/api/saldo?key=aurora_live_9f3a77c1d2</code>.",
            "Segredo no codigo do cliente e segredo publico. Chave de API fica no servidor, em variavel de ambiente, e com escopo minimo.",
        ],
        "fix": "CHAVE = os.environ['AURORA_KEY']  # nunca no JS do cliente",
    },
    {
        "id": "pin", "titulo": "Descobrir o PIN",
        "alvo": "GET /api/pin?p=0000",
        "resumo": "Um PIN de 4 digitos protege o cofre. Tem limite de tentativas?",
        "dicas": [
            "Nao tem limite, nao tem atraso, nao tem bloqueio. 10 mil combinacoes.",
            "Dispare em laco: mil tentativas levam segundos por HTTP.",
            "Teste alguns e veja que a resposta nunca muda de comportamento. Encontre o certo e a flag aparece.",
            "E forca bruta por ausencia de rate limit. Correcao: limite por IP e por conta, atraso progressivo, bloqueio e MFA.",
        ],
        "fix": "if tentativas[ip] > 5: return 429  # + atraso progressivo + MFA",
    },
    {
        "id": "cmd", "titulo": "Injetar no diagnostico",
        "alvo": "GET /diagnostico?host=127.0.0.1",
        "resumo": "Uma ferramenta de ping aceita um host. E se voce colar mais de um comando? (aqui e simulado: nenhum comando roda de verdade)",
        "dicas": [
            "O servidor monta algo como: ping -c1 <host>.",
            "Em shell, <code>;</code> separa comandos. Tudo depois tambem seria executado.",
            "Peca <code>/diagnostico?host=127.0.0.1;id</code> (ou com <code>|</code> ou <code>&amp;&amp;</code>). A resposta simulada mostra a flag.",
            "E command injection. Correcao: nunca montar linha de shell com entrada do usuario; use lista de argumentos e valide o host (regex de IP/hostname).",
        ],
        "fix": "subprocess.run(['ping','-c','1',host], shell=False)  # + validar host",
    },
]

FLAGS = {
    "sql": "MONTROY{sql_1nj3ct4d0_no_l0g1n}",
    "idor": "MONTROY{1d0r_l31tura_d3_c0nt4}",
    "admin": "MONTROY{c00k13_f0rj4d0_p4p3l}",
    "traversal": "MONTROY{tr4v3rs4l_d3_p4st4}",
    "xss": "MONTROY{xss_r3fl3t1d0}",
    "chave": "MONTROY{ch4v3_n0_j4v4scr1pt}",
    "pin": "MONTROY{p1n_d3_4_d1g1t0s}",
    "cmd": "MONTROY{c0mm4nd_1nj3ct10n}",
}


@app.after_request
def cabecalhos(r):
    r.headers["X-Lab"] = "MONTROY treino isolado"
    return r


def pagina(corpo, status=200):
    return make_response(corpo, status)


def shell(titulo, corpo, extra=""):
    return """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%s · MONTROY LAB</title><style>%s</style></head><body><div class="wrap">
<header><span class="logo">MONTROY</span><span class="tag">LAB</span>
<span class="tag">sistema ficticio</span><span class="tag">treino isolado</span>
<a href="/" style="margin-left:auto;font-size:13px">inicio</a></header>
%s
<footer>Banco Aurora e ficticio. Nenhum comando real e executado. Feito para estudar: achar a falha, entender e saber corrigir.</footer>
</div></body></html>""" % (titulo, CSS, corpo + extra)


# ---------------------------------------------------------------- home
def home_html():
    cards = []
    for i, m in enumerate(MISSOES, 1):
        cards.append("""<div class="card"><div class="missao"><div class="num">%d</div><div style="flex:1">
<div style="font-weight:700">%s</div>
<div class="flags" style="margin:2px 0 6px">alvo: <code>%s</code></div>
<div style="font-size:14px;color:#a8a8b6">%s</div>
</div></div></div>""" % (i, m["titulo"], m["alvo"], m["resumo"]))
    return shell("inicio", """
<h1>Alvo: Banco Aurora</h1>
<p>Sistema interno ficticio com 8 falhas reais. Seu trabalho e achar cada uma, entender por que ela existe e saber como se conserta.</p>
<div class="warn">Isto e um laboratorio. Tudo roda em memoria, com dados inventados, no meu proprio servidor. A mesma tecnica usada em sistema de terceiros sem permissao e crime.</div>

<h2>Missoes</h2>
%s

<h2>Seu placar</h2>
<div class="card"><div id="placar">carregando...</div>
<div class="row" style="margin-top:10px">
<input id="flag" placeholder="cole uma flag MONTROY{...} aqui">
<button onclick="validar()">Validar</button>
</div><div id="res" style="margin-top:8px;font-size:14px"></div></div>

<h2>Quadro de dicas</h2>
<div id="dicas"></div>

<script>
var MISSOES = %s;
var chave = 'montroy_lab_flags';
var feitas = JSON.parse(localStorage.getItem(chave) || '[]');

function placar(){
  document.getElementById('placar').textContent = feitas.length + ' de ' + MISSOES.length + ' missoes resolvidas';
}

function dicasHTML(){
  var h = '';
  MISSOES.forEach(function(m, i){
    var aberta = feitas.indexOf(m.id) >= 0;
    h += '<div class="card"><div style="font-weight:700">' + (i+1) + '. ' + m.titulo + (aberta ? ' <span style="color:#5fd08a">✔</span>' : '') + '</div>';
    h += '<div class="flags">alvo: <code>' + m.alvo + '</code></div>';
    h += '<div id="d_' + m.id + '"></div>';
    h += '<div class="row" style="margin-top:8px"><button class="ghost" onclick="maisDica(\\'' + m.id + '\\')">ver dica</button>';
    if (aberta) h += '<button class="ghost" onclick="verFix(\\'' + m.id + '\\')">como corrigir</button>';
    h += '</div><div id="f_' + m.id + '"></div></div>';
  });
  document.getElementById('dicas').innerHTML = h;
  dicasCont = {}; MISSOES.forEach(function(m){ dicasCont[m.id] = 0; });
}

var dicasCont = {};
function maisDica(id){
  var m = MISSOES.filter(function(x){return x.id===id;})[0];
  if (!m) return;
  var n = dicasCont[id] || 0;
  if (n >= m.dicas.length){ return; }
  dicasCont[id] = n + 1;
  var box = document.getElementById('d_' + id);
  var p = document.createElement('div');
  p.className = 'dica'; p.innerHTML = '<b>Dica ' + (n+1) + ':</b> ' + m.dicas[n];
  box.appendChild(p);
}

function verFix(id){
  var m = MISSOES.filter(function(x){return x.id===id;})[0];
  document.getElementById('f_' + id).innerHTML = '<pre>' + m.fix.replace(/</g,'&lt;') + '</pre>';
}

function validar(){
  var f = document.getElementById('flag').value.trim();
  var r = document.getElementById('res');
  fetch('/validar?f=' + encodeURIComponent(f)).then(function(x){return x.json();}).then(function(d){
    if (d.ok){
      if (feitas.indexOf(d.id) < 0) feitas.push(d.id);
      localStorage.setItem(chave, JSON.stringify(feitas));
      placar(); dicasHTML();
      r.innerHTML = '<span style="color:#5fd08a">Isso! ' + d.titulo + '. ' + d.explica + '</span>';
    } else {
      r.innerHTML = '<span style="color:#ff8a8a">' + (d.msg || 'flag nao confere') + '</span>';
    }
  });
}
placar(); dicasHTML();
</script>
""" % ("".join(cards),
       __import__("json").dumps(MISSOES, ensure_ascii=False).replace("</", "<\\/")))


# ==========================================================
# MODO GUIADO (iniciante): cada missao vira passo a passo
# ==========================================================

GUIADAS = [
    {
        "id": 1, "nome": "Entrar sem a senha",
        "ideia": "O site monta a pergunta do banco colando o que voce digita. Se voce digitar um pedaco da pergunta, ela muda de sentido.",
        "passos": [
            ("Tentar entrar com senha errada (o normal).", "login_errado"),
            ("Agora digitar um pedaco de comando no e-mail.", "login_sqli"),
        ],
        "explica": "Isso e injecao de SQL. O texto digitado virou parte do comando do banco, e a condicao virou sempre verdadeira. Correcao: consulta parametrizada, onde o dado nunca vira comando.",
    },
    {
        "id": 2, "nome": "Ver a conta de outra pessoa",
        "ideia": "A pagina da conta recebe o numero pelo endereco (?id=2). Se o servidor nao confere de quem e aquela conta, voce troca o numero.",
        "passos": [
            ("Abrir a SUA conta (id=2).", "conta_propria"),
            ("Trocar o numero para a conta do admin (id=1).", "conta_vizinho"),
        ],
        "explica": "Isso e IDOR: trocar o identificador na URL e ver dado de outro. O servidor precisa comparar o id pedido com o usuario logado.",
    },
    {
        "id": 3, "nome": "Virar administrador",
        "ideia": "O site guarda seu papel (usuario ou admin) num cookie, e base64 nao e protecao: qualquer um le e reescreve.",
        "passos": [
            ("Tentar abrir a area admin sem permissao.", "admin_sem"),
            ("Editar o cookie e mandar de novo.", "admin_com"),
        ],
        "explica": "Controle de acesso feito no cliente nao existe. O papel deve ser decidido no servidor, com sessao assinada.",
    },
    {
        "id": 4, "nome": "Ler arquivo fora da pasta",
        "ideia": "O leitor de arquivos junta a pasta base com o nome que voce manda. Se o nome tiver ../ ele sobe uma pasta.",
        "passos": [
            ("Ler um arquivo publico normal.", "arq_publico"),
            ("Subir de pasta com ../ e ler o segredo.", "arq_traversal"),
        ],
        "explica": "Isso e path traversal. Correcao: normalizar o caminho e conferir se ele continua dentro da pasta permitida.",
    },
    {
        "id": 5, "nome": "Fazer a busca executar codigo",
        "ideia": "A pagina devolve o que voce digitou sem tratar. Se todos tratassem o texto como texto, isso nao aconteceria.",
        "passos": [
            ("Buscar uma palavra normal.", "busca_normal"),
            ("Buscar com um pedaco de HTML/script.", "busca_xss"),
        ],
        "explica": "XSS refletido: o navegador de quem abrir o link roda o que voce escreveu. Correcao: escapar a saida.",
    },
    {
        "id": 6, "nome": "Achar a chave escondida",
        "ideia": "Tudo que vai para o navegador pode ser lido. Chave de API no arquivo do site e chave entregue.",
        "passos": [
            ("Abrir o arquivo de script do site.", "ver_js"),
            ("Usar a chave achada nele.", "usar_chave"),
        ],
        "explica": "Segredo no cliente nao e segredo. Chave de servidor fica no servidor, com permissao minima e rotacao.",
    },
    {
        "id": 7, "nome": "Descobrir o PIN",
        "ideia": "Sao 10 mil combinacoes. Se o site aceita tentar sem limite e sem esperar, o computador acha rapido.",
        "passos": [
            ("Tentar um PIN qualquer.", "pin_errado"),
            ("Tentar todos ate achar (o servidor faz o laco).", "pin_bruto"),
        ],
        "explica": "Forca bruta por falta de rate limit. Correcao: limite por IP e por conta, atraso progressivo, bloqueio e MFA.",
    },
    {
        "id": 8, "nome": "Mandar comando pelo diagnostico",
        "ideia": "O site monta um comando de terminal com o texto que voce manda. ; e | encadeiam outro comando.",
        "passos": [
            ("Rodar o diagnostico normal.", "diag_normal"),
            ("Encadear outro comando com ;id.", "diag_injecao"),
        ],
        "explica": "Injecao de comando. Aqui o terminal e simulado, nada roda de verdade. Correcao: nunca montar comando com texto do usuario, usar lista de argumentos fixa.",
    },
]


def _resp_txt(metodo, caminho, status, corpo):
    return "%s %s\n%d %s\n%s" % (metodo, caminho, status, "OK" if status == 200 else ("FORBIDDEN" if status == 403 else "ERRO"), corpo)


def _user(uid):
    for u in USUARIOS:
        if u["id"] == uid:
            return u
    return None


def executar_passo(m, p):
    """Executa a acao do passo e devolve dict com saida, sucesso e flag."""
    par = GUIADAS[m - 1]["passos"][p - 1][1]

    if par == "login_errado":
        q = "SELECT id, nome, papel FROM usuarios WHERE email = 'brayan@aurora.local' AND senha = 'chute'"
        linhas, _err = run_sql(q)
        return {"saida": _resp_txt("POST", "/entrar", 200, "Acesso negado. E-mail ou senha invalidos." if not linhas else "entrou"),
                "ok": False, "consulta": q}

    if par == "login_sqli":
        em = "' OR '1'='1' --"
        q = "SELECT id, nome, papel FROM usuarios WHERE email = '%s' AND senha = 'chute'" % em
        linhas, _err = run_sql(q)
        if linhas:
            return {"saida": _resp_txt("POST", "/entrar", 200,
                    "Entrou como: %s (papel: %s)\nflag: %s" % (linhas[0].get("nome"), linhas[0].get("papel"), FLAGS["sql"])),
                    "ok": True, "consulta": q}
        return {"saida": "nao entrou", "ok": False, "consulta": q}

    if par == "conta_propria":
        u = _user(2)
        return {"saida": _resp_txt("GET", "/conta?id=2", 200, "%s | %s\nnota: %s" % (u["nome"], u["email"], u["segredo"])), "ok": False}

    if par == "conta_vizinho":
        u = _user(1)
        return {"saida": _resp_txt("GET", "/conta?id=1", 200,
                "%s | %s\nnota privada: %s\nflag: %s" % (u["nome"], u["email"], u["segredo"], FLAGS["idor"])),
                "ok": True}

    if par == "admin_sem":
        return {"saida": _resp_txt("GET", "/admin", 403, "Acesso negado: papel atual = usuario"), "ok": False}

    if par == "admin_com":
        ck = base64.b64encode(b"papel=admin&id=1").decode()
        return {"saida": _resp_txt("GET", "/admin", 200,
                "cookie enviado: acesso=%s\nBem-vindo, admin. Chave do cofre: %s" % (ck, FLAGS["admin"])), "ok": True}

    if par == "arq_publico":
        return {"saida": _resp_txt("GET", "/arquivos?nome=publico/aviso.txt", 200, ARQUIVOS["publico/aviso.txt"]), "ok": False}

    if par == "arq_traversal":
        return {"saida": _resp_txt("GET", "/arquivos?nome=../privado/segredo.txt", 200,
                "/var/aurora/publico/../privado/segredo.txt\n" + ARQUIVOS["privado/segredo.txt"] + "\nflag: " + FLAGS["traversal"]), "ok": True}

    if par == "busca_normal":
        return {"saida": _resp_txt("GET", "/busca?q=empréstimo", 200, "resultados para: emprestimo (2 itens)"), "ok": False}

    if par == "busca_xss":
        return {"saida": _resp_txt("GET", "/busca?q=<script>alert(1)</script>", 200,
                "resultados para: <script>alert(1)</script>\n(o navegador de quem abre o link executa isso)\nflag: " + FLAGS["xss"]), "ok": True}

    if par == "ver_js":
        trecho = '// app.js do Banco Aurora\nvar API_KEY = "%s";\nfunction saldo(){ fetch("/api/saldo?key=" + API_KEY) }' % API_KEY
        return {"saida": _resp_txt("GET", "/static/app.js", 200, trecho), "ok": False}

    if par == "usar_chave":
        return {"saida": _resp_txt("GET", "/api/saldo?key=" + API_KEY, 200,
                '{"conta":"aurora-master","saldo":987654321.0}\nflag: ' + FLAGS["chave"]), "ok": True}

    if par == "pin_errado":
        return {"saida": _resp_txt("GET", "/api/pin?p=0000", 200, '{"ok":false,"msg":"pin errado"}'), "ok": False}

    if par == "pin_bruto":
        achou = None
        for i in range(10000):
            cand = "%04d" % i
            if cand == PIN:
                achou = (i + 1, cand)
                break
        return {"saida": _resp_txt("GET", "/api/pin?p=" + (achou[1] if achou else "----"), 200,
                '{"ok":true,"flag":"%s"}' % FLAGS["pin"]) + "\n(tentei %d vezes, sem bloqueio nenhum)" % achou[0], "ok": True}

    if par == "diag_normal":
        return {"saida": _resp_txt("GET", "/diagnostico?host=127.0.0.1", 200, "ping 127.0.0.1 -> 3 pacotes, 0 perda"), "ok": False}

    if par == "diag_injecao":
        return {"saida": _resp_txt("GET", "/diagnostico?host=127.0.0.1;id", 200,
                "ping 127.0.0.1 -> ok\nuid=0(root) gid=0(root)\nflag: " + FLAGS["cmd"] + "\n(terminal simulado: nada rodou de verdade)"), "ok": True}

    return {"saida": "passo desconhecido", "ok": False}


@app.route("/guia/executar")
def guia_executar():
    try:
        m = int(request.args.get("m", "1"))
        p = int(request.args.get("p", "1"))
    except ValueError:
        return {"erro": "parametros"}, 400
    if not (1 <= m <= len(GUIADAS)) or not (1 <= p <= len(GUIADAS[m - 1]["passos"])):
        return {"erro": "missao invalida"}, 404
    r = executar_passo(m, p)
    g = GUIADAS[m - 1]
    r["totalPassos"] = len(g["passos"])
    if r.get("ok"):
        r["explica"] = g["explica"]
    return r


def guia_html():
    cards = []
    for g in GUIADAS:
        passos = []
        for i, (txt, acao) in enumerate(g["passos"], 1):
            passos.append(
                '<div class="passo"><div class="ptxt">%d. %s</div>'
                '<button class="btn" onclick="rodar(%d,%d,this)">▶ Fazer esse passo</button>'
                '<pre class="out" id="o%d_%d"></pre></div>' % (i, txt, g["id"], i, g["id"], i)
            )
        cards.append(
            '<div class="cartao" id="m%d">'
            '<div class="titulo">Missao %d · %s</div>'
            '<p class="ideia">%s</p>'
            '%s'
            '<div class="fim" id="f%d"></div>'
            '</div>' % (g["id"], g["id"], g["nome"], g["ideia"], "".join(passos), g["id"])
        )

    corpo = """
<div class="topo">
  <div class="marca">MONTROY <span>LAB</span></div>
  <div class="sub">modo guiado · clique e veja acontecer</div>
</div>

<div class="aviso">
<strong>Como usar:</strong> leia a ideia da missao e va clicando nos botoes, do primeiro para o ultimo.
Cada botao faz uma coisa no sistema e mostra a resposta dele. Quando a resposta trouxer uma flag,
voce resolveu. Depois leia "por que funcionou".
</div>

<div id="placar" class="placar">0 de 8 resolvidas</div>

%s

<div class="cartao">
  <div class="titulo">Dicionario rapido</div>
  <p class="ideia">Se travar em alguma palavra, e aqui:</p>
  <ul class="dic">
    <li><strong>Requisicao</strong>: o pedido que o app manda pro servidor (GET le, POST envia).</li>
    <li><strong>URL</strong>: o endereco do pedido; o que vem depois de ? sao os dados (ex: ?id=2).</li>
    <li><strong>Cookie</strong>: bilhete que o site guarda no seu navegador e voce pode editar.</li>
    <li><strong>Banco de dados</strong>: tabelas com linhas; o site pergunta em SQL.</li>
    <li><strong>SQL</strong>: a lingua das perguntas ao banco (SELECT ... WHERE ...).</li>
    <li><strong>Flag</strong>: prova de que voce chegou la, tipo MONTROY{...}.</li>
  </ul>
</div>

<div class="rodape">
  <a href="/livre">modo livre (sem passos, para quem ja sabe)</a>
</div>

<script>
var chave = 'montroy_guia';
var feitas = JSON.parse(localStorage.getItem(chave) || '[]');

function placar(){
  document.getElementById('placar').textContent = feitas.length + ' de 8 resolvidas';
}

function marcar(m){
  if (feitas.indexOf(m) < 0){ feitas.push(m); localStorage.setItem(chave, JSON.stringify(feitas)); placar(); }
}

function rodar(m, p, btn){
  var out = document.getElementById('o' + m + '_' + p);
  out.style.display = 'block';
  out.textContent = 'executando...';
  btn.disabled = true;
  fetch('/guia/executar?m=' + m + '&p=' + p).then(function(r){ return r.json(); }).then(function(d){
    out.textContent = d.saida || d.erro || 'sem resposta';
    out.className = 'out' + (d.ok ? ' bom' : '');
    btn.disabled = false;
    if (d.ok){
      marcar(m);
      var f = document.getElementById('f' + m);
      f.innerHTML = '<div class="ok">Resolveu essa. ' + (d.explica || '') + '</div>';
    }
  }).catch(function(e){
    out.textContent = 'erro: ' + e;
    btn.disabled = false;
  });
}

placar();
</script>
""" % ("".join(cards))

    return shell("modo guiado", corpo)


@app.route("/")
def index():
    return pagina(guia_html())


@app.route("/guia")
def guia():
    return pagina(guia_html())


@app.route("/livre")
def livre():
    return pagina(home_html())



@app.route("/validar")
def validar():
    f = (request.args.get("f") or "").strip()
    for mid, fl in FLAGS.items():
        if f == fl:
            m = [x for x in MISSOES if x["id"] == mid][0]
            return {"ok": True, "id": mid, "titulo": m["titulo"], "explica": m["dicas"][-1]}
    return {"ok": False, "msg": "flag nao confere (ainda)"}


# ---------------------------------------------------------------- alvo
@app.route("/entrar", methods=["GET", "POST"])
def entrar():
    if request.method == "GET":
        return pagina(shell("entrar", """
<h1>Entrar · Banco Aurora</h1>
<div class="card"><form method="post">
<p style="margin:0 0 6px;font-size:13px;color:#9a9aa8">e-mail</p>
<input name="email" placeholder="voce@aurora.local">
<p style="margin:10px 0 6px;font-size:13px;color:#9a9aa8">senha</p>
<input name="senha" type="text" placeholder="sua senha">
<div style="margin-top:12px"><button type="submit">Entrar</button></div>
</form></div>
<p class="flags">conta de teste: <code>brayan@aurora.local</code> / <code>senha123</code></p>
"""))
    email = request.form.get("email", "")
    senha = request.form.get("senha", "")
    # VULNERAVEL de proposito: concatenacao direta
    consulta = "SELECT id, nome, papel FROM usuarios WHERE email = '%s' AND senha = '%s'" % (email, senha)
    linhas, erro = run_sql(consulta)
    if erro:
        return pagina(shell("entrar", '<h1>Erro</h1><div class="card"><pre>%s</pre><pre>%s</pre></div>' % (consulta, erro)), 500)
    if not linhas:
        return pagina(shell("entrar", '<h1>Negado</h1><div class="card">usuario ou senha invalidos</div><p class="flags">consulta executada:</p><pre>%s</pre>' % consulta), 200)
    u = linhas[0]
    flag = ""
    original = next((x for x in USUARIOS if str(x["id"]) == str(u.get("id"))), None)
    if original and senha != original.get("senha"):
        flag = '<div class="card ok"><b>Flag:</b> <code>%s</code></div>' % FLAGS["sql"]
    corpo = """<h1>Bem-vindo, %s</h1>
<div class="card">id: <code>%s</code> · papel: <code>%s</code></div>
%s
<p class="flags">consulta que o servidor montou:</p><pre>%s</pre>
<p><a href="/conta?id=%s">minha conta</a></p>""" % (u.get("nome"), u.get("id"), u.get("papel"), flag, consulta, u.get("id"))
    r = pagina(shell("painel", corpo))
    r.set_cookie("acesso", base64.b64encode(("papel=user&id=%s" % u.get("id")).encode()).decode())
    return r


@app.route("/conta")
def conta():
    """IDOR: confia no id da URL."""
    try:
        cid = int(request.args.get("id", "2"))
    except ValueError:
        cid = 2
    u = next((x for x in USUARIOS if x["id"] == cid), None)
    if not u:
        return pagina(shell("conta", "<h1>conta nao encontrada</h1>"), 404)
    flag = ""
    if cid != 2:
        flag = '<div class="card ok"><b>Flag:</b> <code>%s</code></div>' % FLAGS["idor"]
    return pagina(shell("conta", """
<h1>Conta %s</h1>
<div class="card"><table>
<tr><th>id</th><td>%s</td></tr>
<tr><th>nome</th><td>%s</td></tr>
<tr><th>e-mail</th><td>%s</td></tr>
<tr><th>papel</th><td>%s</td></tr>
<tr><th>anotacao interna</th><td>%s</td></tr>
</table></div>%s
<p class="flags">voce esta logado como a conta 2.</p>""" % (u["id"], u["id"], u["nome"], u["email"], u["papel"], u["segredo"], flag)))


@app.route("/admin")
def admin():
    """Broken access control: papel vem do cookie do cliente."""
    raw = request.cookies.get("acesso", "")
    decoded = ""
    try:
        decoded = base64.b64decode(raw).decode("utf-8", "replace")
    except Exception:
        decoded = ""
    if "papel=admin" not in decoded:
        return pagina(shell("admin", """
<h1>Area administrativa</h1>
<div class="card">Acesso negado. O papel atual e lido do cookie <code>acesso</code>.</div>
<pre>acesso = %s
decodificado = %s</pre>
<p class="flags">dica: base64 nao e criptografia.</p>""" % (raw or "(vazio)", decoded or "(nada)")), 403)
    return pagina(shell("admin", """
<h1>Painel do administrador</h1>
<div class="card ok"><b>Flag:</b> <code>%s</code></div>
<div class="card"><table><tr><th>usuario</th><th>papel</th><th>segredo</th></tr>
%s</table></div>
<pre>acesso = %s</pre>""" % (FLAGS["admin"], "".join(
        "<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (u["email"], u["papel"], u["segredo"]) for u in USUARIOS), raw)))


@app.route("/arquivos")
def arquivos():
    nome = request.args.get("nome", "")
    if not nome:
        return pagina(shell("arquivos", """<h1>Arquivos</h1>
<div class="card">Documentos publicos:</div>
<pre>%s</pre>""" % "\n".join(ARQUIVOS.keys())))
    limpo = nome.replace("\\", "/")
    alvo = limpo
    while alvo.startswith("../"):
        alvo = alvo[3:]
    conteudo = ARQUIVOS.get(alvo) or ARQUIVOS.get(limpo)
    if conteudo is None:
        return pagina(shell("arquivos", "<h1>nao encontrado</h1><pre>%s</pre>" % limpo), 404)
    flag = ""
    if "../" in limpo:
        flag = '<div class="card ok"><b>Flag:</b> <code>%s</code></div>' % FLAGS["traversal"]
    return pagina(shell("arquivos", """<h1>%s</h1><div class="card"><pre>%s</pre></div>%s""" % (nome, conteudo, flag)))


@app.route("/busca")
def busca():
    q = request.args.get("q", "")
    cru = q  # VULNERAVEL: sem escapar
    flag = ""
    if re.search(r"<\s*script|onerror\s*=|onload\s*=", q, re.I):
        flag = '<div class="card ok"><b>Flag:</b> <code>%s</code></div>' % FLAGS["xss"]
    return pagina(shell("busca", """
<h1>Busca</h1>
<div class="card"><form><input name="q" value=""><div style="margin-top:8px"><button>Buscar</button></div></form></div>
<div class="card">Voce buscou por: %s</div>
<div class="card">Nenhum resultado para <b>%s</b>.</div>%s""" % (cru, cru, flag)))


@app.route("/api/saldo")
def api_saldo():
    key = request.args.get("key", "")
    if key != API_KEY:
        return {"erro": "chave invalida"}, 401
    return {"titular": "Rita Alencar", "saldo": 982340.55,
            "flag": FLAGS["chave"]}


@app.route("/static/app.js")
def static_js():
    # VULNERAVEL: segredo no codigo do cliente
    return pagina("""/* Banco Aurora - app v1.2.4
   TODO(dev): lembrar de tirar isso antes do release
   endpoint interno de saldo: /api/saldo?key=aurora_live_9f3a77c1d2
*/
console.log('aurora ok');
""", 200)


@app.route("/api/pin")
def api_pin():
    p = request.args.get("p", "")
    if p == PIN:
        return {"ok": True, "flag": FLAGS["pin"]}
    return {"ok": False, "msg": "pin errado"}


@app.route("/diagnostico")
def diagnostico():
    host = request.args.get("host", "")
    if not host:
        return pagina(shell("diag", """<h1>Diagnostico</h1>
<div class="card"><form><input name="host" placeholder="127.0.0.1"><div style="margin-top:8px"><button>Pingar</button></div></form></div>"""))
    simulado = "PING %s: 1 pacote, tempo 0.04ms\n1 recebido, 0 perdidos" % host
    for sep in (";", "|", "&&", "$("):
        if sep in host:
            simulado += "\n[simulado] aurora-internal:/# cat /flag\n" + FLAGS["cmd"]
            break
    return pagina(shell("diag", """<h1>Diagnostico</h1>
<div class="card"><pre>comando montado: ping -c1 %s\n\n%s</pre></div>
<p class="flags">Saida simulada. Nada e executado de verdade neste laboratorio.</p>""" % (host, simulado)))


@app.route("/health")
def health():
    return {"status": "online", "lab": "MONTROY", "missoes": len(MISSOES)}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8097)))
