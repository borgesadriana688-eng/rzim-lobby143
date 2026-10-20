#!/usr/bin/env python3
# COMBINED WSGI v0.1 — FF2018 (Rzim) + Aisaka (Roblox 2.463) no MESMO servico Railway
# Dispatcher por prefixo de caminho: /v1/settings, /v2/settings, /auth, /chat, /friends,
# /thumbnails, /accountinformation, /accountsettings, /notifications, /translations,
# /locale, /clientsettings.api, /ecsv2, /metrics, /ephemeralcounters, /abtesting,
# /contacts -> aisaka_server; o resto (oauth, app, api, player, game, match, health,
# livever, crash, debug, v2.5...) -> freefire_server_v220 (ou o que estiver no FF_FILE).
import os, sys, traceback

FF_FILE = os.environ.get("FF_FILE", "freefire_server_v220.py")
PROXY_GAME_ENV = os.environ.get("PROXY_GAME") or ""

AISAKA_PREFIXES = (
    "/download", "/_upload", "/crash",
    "/v1/settings", "/v2/settings", "/clientsettings.api", "/auth", "/chat",
    "/friends", "/thumbnails", "/accountinformation", "/accountsettings",
    "/notifications", "/translations", "/locale", "/ecsv2", "/metrics",
    "/ephemeralcounters", "/abtesting", "/contacts", "/asset", "/v1/asset", "/mobile", "/v1.1",
    "/signup", "/v2/signup", "/_logs",
)

LOBBY_ROUTES = frozenset(['/Login', '/ChangeClothes', '/EPVideoAdPortal', '/GetAccountLifeSeasonStats', '/GetAccountSubscriptions', '/GetBackpack', '/GetBingoRewardsInfo', '/GetDailyRankingReward', '/GetDiscountStore', '/GetEPInfo', '/GetEPSubscriptionBonusStatus', '/GetExchangeStore', '/GetFollowStreamerList', '/GetFreshActivityInfo', '/GetFriend', '/GetFriendIDs', '/GetFriendRequestList', '/GetGachaDesc', '/GetGachaInfo', '/GetGachaSpecialExchangeDesc', '/GetGiftRankDesc', '/GetGiftStore', '/GetGiftStoreDetails', '/GetInstallmentItems', '/GetInstallmentStore', '/GetLinkageActivityInfo', '/GetLoginData', '/GetMailList', '/GetManualAllMapRewardStates', '/GetManualAllWeaponRewardStates', '/GetManualCollectInfo', '/GetNewPlayerLevelUpTaskInfo', '/GetPetList', '/GetPlatformFriendIDs', '/GetPlatformFriends', '/GetPlatformProfile', '/GetPlayerPersonalShow', '/GetRandomClanList', '/GetRecommendedFriend', '/GetStore', '/GetSubscribeStore', '/GetTopupEventInfo', '/GetVeteranTaskDesc', '/LoginGetDesc', '/LoginGetSplash', '/MajorLogin', '/OpenTreasureBox', '/PurchaseGacha', '/SelectProfile', '/UnlockProfile', '/live/ver.php'])

def load_app(module_name, attr="app"):
    try:
        mod = __import__(module_name)
        return getattr(mod, attr), None
    except Exception as e:
        return None, f"{module_name}: {e}\n{traceback.format_exc()[:500]}"

aisaka_app, aisaka_err = load_app("aisaka_server")
rbx2015_app, rbx2015_err = load_app("roblox2015")
RBX2015_PREFIXES = ("/Setting", "/Asset", "/asset", "/Game", "/game", "/Error", "/mobileapi")
lobby_app, lobby_err = load_app("lobby143_wsgi")
if lobby_err:
    print("[combined] ERRO lobby143:", lobby_err, file=sys.stderr)
ff_app, ff_err = load_app(os.path.splitext(FF_FILE)[0])

if aisaka_err:
    print("[combined] ERRO ao importar aisaka_server:", aisaka_err, file=sys.stderr)
if ff_err:
    print("[combined] AVISO: FF server nao importado:", ff_err.splitlines()[0], file=sys.stderr)
    ff_app = None

try:
    import conta_pv
    conta_app = conta_pv.application
except Exception as _e:
    print("[combined] conta_pv nao importado:", _e, file=sys.stderr)
    conta_app = None
CONTA_ROTAS = ("/access", "/login", "/api/captcha", "/api/register")
# /api/login cai no lobby143_wsgi (resposta estatica uid 10011227 = identidade embutida)


# ===== CAPTURA REMOTA no dispatcher (pega TODAS as rotas, inclusive as do ff_app) =====
import threading as _thc2, urllib.request as _urc2, json as _jc2
_CAPTURE_URL2 = "https://base44.app/api/apps/6acff94602abf7c68b7cd784/functions/lobbyCapture"

def _capture2(route, req_hex="", dec_hex="", note=""):
    def _go():
        try:
            d = _jc2.dumps({"route": str(route), "req_hex": str(req_hex), "dec_hex": str(dec_hex),
                            "note": str(note)}).encode()
            r = _urc2.Request(_CAPTURE_URL2, data=d, headers={"Content-Type": "application/json",
                                                              "User-Agent": "lobby143-capture/1.0"})
            _urc2.urlopen(r, timeout=5).read()
        except Exception:
            pass
    _thc2.Thread(target=_go, daemon=True).start()

def application(environ, start_response):
    import re as _re
    globals()["__re"] = _re
    path = environ.get("PATH_INFO", "")
    _capture2(path[:100], "", "", "dispatch")

    target = None
    if path.startswith("/ff143"):
        path = path[6:]
    # MODO PONTE: com PROXY_GAME ativo, todo o trafego do jogo FF (registro,
    # login, lobby) vai pra lobby143_wsgi, que repassa ao servidor de
    # referencia e grava as capturas. Roblox/Aisaka, health e logs seguem local.
    if PROXY_GAME_ENV and lobby_app is not None:
        _segue_local = (path in ("/health", "/_logs") or
                        path.startswith(RBX2015_PREFIXES) or
                        (path.startswith(AISAKA_PREFIXES) and
                         not path.startswith(("/downloads/", "/api/", "/access", "/signal/", "/live/"))))
        if not _segue_local:
            environ["PATH_INFO"] = path
            return lobby_app(environ, start_response)
    if conta_app is not None and (path in CONTA_ROTAS or (conta_pv._eh_fb_dialog(path) if "conta_pv" in globals() else False)):
        environ["PATH_INFO"] = path
        return conta_app(environ, start_response)
    if lobby_app is not None and (path == "/" or path in LOBBY_ROUTES or path.startswith(("/live/", "/signal/", "/oauth/", "/downloads/", "/access", "/api/login")) or path.startswith("/app/")):
        target = lobby_app
    elif path.startswith(RBX2015_PREFIXES):
        target = rbx2015_app
    elif "roblox" in environ.get("HTTP_USER_AGENT", "").lower():
        target = aisaka_app
    elif path.startswith(AISAKA_PREFIXES):
        target = aisaka_app
    elif ff_app is not None:
        target = ff_app
    else:
        target = aisaka_app
    return target(environ, start_response)

# para gunicorn: app = application
app = application

if __name__ == "__main__":
    from werkzeug.serving import run_simple
    run_simple("0.0.0.0", int(os.environ.get("PORT", 8080)), application)
