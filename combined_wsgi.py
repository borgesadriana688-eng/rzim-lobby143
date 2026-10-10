#!/usr/bin/env python3
# COMBINED WSGI v0.1 — FF2018 (Rzim) + Aisaka (Roblox 2.463) no MESMO servico Railway
# Dispatcher por prefixo de caminho: /v1/settings, /v2/settings, /auth, /chat, /friends,
# /thumbnails, /accountinformation, /accountsettings, /notifications, /translations,
# /locale, /clientsettings.api, /ecsv2, /metrics, /ephemeralcounters, /abtesting,
# /contacts -> aisaka_server; o resto (oauth, app, api, player, game, match, health,
# livever, crash, debug, v2.5...) -> freefire_server_v220 (ou o que estiver no FF_FILE).
import os, sys, traceback

FF_FILE = os.environ.get("FF_FILE", "freefire_server_v220.py")

AISAKA_PREFIXES = (
    "/download", "/_upload", "/crash",
    "/v1/settings", "/v2/settings", "/clientsettings.api", "/auth", "/chat",
    "/friends", "/thumbnails", "/accountinformation", "/accountsettings",
    "/notifications", "/translations", "/locale", "/ecsv2", "/metrics",
    "/ephemeralcounters", "/abtesting", "/contacts",
    "/signup", "/v2/signup",
)

LOBBY_ROUTES = frozenset(['/ChangeClothes', '/EPVideoAdPortal', '/GetAccountLifeSeasonStats', '/GetAccountSubscriptions', '/GetBackpack', '/GetBingoRewardsInfo', '/GetDailyRankingReward', '/GetDiscountStore', '/GetEPInfo', '/GetEPSubscriptionBonusStatus', '/GetExchangeStore', '/GetFollowStreamerList', '/GetFreshActivityInfo', '/GetFriend', '/GetFriendIDs', '/GetFriendRequestList', '/GetGachaDesc', '/GetGachaInfo', '/GetGachaSpecialExchangeDesc', '/GetGiftRankDesc', '/GetGiftStore', '/GetGiftStoreDetails', '/GetInstallmentItems', '/GetInstallmentStore', '/GetLinkageActivityInfo', '/GetLoginData', '/GetMailList', '/GetManualAllMapRewardStates', '/GetManualAllWeaponRewardStates', '/GetManualCollectInfo', '/GetNewPlayerLevelUpTaskInfo', '/GetPetList', '/GetPlatformFriendIDs', '/GetPlatformFriends', '/GetPlatformProfile', '/GetPlayerPersonalShow', '/GetRandomClanList', '/GetRecommendedFriend', '/GetStore', '/GetSubscribeStore', '/GetTopupEventInfo', '/GetVeteranTaskDesc', '/LoginGetDesc', '/LoginGetSplash', '/MajorLogin', '/OpenTreasureBox', '/PurchaseGacha', '/SelectProfile', '/UnlockProfile', '/live/ver.php'])

def load_app(module_name, attr="app"):
    try:
        mod = __import__(module_name)
        return getattr(mod, attr), None
    except Exception as e:
        return None, f"{module_name}: {e}\n{traceback.format_exc()[:500]}"

aisaka_app, aisaka_err = load_app("aisaka_server")
lobby_app, lobby_err = load_app("lobby143_wsgi")
if lobby_err:
    print("[combined] ERRO lobby143:", lobby_err, file=sys.stderr)
ff_app, ff_err = load_app(os.path.splitext(FF_FILE)[0])

if aisaka_err:
    print("[combined] ERRO ao importar aisaka_server:", aisaka_err, file=sys.stderr)
if ff_err:
    print("[combined] AVISO: FF server nao importado:", ff_err.splitlines()[0], file=sys.stderr)
    ff_app = None

def application(environ, start_response):
    path = environ.get("PATH_INFO", "")
    target = None
    if lobby_app is not None and (path == "/" or path in LOBBY_ROUTES or path.startswith(("/live/", "/signal/", "/downloads/", "/access", "/api/login"))):
        target = lobby_app
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
