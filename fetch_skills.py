"""EVE Online のキャラクタースキルとスキルキューを取得して JSON に保存する（複数キャラクター対応）。

事前準備:
  1. https://developers.eveonline.com/ でアプリを作成
     - Callback URL: http://localhost:8080/callback
     - Scopes: esi-skills.read_skills.v1, esi-skills.read_skillqueue.v1,
               esi-fittings.read_fittings.v1, esi-assets.read_assets.v1,
               esi-clones.read_implants.v1, esi-location.read_ship_type.v1,
               esi-universe.read_structures.v1, esi-markets.structure_markets.v1
  2. .env.example を .env にコピーし、Client ID / Secret Key を記入

使い方:
  py fetch_skills.py                 登録済みの全キャラクターを取得
  py fetch_skills.py --add           キャラクターを追加（ブラウザでログイン）
  py fetch_skills.py --list          登録済みキャラクターの一覧
  py fetch_skills.py -c 名前         指定したキャラクターだけ取得（部分一致）
  py fetch_skills.py --remove 名前   キャラクターの登録を削除
  py fetch_skills.py --check Drake   targets.txt に加えて指定した艦・装備もチェック（複数可）
  py fetch_skills.py --no-open       HTML レポートをブラウザで開かない

取得後、targets.txt の艦・装備を使えるか判定し、report.html を生成してブラウザで開く。
"""

import argparse
import base64
import datetime as dt
import hashlib
import http.server
import json
import os
import re
import secrets
import threading
import time
import unicodedata
import urllib.parse
import webbrowser

import requests

import accounts
import report
import skill_check
from i18n import tr
from paths import BASE_DIR, DATA_DIR

ENV_FILE = BASE_DIR / ".env"
DESKTOP_ENV_FILE = BASE_DIR / "desktop.env"  # .exe に入れる設定（Client ID だけ。秘密鍵は入れない）
TOKENS_FILE = DATA_DIR / ".eve_tokens.json"
LEGACY_TOKEN_FILE = DATA_DIR / ".eve_token.json"  # 旧形式（1 キャラクターのみ）
SKILL_CACHE_FILE = DATA_DIR / "skill_cache.json"

CALLBACK_HOST = "localhost"
CALLBACK_PORT = 8080
# クラウドでは公開 URL の /callback（EVE Developers のアプリにも同じ URL を登録する）
PUBLIC_URL = os.environ.get("EVE_PUBLIC_URL", "").rstrip("/")
CALLBACK_URL = f"{PUBLIC_URL}/callback" if PUBLIC_URL else f"http://{CALLBACK_HOST}:{CALLBACK_PORT}/callback"
# 基本機能に必要なスコープ
BASE_SCOPES = ["esi-skills.read_skills.v1", "esi-skills.read_skillqueue.v1"]
# 追加機能用のスコープ（無くても基本機能は動く）
SCOPE_FITTINGS = "esi-fittings.read_fittings.v1"
SCOPE_ASSETS = "esi-assets.read_assets.v1"
SCOPE_IMPLANTS = "esi-clones.read_implants.v1"
SCOPE_SHIP = "esi-location.read_ship_type.v1"
SCOPE_STRUCTURES = "esi-universe.read_structures.v1"          # プレイヤー建造物の名前
SCOPE_STRUCTURE_MARKETS = "esi-markets.structure_markets.v1"  # プレイヤー建造物のマーケット
SCOPE_LOCATION = "esi-location.read_location.v1"              # 今いる星系（ワームホールのページ）
# お金（ウォレット・注文・契約・LP・スタンディング）
SCOPE_WALLET = "esi-wallet.read_character_wallet.v1"
SCOPE_ORDERS = "esi-markets.read_character_orders.v1"
SCOPE_CONTRACTS = "esi-contracts.read_character_contracts.v1"
SCOPE_LOYALTY = "esi-characters.read_loyalty.v1"
SCOPE_STANDINGS = "esi-characters.read_standings.v1"
# 生産・採掘・PI
SCOPE_JOBS = "esi-industry.read_character_jobs.v1"
SCOPE_BLUEPRINTS = "esi-characters.read_blueprints.v1"
SCOPE_MINING = "esi-industry.read_character_mining.v1"
SCOPE_PLANETS = "esi-planets.manage_planets.v1"
# 移動・ゲームの操作
SCOPE_WAYPOINT = "esi-ui.write_waypoint.v1"
SCOPE_OPEN_WINDOW = "esi-ui.open_window.v1"
SCOPE_CLONES = "esi-clones.read_clones.v1"
SCOPE_FATIGUE = "esi-characters.read_fatigue.v1"
# コーポレーション（役職が必要）
SCOPE_CORP_WALLETS = "esi-wallet.read_corporation_wallets.v1"
SCOPE_CORP_ASSETS = "esi-assets.read_corporation_assets.v1"
SCOPE_CORP_ROLES = "esi-characters.read_corporation_roles.v1"
SCOPE_CORP_DIVISIONS = "esi-corporations.read_divisions.v1"
SCOPE_CORP_BLUEPRINTS = "esi-corporations.read_blueprints.v1"  # コーポの設計図（ME・TE・残り回数）
EXTRA_SCOPES = [SCOPE_FITTINGS, SCOPE_ASSETS, SCOPE_IMPLANTS, SCOPE_SHIP, SCOPE_STRUCTURES, SCOPE_STRUCTURE_MARKETS,
                SCOPE_LOCATION, SCOPE_WALLET, SCOPE_ORDERS, SCOPE_CONTRACTS, SCOPE_LOYALTY, SCOPE_STANDINGS,
                SCOPE_JOBS, SCOPE_BLUEPRINTS, SCOPE_MINING, SCOPE_PLANETS, SCOPE_WAYPOINT, SCOPE_OPEN_WINDOW,
                SCOPE_CLONES, SCOPE_FATIGUE, SCOPE_CORP_WALLETS, SCOPE_CORP_ASSETS, SCOPE_CORP_ROLES,
                SCOPE_CORP_DIVISIONS, SCOPE_CORP_BLUEPRINTS]
SCOPES = " ".join(BASE_SCOPES + EXTRA_SCOPES)

SSO_AUTHORIZE_URL = "https://login.eveonline.com/v2/oauth/authorize/"
SSO_TOKEN_URL = "https://login.eveonline.com/v2/oauth/token"
SSO_ISSUERS = ("login.eveonline.com", "https://login.eveonline.com")
ESI_BASE = "https://esi.evetech.net/latest"
SKILL_CATEGORY_ID = 16

AUTH_TIMEOUT_SEC = 300
HTTP_TIMEOUT_SEC = 30
SESSION = requests.Session()
SESSION.headers["User-Agent"] = "EVE-online-skill-checker/1.0 (personal script)"


class TokenRevokedError(RuntimeError):
    """リフレッシュトークンが無効になり、再ログインが必要な状態。"""


# ---------- 設定 ----------

def load_env_file(path):
    """.env の KEY=VALUE を環境変数に読み込む（既存の環境変数は上書きしない）。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_credentials():
    """(Client ID, Secret Key)。Secret Key が無いときは None（秘密鍵を使わないログイン = PKCE）。

    読む順: データの場所の .env（.exe で使う人が自分の値で上書きするとき）→ このフォルダーの .env →
    .exe に入れた desktop.env（Client ID だけ）。先に読んだ値が優先。
    """
    for path in dict.fromkeys([DATA_DIR / ".env", ENV_FILE, DESKTOP_ENV_FILE]):
        load_env_file(path)
    client_id = os.environ.get("EVE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("EVE_CLIENT_SECRET", "").strip() or None
    if not client_id:
        raise RuntimeError(
            "EVE_CLIENT_ID が設定されていません。"
            ".env.example を .env にコピーして値を記入してください。"
        )
    return client_id, client_secret


def pkce_pair():
    """PKCE の (code_verifier, code_challenge)。秘密鍵を配れないアプリ（.exe）のログインで使う。"""
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


# ---------- 認証 (EVE SSO) ----------

class OAuthHandler(http.server.BaseHTTPRequestHandler):
    result = None  # {"code": ..., "state": ...} または {"error": ...}

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            # favicon.ico などは無視する
            self.send_response(404)
            self.end_headers()
            return

        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params:
            OAuthHandler.result = {
                "code": params["code"][0],
                "state": params.get("state", [""])[0],
            }
            self._respond(200, "認証成功。ブラウザを閉じてターミナルに戻ってください。")
        else:
            error = params.get("error_description", params.get("error", ["不明なエラー"]))[0]
            OAuthHandler.result = {"error": error}
            self._respond(400, tr("認証エラー: {0}", error))

    def _respond(self, status, message):
        self.send_response(status)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(message.encode("utf-8"))

    def log_message(self, format, *args):
        pass  # アクセスログを出さない


def wait_for_callback():
    OAuthHandler.result = None
    server = http.server.HTTPServer((CALLBACK_HOST, CALLBACK_PORT), OAuthHandler)
    server.timeout = 1
    deadline = time.monotonic() + AUTH_TIMEOUT_SEC
    try:
        while OAuthHandler.result is None:
            if time.monotonic() > deadline:
                raise RuntimeError(tr("{0} 秒以内に認証が完了しませんでした。", AUTH_TIMEOUT_SEC))
            server.handle_request()
    finally:
        server.server_close()
    return OAuthHandler.result


def request_token(credentials, data):
    client_id, client_secret = credentials
    if client_secret:
        res = SESSION.post(SSO_TOKEN_URL, auth=credentials, data=data, timeout=HTTP_TIMEOUT_SEC)
    else:  # PKCE: 秘密鍵の代わりに Client ID を送る（コードの交換では code_verifier も）
        res = SESSION.post(SSO_TOKEN_URL, data={**data, "client_id": client_id}, timeout=HTTP_TIMEOUT_SEC)
    if res.ok:
        return res.json()
    if "json" not in res.headers.get("content-type", ""):
        # クライアント認証に失敗すると EVE SSO は JSON ではなく HTML のエラーページを返す
        raise RuntimeError(
            tr("トークン取得失敗 ({0}): EVE SSO がクライアント認証を拒否しました。\n→ .env の EVE_CLIENT_SECRET が EVE Developers の Secret Key と一致していません。Secret Key を再生成して .env に貼り直してください。", res.status_code)
        )
    if "invalid_grant" in res.text and data["grant_type"] == "refresh_token":
        raise TokenRevokedError(tr("ログイン情報が無効になっています ({0})", res.text))
    raise RuntimeError(tr("トークン取得失敗 ({0}): {1}", res.status_code, res.text))


def build_auth_url(client_id, state, code_challenge=None):
    params = {
        "response_type": "code",
        "redirect_uri": CALLBACK_URL,
        "client_id": client_id,
        "scope": SCOPES,
        "state": state,
    }
    if code_challenge:
        params.update(code_challenge=code_challenge, code_challenge_method="S256")
    return SSO_AUTHORIZE_URL + "?" + urllib.parse.urlencode(params)


def login_with_browser(credentials):
    state = secrets.token_urlsafe(32)
    verifier, challenge = pkce_pair() if not credentials[1] else (None, None)
    auth_url = build_auth_url(credentials[0], state, challenge)
    print("ブラウザで認証を開きます...")
    print("別のアカウントのキャラクターを追加する場合は、次の URL をブラウザの")
    print("プライベートウィンドウで開くか、EVE のログイン画面でアカウントを切り替えてください:")
    print(auth_url)
    webbrowser.open(auth_url)

    result = wait_for_callback()
    if "error" in result:
        raise RuntimeError(tr("認証エラー: {0}", result['error']))
    if not secrets.compare_digest(result["state"], state):
        raise RuntimeError("state が一致しません（不正なリクエストの可能性があります）。")

    data = {"grant_type": "authorization_code", "code": result["code"]}
    if verifier:
        data["code_verifier"] = verifier
    return request_token(credentials, data)


def decode_jwt_payload(token):
    """アクセストークン (JWT) のペイロードを取り出す。

    トークンは TLS 経由で EVE SSO から直接受け取ったものなので署名検証は省略し、
    発行者と有効期限のみ確認する。
    """
    payload_b64 = token.split(".")[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    if payload.get("iss") not in SSO_ISSUERS:
        raise RuntimeError(tr("想定外のトークン発行者です: {0}", payload.get('iss')))
    if payload.get("exp", 0) < time.time():
        raise RuntimeError("アクセストークンの有効期限が切れています。")
    return payload


def character_from_token(access_token):
    payload = decode_jwt_payload(access_token)
    # sub は "CHARACTER:EVE:<character_id>" 形式
    return int(payload["sub"].split(":")[-1]), payload["name"]


def scopes_from_token(access_token):
    scp = decode_jwt_payload(access_token).get("scp", [])
    return [scp] if isinstance(scp, str) else list(scp)


# ---------- キャラクター（トークン）の保存 ----------

class CharacterStore:
    """キャラクターごとのリフレッシュトークンを .eve_tokens.json に保存する。

    形式: {"<character_id>": {"name": "...", "refresh_token": "...", "scopes": [...]}}
    """

    def __init__(self, path=TOKENS_FILE):
        self.path = path
        try:
            self.data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            self.data = {}

    def save(self):
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def characters(self):
        """[(character_id, name), ...] を名前順で返す。"""
        return sorted(((int(k), v["name"]) for k, v in self.data.items()), key=lambda c: c[1].lower())

    def put(self, char_id, name, refresh_token, scopes=None):
        self.data[str(char_id)] = {"name": name, "refresh_token": refresh_token, "scopes": scopes or []}
        self.save()

    def missing_scopes(self, char_id):
        """このキャラクターのログインに含まれていない追加機能用スコープ。"""
        granted = set(self.data.get(str(char_id), {}).get("scopes", []))
        return [s for s in EXTRA_SCOPES if s not in granted]

    def remove(self, char_id):
        self.data.pop(str(char_id), None)
        self.save()

    def refresh_token(self, char_id):
        return self.data[str(char_id)]["refresh_token"]

    def find(self, query):
        """名前の完全一致 → 部分一致（大文字小文字を区別しない）の順で探す。"""
        chars = self.characters()
        q = query.lower()
        exact = [c for c in chars if c[1].lower() == q]
        return exact or [c for c in chars if q in c[1].lower()]


def save_login(store, tokens):
    char_id, name = character_from_token(tokens["access_token"])
    store.put(char_id, name, tokens["refresh_token"], scopes_from_token(tokens["access_token"]))
    return char_id, name


def add_character(store, credentials):
    tokens = login_with_browser(credentials)
    char_id, name = save_login(store, tokens)
    print(f"✅ {name} を登録しました。")
    return char_id, name, tokens["access_token"]


def migrate_legacy_token(store, credentials):
    """旧形式 .eve_token.json（1 キャラクター分）を .eve_tokens.json に移行する。"""
    if not LEGACY_TOKEN_FILE.exists():
        return
    try:
        refresh_token = json.loads(LEGACY_TOKEN_FILE.read_text(encoding="utf-8"))["refresh_token"]
        tokens = request_token(credentials, {"grant_type": "refresh_token", "refresh_token": refresh_token})
        _, name = save_login(store, tokens)
        print(f"旧形式のログイン情報を移行しました: {name}")
    except (KeyError, json.JSONDecodeError, TokenRevokedError) as e:
        print(f"旧形式のログイン情報は移行できませんでした（{e}）")
    LEGACY_TOKEN_FILE.unlink()


def get_access_token(store, credentials, char_id):
    tokens = request_token(credentials, {
        "grant_type": "refresh_token",
        "refresh_token": store.refresh_token(char_id),
    })
    # EVE SSO はリフレッシュのたびに新しいリフレッシュトークンを返すので保存し直す
    save_login(store, tokens)
    return tokens["access_token"]


# ---------- ESI ----------

# ---------- ESI の利用制限 ----------
# ESI には 2 つの制限がある（https://developers.eveonline.com/docs/services/esi/rate-limiting/）。
#   ・ルートのグループごとの制限: 超えると 429 と Retry-After（マーケットの履歴は 1 分に 300 回ほど）
#   ・エラーの制限: 1 分にエラー（2xx・3xx 以外）が 100 回を超えると、しばらく全部のルートが 420 になる
# 429 もエラーとして数えられるので、制限にかかったら、同じグループ（420 なら全部）へは送らずに待つ。
ERROR_LIMIT_MARGIN = 20   # 残りのエラーの回数がこれ以下になったら、窓が終わるまで止める
RATE_LIMIT_MARGIN = 10    # グループの残りのトークンがこれ以下になったら、少し止める
MAX_WAIT_SEC = 30         # これより長く待つ必要があれば、送らずにエラーにする
_limit_lock = threading.Lock()
_paused_until = {}        # グループ（None = 全部のルート）→ 再開する時刻
_route_groups = {}        # パスの形（数字を {id} にしたもの）→ グループ


def _route_key(path):
    return re.sub(r"/\d+", "/{id}", path)


def _wait_for_limits(path):
    """制限で止めている間は待つ。長く待つ必要があれば RuntimeError（送ってもエラーが増えるだけなので）。"""
    with _limit_lock:
        group = _route_groups.get(_route_key(path))
        until = max(_paused_until.get(None, 0), _paused_until.get(group, 0) if group else 0)
    wait = until - time.time()
    if wait <= 0:
        return
    if wait > MAX_WAIT_SEC:
        raise RuntimeError(tr("ESI の利用制限にかかっています。{0} 秒ほど待ってから、もう一度試してください。", int(wait) + 1))
    time.sleep(wait)


def _int_header(headers, name):
    try:
        return int(headers[name])
    except (KeyError, TypeError, ValueError):
        return None


def _note_limits(path, res):
    """応答のヘッダーから制限の残りを読み、足りなければ止める。"""
    h = res.headers
    now = time.time()
    group = h.get("X-Ratelimit-Group")
    remain = _int_header(h, "X-ESI-Error-Limit-Remain")
    tokens = _int_header(h, "X-Ratelimit-Remaining")

    def pause(key, seconds):
        _paused_until[key] = max(_paused_until.get(key, 0), now + seconds)
    with _limit_lock:
        if group:
            _route_groups[_route_key(path)] = group
        if res.status_code == 420 or (remain is not None and remain <= ERROR_LIMIT_MARGIN):
            pause(None, (_int_header(h, "X-ESI-Error-Limit-Reset") or 60) + 1)
        if res.status_code == 429:
            pause(group, _int_header(h, "Retry-After") or 10)  # グループが分からなければ全部止める
        elif group and tokens is not None and tokens <= RATE_LIMIT_MARGIN:
            pause(group, 5)


def _esi_request(method, path, retries=3, with_headers=False, **kwargs):
    """ESI へのリクエスト。一時的なエラー（5xx・通信エラー）と利用制限（420・429）は待って再試行する。"""
    for attempt in range(retries):
        _wait_for_limits(path)
        try:
            res = SESSION.request(method, f"{ESI_BASE}{path}", timeout=HTTP_TIMEOUT_SEC, **kwargs)
        except requests.RequestException:
            if attempt == retries - 1:
                raise
        else:
            _note_limits(path, res)
            if res.ok:
                body = res.json() if res.content else None  # 204（ゲームの操作など）は本文なし
                return (body, res.headers) if with_headers else body
            if res.status_code in (420, 429) and attempt < retries - 1:
                continue  # 次の回の前に、制限が解けるまで待つ
            if res.status_code < 500 or attempt == retries - 1:
                raise RuntimeError(tr("ESI エラー ({0}) {1}: {2}", res.status_code, path, res.text))
        time.sleep(1 + attempt * 2)


def esi_get(path, access_token=None, params=None):
    headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}
    return _esi_request("GET", path, headers=headers, params=params)


def esi_get_all_pages(path, access_token):
    """X-Pages でページ分割される ESI（資産など）を全ページ取得する。"""
    headers = {"Authorization": f"Bearer {access_token}"}
    first, res_headers = _esi_request("GET", path, headers=headers, params={"page": 1}, with_headers=True)
    items = list(first)
    for page in range(2, int(res_headers.get("X-Pages", 1)) + 1):
        items += _esi_request("GET", path, headers=headers, params={"page": page})
    return items


def esi_post(path, body, params=None, access_token=None):
    headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}
    return _esi_request("POST", path, json=body, params=params, headers=headers)


def load_skill_catalog():
    """全スキルの {skill_id: {"name", "group"}} を返す。初回のみ ESI から取得してキャッシュする。"""
    try:
        cache = json.loads(SKILL_CACHE_FILE.read_text(encoding="utf-8"))
        return {int(k): v for k, v in cache.items()}
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    print("スキル名の一覧を取得しています（初回のみ）...")
    catalog = {}
    category = esi_get(f"/universe/categories/{SKILL_CATEGORY_ID}/")
    for group_id in category["groups"]:
        group = esi_get(f"/universe/groups/{group_id}/")
        type_ids = group.get("types", [])
        if not type_ids:
            continue
        # /universe/names/ は 1 回 1000 件まで
        for i in range(0, len(type_ids), 1000):
            for entry in esi_post("/universe/names/", type_ids[i:i + 1000]):
                catalog[entry["id"]] = {"name": entry["name"], "group": group["name"]}

    SKILL_CACHE_FILE.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return catalog


def skill_info(catalog, skill_id):
    return catalog.get(skill_id, {"name": f"Unknown ({skill_id})", "group": "Unknown"})


STATION_IDS = range(60_000_000, 64_000_000)
SOLAR_SYSTEM_IDS = range(30_000_000, 33_000_000)
STRUCTURE_MIN_ID = 1_000_000_000_000


STRUCTURE_NAMES_FILE = DATA_DIR / "structure_names.json"


def load_structure_names():
    try:
        return {int(k): v for k, v in json.loads(STRUCTURE_NAMES_FILE.read_text(encoding="utf-8")).items()}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def structure_name(structure_id, access_token):
    """プレイヤー建造物の名前（esi-universe.read_structures.v1 とドッキング権限が必要）。取れなければ None。"""
    cache = load_structure_names()
    if structure_id in cache:
        return cache[structure_id]["name"]
    try:
        info = esi_get(f"/universe/structures/{structure_id}/", access_token)
    except RuntimeError:
        return None  # 403: ドッキング権限なし など
    cache[structure_id] = {"name": info["name"], "solar_system_id": info.get("solar_system_id")}
    STRUCTURE_NAMES_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    return info["name"]


def resolve_location_names(location_ids, access_token=None):
    """ステーション・星系・プレイヤー建造物の ID → 名前。

    建造物の名前は access_token（esi-universe.read_structures.v1 付き）があるときだけ取得する。
    """
    names = {}
    public_ids = sorted({i for i in location_ids if i in STATION_IDS or i in SOLAR_SYSTEM_IDS})
    for i in range(0, len(public_ids), 1000):
        for entry in esi_post("/universe/names/", public_ids[i:i + 1000]):
            names[entry["id"]] = entry["name"]
    for i in location_ids:
        if i not in names and i >= STRUCTURE_MIN_ID:
            names[i] = (structure_name(i, access_token) if access_token else None) or "プレイヤー建造物"
    return names


def fetch_hangar_items(char_id, access_token, can_read_structures=False):
    """ハンガーにある組み立て済みアイテム（艦船の候補）。艦船かどうかはアプリ側で判定する。"""
    assets = esi_get_all_pages(f"/characters/{char_id}/assets/", access_token)
    item_ids = {a["item_id"] for a in assets}
    hangar = [
        a for a in assets
        if a.get("is_singleton") and a.get("location_flag") == "Hangar" and a["location_id"] not in item_ids
    ]
    names = resolve_location_names({a["location_id"] for a in hangar}, access_token if can_read_structures else None)
    return [
        {"item_id": a["item_id"], "type_id": a["type_id"], "location_id": a["location_id"],
         "location": names.get(a["location_id"], "不明な場所")}
        for a in hangar
    ]


def clean_ship_name(name):
    """ESI が返す艦名・フィット名の整形。

    - 日本語を Python 2 の repr 形式（u'<エスケープ列> - 名前'）で返すことがあるので元の文字に戻す
    - ゲームの翻訳タグ（<localized hint="Venture">ベンチャー*</localized>）を外し、中の名前だけにする
    """
    name = name or ""
    m = re.fullmatch(r"u'(.*)'", name)
    if m:
        name = re.sub(r"\\u([0-9a-fA-F]{4})", lambda u: chr(int(u.group(1), 16)), m.group(1))
    if "<localized" in name:
        name = re.sub(r"<localized[^>]*>(.*?)</localized>", lambda t: t.group(1).rstrip("*"), name)
        name = re.sub(r"</?localized[^>]*>", "", name)
    return name


def fetch_extras(char_id, access_token, scopes):
    """追加スコープで取れる情報。スコープが無い項目は None（＝未取得）のまま。"""
    extras = {"fittings": None, "hangar": None, "implants": None, "current_ship": None}
    if SCOPE_FITTINGS in scopes:
        extras["fittings"] = [
            {"fitting_id": f["fitting_id"], "name": clean_ship_name(f["name"]), "ship_type_id": f["ship_type_id"],
             "items": [{"type_id": i["type_id"], "flag": i["flag"], "quantity": i["quantity"]} for i in f["items"]]}
            for f in esi_get(f"/characters/{char_id}/fittings/", access_token)
        ]
    if SCOPE_ASSETS in scopes:
        extras["hangar"] = fetch_hangar_items(char_id, access_token, SCOPE_STRUCTURES in scopes)
    if SCOPE_IMPLANTS in scopes:
        extras["implants"] = esi_get(f"/characters/{char_id}/implants/", access_token)
    if SCOPE_SHIP in scopes:
        ship = esi_get(f"/characters/{char_id}/ship/", access_token)
        extras["current_ship"] = {"type_id": ship["ship_type_id"], "name": clean_ship_name(ship.get("ship_name"))}
    return extras


def fetch_character(char_id, char_name, access_token, catalog):
    skills_data = esi_get(f"/characters/{char_id}/skills/", access_token)
    queue_data = esi_get(f"/characters/{char_id}/skillqueue/", access_token)
    attributes = esi_get(f"/characters/{char_id}/attributes/", access_token)
    extras = fetch_extras(char_id, access_token, scopes_from_token(access_token))

    skills = sorted(
        (
            {
                **skill_info(catalog, s["skill_id"]),
                "skill_id": s["skill_id"],
                "trained_level": s["trained_skill_level"],
                "active_level": s["active_skill_level"],
                "skillpoints": s["skillpoints_in_skill"],
            }
            for s in skills_data.get("skills", [])
        ),
        key=lambda s: (s["group"], s["name"]),
    )
    queue = [
        {**skill_info(catalog, q["skill_id"]), **q}
        for q in sorted(queue_data, key=lambda q: q["queue_position"])
    ]
    return {
        "character_id": char_id,
        "character_name": char_name,
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "total_sp": skills_data.get("total_sp", 0),
        "unallocated_sp": skills_data.get("unallocated_sp", 0),
        "attributes": attributes,
        "skills": skills,
        "skill_queue": queue,
        **extras,
    }


# ---------- 出力 ----------

def output_dir():
    """キャラクターのデータの保存先（Web アプリでアカウントを使っているときは、アカウントごと）。"""
    return accounts.user_file("skills")


def output_path(char_name):
    safe = re.sub(r'[\\/:*?"<>|]', "_", char_name).strip() or "unknown"
    return output_dir() / f"{safe}.json"


def load_saved_output(char_name):
    """前回保存したデータ（取得に失敗したときの代わり）。"""
    try:
        return json.loads(output_path(char_name).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save_output(output):
    output_dir().mkdir(exist_ok=True)
    path = output_path(output["character_name"])
    path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def format_remaining(finish_date):
    if not finish_date:
        return "一時停止中"
    finish = dt.datetime.fromisoformat(finish_date.replace("Z", "+00:00"))
    remaining = finish - dt.datetime.now(dt.timezone.utc)
    if remaining.total_seconds() <= 0:
        return "完了"
    days = remaining.days
    hours, rem = divmod(remaining.seconds, 3600)
    minutes = rem // 60
    return tr("{0}日 {1}時間 {2}分", days, hours, minutes) if days else tr("{0}時間 {1}分", hours, minutes)


def queue_end(output):
    """キュー全体の残り時間（空なら「空」）。"""
    queue = output["skill_queue"]
    if not queue:
        return "空"
    return format_remaining(queue[-1].get("finish_date"))


def print_summary(output):
    print()
    print(f"=== {output['character_name']} ===")
    print(f"総 SP: {output['total_sp']:,}  / 未割り当て SP: {output['unallocated_sp']:,}")
    print(f"習得スキル数: {len(output['skills'])}  (Lv5: {sum(s['trained_level'] == 5 for s in output['skills'])})")

    group_sp = {}
    for s in output["skills"]:
        group_sp[s["group"]] = group_sp.get(s["group"], 0) + s["skillpoints"]
    print("\n--- グループ別 SP ---")
    for group, sp in sorted(group_sp.items(), key=lambda x: -x[1]):
        print(f"  {group:<32} {sp:>12,}")

    print("\n--- スキルキュー ---")
    if not output["skill_queue"]:
        print("  (空)  ⚠ スキルを訓練していません")
    for q in output["skill_queue"]:
        print(f"  {q['queue_position'] + 1:>2}. {q['name']} Lv{q['finished_level']}  残り {format_remaining(q.get('finish_date'))}")


def ljust_width(text, width):
    """全角文字を幅 2 として左寄せする。"""
    w = sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)
    return text + " " * max(width - w, 0)


def print_overview(results):
    """複数キャラクターの一覧表。"""
    print("\n" + "=" * 60)
    print("全キャラクター一覧")
    print("=" * 60)
    print(f"  {ljust_width('キャラクター', 24)} {'総 SP':>11}  キュー完了まで")
    for name, output, error in results:
        if error:
            print(f"  {ljust_width(name, 24)} {'-':>12}  ✖ {error}")
        else:
            print(f"  {ljust_width(name, 24)} {output['total_sp']:>12,}  {queue_end(output)}")
    total = sum(o["total_sp"] for _, o, e in results if not e)
    print(f"  {ljust_width('合計', 24)} {total:>12,}")


# ---------- コマンド ----------

def cmd_list(store):
    chars = store.characters()
    if not chars:
        print("登録済みのキャラクターはありません。--add で追加してください。")
        return
    print("登録済みキャラクター:")
    for char_id, name in chars:
        print(f"  {name}  (ID: {char_id})")


def select_one(store, query):
    matches = store.find(query)
    if not matches:
        raise RuntimeError(tr("「{0}」に一致するキャラクターがいません。--list で確認してください。", query))
    if len(matches) > 1:
        names = ", ".join(name for _, name in matches)
        raise RuntimeError(tr("「{0}」に複数のキャラクターが一致します: {1}", query, names))
    return matches[0]


def cmd_remove(store, query):
    char_id, name = select_one(store, query)
    store.remove(char_id)
    print(f"{name} の登録を削除しました。")


def refresh_character(store, credentials, char_id, name, catalog, access_token=None):
    """1 キャラクター分を ESI から取得して保存し、そのデータを返す。"""
    access_token = access_token or get_access_token(store, credentials, char_id)
    output = fetch_character(char_id, name, access_token, catalog)
    save_output(output)
    return output


def cmd_fetch(store, credentials, targets, fresh_logins=None):
    """targets: [(char_id, name), ...] を順に取得する。1 人失敗しても残りは続ける。

    戻り値: レポートに載せるキャラクターデータのリスト（失敗時は前回データで代用）。
    """
    fresh_logins = fresh_logins or {}
    catalog = load_skill_catalog()
    results = []
    characters = []
    for char_id, name in targets:
        try:
            output = refresh_character(store, credentials, char_id, name, catalog, fresh_logins.get(char_id))
            print_summary(output)
            print(f"\n✅ {output_path(name).relative_to(DATA_DIR)} に保存しました。")
            results.append((name, output, None))
            characters.append(output)
            continue
        except TokenRevokedError:
            error = "ログイン情報が無効です。--add で再登録してください"
        except (RuntimeError, requests.RequestException) as e:
            error = str(e).splitlines()[0]
        print(f"\n✖ {name}: {error}")
        results.append((name, None, error))
        saved = load_saved_output(name)
        if saved:
            print("  （レポートには前回取得したデータを使います）")
            characters.append({**saved, "stale": True})

    if len(results) > 1:
        print_overview(results)
    return characters


def run_checks(characters, extra_targets):
    """チェックリストと --check の艦・装備を判定し、結果を表示してレポート用データを返す。

    Web アプリで編集した targets.json があればそれを、なければ targets.txt を使う。
    """
    saved_list = skill_check.load_target_list()
    entries = [] if saved_list is not None else skill_check.load_targets()
    entries += [("コマンドライン指定", name) for name in extra_targets]
    if not (entries or saved_list) or not characters:
        return [], {}, []

    type_cache = skill_check.TypeCache(esi_get, esi_post)
    resolved = type_cache.resolve_names([name for _, name in entries]) if entries else {}
    unresolved = list(dict.fromkeys(name for _, name in entries if name not in resolved))

    targets = []
    seen = set()
    for t in saved_list or []:
        seen.add(t["type_id"])
        targets.append({"category": t["category"], "input": t["label"], "type_id": t["type_id"],
                        "name": type_cache.get(t["type_id"])["name"]})
    for category, name in entries:
        if name not in resolved or resolved[name][0] in seen:
            continue
        type_id, en_name = resolved[name]
        seen.add(type_id)
        targets.append({"category": category, "input": name, "type_id": type_id, "name": en_name})

    if targets:
        print("\n必要スキルを確認しています...")
    checks = {}
    for t in targets:
        for c in characters:
            checks[(t["type_id"], c["character_id"])] = skill_check.check_target(type_cache, t["type_id"], c)
    type_cache.save()

    print_checks(characters, targets, checks, unresolved)
    return targets, checks, unresolved


def print_checks(characters, targets, checks, unresolved):
    if not targets and not unresolved:
        return
    print("\n" + "=" * 60)
    print("艦・装備チェック")
    print("=" * 60)
    for name in unresolved:
        print(f"  ⚠ 「{name}」が見つかりません（英語名か日本語名の完全一致で指定してください）")
    for t in targets:
        print(f"  {t['input']}")
        for c in characters:
            r = checks[(t["type_id"], c["character_id"])]
            if r["status"] == "ok":
                state = "✓ 使用可"
            elif r["status"] == "queued":
                state = tr("⏳ キュー済み（{0} に使用可）", skill_check.format_local(r['ready_at']))
            else:
                state = tr("✗ 不足 {0} スキル / あと {1}", len(r['missing']), skill_check.format_minutes(r['total_minutes']))
            print(f"      {ljust_width(c['character_name'], 22)} {state}")


def write_report(characters, targets, checks, unresolved, open_browser):
    if not characters:
        return
    path = report.build_report(characters, targets, checks, unresolved)
    print(f"\n📄 レポートを {path.name} に出力しました。")
    if open_browser:
        webbrowser.open(path.as_uri())


def main():
    parser = argparse.ArgumentParser(description="EVE Online のスキルとスキルキューを取得します。")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--add", action="store_true", help="キャラクターを追加（ブラウザでログイン）")
    group.add_argument("--list", action="store_true", help="登録済みキャラクターの一覧")
    group.add_argument("--remove", metavar="名前", help="キャラクターの登録を削除")
    group.add_argument("-c", "--character", metavar="名前", help="指定したキャラクターだけ取得（部分一致）")
    parser.add_argument("--check", metavar="艦・装備", nargs="+", default=[],
                        help="targets.txt に加えてチェックする艦・装備（英語名または日本語名）")
    parser.add_argument("--no-open", action="store_true", help="HTML レポートをブラウザで開かない")
    args = parser.parse_args()

    try:
        store = CharacterStore()

        if args.list:
            cmd_list(store)
            return
        if args.remove:
            cmd_remove(store, args.remove)
            return

        credentials = get_credentials()
        migrate_legacy_token(store, credentials)

        if args.add or not store.characters():
            if not args.add:
                print("登録済みのキャラクターがないため、ログインを開始します。")
            char_id, name, access_token = add_character(store, credentials)
            characters = cmd_fetch(store, credentials, [(char_id, name)], {char_id: access_token})
            print("\n別のキャラクターを追加するには: py fetch_skills.py --add")
        else:
            selected = [select_one(store, args.character)] if args.character else store.characters()
            characters = cmd_fetch(store, credentials, selected)

        write_report(characters, *run_checks(characters, args.check), open_browser=not args.no_open)

    except KeyboardInterrupt:
        print("\n中断しました。")
    except (RuntimeError, requests.RequestException) as e:
        print(f"エラーが発生しました: {e}")


if __name__ == "__main__":
    main()
