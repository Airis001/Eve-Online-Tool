"""EVE スキルチェッカーのローカル Web アプリ。

  py app.py               → http://localhost:8080 がブラウザで開く
  py app.py --no-browser  → ブラウザを開かずに起動

自分の PC からのアクセスだけを受け付ける（127.0.0.1 で待ち受け）。
EVE SSO の Callback URL (http://localhost:8080/callback) もこのサーバーが受け取る。

クラウドで動かすときは環境変数で設定する（DEPLOY.md）:
  EVE_PUBLIC_URL  公開 URL（例 https://xxx.fly.dev）。Callback URL はこれ + /callback
  APP_PASSWORD    招待コード（公開するときは必須）。設定すると、アカウントを作ってサインインして使う形になり、
                  キャラクターなどのデータはアカウントごとに分かれる。アカウントを作るときに招待コードが必要
  EVE_DATA_DIR    データの置き場所（永続ディスク）
  HOST / PORT     待ち受けるアドレス・ポート
"""

import hmac
import json
import os
import secrets
import socket
import sys
import threading
import time
import urllib.parse
import webbrowser
from datetime import timedelta
from html import escape

import requests
from flask import Flask, Response, abort, has_request_context, jsonify, redirect, request, session
from flask.json.provider import DefaultJSONProvider
from waitress import serve
from werkzeug.middleware.proxy_fix import ProxyFix

import accounts
import fetch_skills as core
import fitting
import market
import features
import i18n
import live as live_data
import sde as sde_data
import skill_check
import wormhole
from accounts import ThreadPoolExecutor
from recommend import Recommender
from i18n import tr
from item_catalog import CATEGORY_ORDER, ItemCatalog

HOST = os.environ.get("HOST", "127.0.0.1")
# --port は動作確認用（EVE の Callback URL が 8080 固定なので、ログインは 8080 でしか使えない）
PORT = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else int(os.environ.get("PORT") or core.CALLBACK_PORT)
CLOUD = bool(core.PUBLIC_URL)  # クラウド（公開 URL あり）で動いている
APP_URL = f"{core.PUBLIC_URL}/" if CLOUD else f"http://localhost:{PORT}/"
ALLOWED_HOSTS = {f"localhost:{PORT}", f"127.0.0.1:{PORT}", f"[::1]:{PORT}"}
if CLOUD:
    ALLOWED_HOSTS.add(urllib.parse.urlsplit(core.PUBLIC_URL).netloc)
SECRET_KEY_FILE = core.DATA_DIR / ".flask_secret"

# 取引に関係するスキル（手数料・注文数の上限）
TRADE_SKILLS = {"accounting": 16622, "broker_relations": 3446, "advanced_broker_relations": 16597,
                "trade": 3443, "retail": 3444, "wholesale": 16596, "tycoon": 18580}
# 生産に関係するスキル（トレード × 生産の損益で、生産するキャラクターを選ぶ目安）
INDUSTRY_SKILLS = {"industry": 3380, "advanced_industry": 3388, "mass_production": 3387}

class I18nJSONProvider(DefaultJSONProvider):
    """API の応答を画面の言語にして返す。

    日本語の値（カテゴリ名・エラーメッセージなど）は訳し、艦・装備の英語名の隣にはその言語の名前（loc）を足す。
    """

    def dumps(self, obj, **kwargs):
        language = i18n.lang()
        if language != "ja":
            obj = i18n.localize_names(i18n.translate_data(obj, i18n.dict_for(language)), language)
        return super().dumps(obj, **kwargs)


app = Flask(__name__, static_folder=str(core.BASE_DIR / "static"), static_url_path="/static")
app.json = I18nJSONProvider(app)
app.secret_key = secrets.token_hex(32)
if CLOUD:
    # HTTPS の前にあるプロキシ（Fly.io など）経由。再起動してもサインインが切れないよう、鍵はディスクに残す
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1)
    if not SECRET_KEY_FILE.exists():
        SECRET_KEY_FILE.write_text(secrets.token_hex(32), encoding="utf-8")
    app.secret_key = SECRET_KEY_FILE.read_text(encoding="utf-8").strip()
    app.config.update(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_SAMESITE="Lax",
                      PERMANENT_SESSION_LIFETIME=timedelta(days=30))

class UserStores:
    """サインイン中のアカウントのキャラクター（CharacterStore）に取り次ぐ。アカウントなしのときは今まで通り 1 つだけ。"""

    def __init__(self):
        self._stores = {}
        self._lock = threading.Lock()

    def _current(self):
        uid = accounts.current_uid()
        with self._lock:
            if uid not in self._stores:
                self._stores[uid] = core.CharacterStore(accounts.user_file(core.TOKENS_FILE.name))
            return self._stores[uid]

    def __getattr__(self, name):
        return getattr(self._current(), name)


store = UserStores()
type_cache = skill_check.TypeCache(core.esi_get, core.esi_post)
catalog = ItemCatalog(core.esi_get, core.esi_post)
fitting_data = fitting.FittingData(core.esi_get)
wormholes = wormhole.WormholeData(core.esi_get)
universe = wormhole.Universe(core.esi_get)
sde = sde_data.SdeData()


def _use_sde_names():
    """SDE のほかの言語の名前を、画面の名前と名前一覧の検索に使う（SDE を作り直したときも）。"""
    catalog.set_extra_names(sde.loc_names)


i18n.set_name_lookup(sde.localized)
sde.on_loaded.append(_use_sde_names)
if sde.ready:
    _use_sde_names()

_token_cache = {}  # (アカウント, character_id) → (アクセストークン, 有効期限)


def cached_access_token(char_id):
    """アクセストークン（有効期限まで使い回す。リフレッシュのたびにトークンが変わるのを避ける）。"""
    if str(char_id) not in store.data:  # ほかのアカウントのキャラクターは使えない
        raise RuntimeError("キャラクターが見つかりません。")
    key = (accounts.current_uid(), char_id)
    token, exp = _token_cache.get(key, (None, 0))
    if token and exp - 60 > time.time():
        return token
    with store_lock:
        token = core.get_access_token(store, credentials, char_id)
    _token_cache[key] = (token, core.decode_jwt_payload(token)["exp"])
    return token


def structure_market_tokens():
    """建造物のマーケットを読める（スコープのある）キャラクターのアクセストークンを順に返す。"""
    for char_id, _ in store.characters():
        if core.SCOPE_STRUCTURE_MARKETS in store.data.get(str(char_id), {}).get("scopes", []):
            try:
                yield cached_access_token(char_id)
            except (RuntimeError, requests.RequestException):
                continue


markets = market.Market(core.esi_get, core.esi_get_all_pages, structure_market_tokens, accounts.current_uid)
live = live_data.Live(core.esi_get, core.esi_get_all_pages, lambda cid: cached_access_token(cid),
                      lambda cid: store.data.get(str(cid), {}).get("scopes", []), accounts.current_uid)
store_lock = threading.RLock()  # トークンの保存（リフレッシュのたびに書き換わる）を直列化
credentials = None
skill_names = None


# ---------- 共通 ----------

@app.before_request
def guard():
    # DNS リバインディング対策: localhost（とクラウドの公開 URL）以外の Host は拒否
    accounts.set_current(None)
    if request.host not in ALLOWED_HOSTS:
        abort(403)
    # 招待コードを設定したときは、アカウントでサインインするまでページも API も開けない
    if app_password():
        user = accounts.get(session.get("uid"))
        if user and session.get("key"):
            accounts.set_current(user["id"], session["key"])
        elif request.path not in ("/signin", "/signup", "/lang") and not request.path.startswith("/static/"):
            if request.path.startswith("/api/"):
                return error("サインインしてください。", 401)
            return redirect("/signin?" + urllib.parse.urlencode({"next": request.full_path.rstrip("?")}))
    # CSRF 対策: 変更系 API は、このアプリの JS だけが付けるヘッダーを必須にする
    if request.method in ("POST", "DELETE") and request.path not in FORM_PATHS \
            and request.headers.get("X-Requested-With") != "skill-checker":
        abort(403)


# ---------- アカウント（クラウドで公開するとき） ----------

FORM_PATHS = ("/signin", "/signup", "/account")  # JS を使わないフォームのページ
SIGNIN_MAX_FAILS = 10       # この回数まちがえたら、しばらくサインインできなくする
SIGNIN_LOCK_SEC = 15 * 60
_signin_fails = {}          # ユーザー名（アカウントの作成は "signup"）→ まちがえた時刻
_signin_lock = threading.Lock()
LOCKED_MESSAGE = "まちがいが多いため、しばらく受け付けられません。15 分ほど待ってください。"


def app_password():
    """招待コード。設定してあるときは、アカウントでサインインして使う。"""
    return os.environ.get("APP_PASSWORD", "")


def signin_locked(key):
    with _signin_lock:
        now = time.time()
        for k in list(_signin_fails):
            _signin_fails[k] = [t for t in _signin_fails[k] if now - t < SIGNIN_LOCK_SEC]
            if not _signin_fails[k]:
                del _signin_fails[k]
        return len(_signin_fails.get(key, [])) >= SIGNIN_MAX_FAILS


def signin_failed(key):
    with _signin_lock:
        _signin_fails.setdefault(key, []).append(time.time())
    time.sleep(1)


def form_page(title, fields, button, message="", footer="", ok=""):
    """JS を使わないフォームのページ（文言は translate_html で今の言語にする）。"""
    language = i18n.lang()
    title, button, site = tr(title), tr(button), tr("EVE ツール")
    note = f'<p class="warn">{escape(message)}</p>' if message else ""
    note += f'<p class="ok-text">{escape(ok)}</p>' if ok else ""
    back = request.full_path.rstrip("?")
    switch = '<p class="muted lang-links">🌐 ' + " · ".join(
        f'<a href="/lang?{urllib.parse.urlencode({"to": code, "next": back})}" lang="{code}">{escape(label)}</a>'
        for code, label in i18n.LANG_NAMES.items() if code != language) + "</p>"
    html = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{title} · {site}</title>
<link rel="stylesheet" href="/static/style.css"></head>
<body><main class="signin"><div class="card"><h1>{site} · {title}</h1>{note}
<form method="post">{fields}
<button class="btn primary" type="submit">{button}</button></form>{footer}<!--lang-links--></div></main></body></html>"""
    # 言語名はそれぞれの言語のまま出すので、訳したあとに入れる
    return i18n.translate_html(html, language).replace("<!--lang-links-->", switch)


def form_field(label, name, kind="password", autocomplete="off", value="", focus=False):
    return (f'<label>{label}<input type="{kind}" name="{name}" autocomplete="{autocomplete}" value="{escape(value)}"'
            f'{" autofocus" if focus else ""} required></label>')


def signin_page(message="", name=""):
    fields = form_field("ユーザー名", "username", "text", "username", name, focus=True) \
        + form_field("パスワード", "password", autocomplete="current-password")
    return form_page("サインイン", fields, "サインイン", message,
                     '<p class="muted">はじめての方は <a href="/signup">アカウントを作る</a></p>')


def signup_page(message="", name=""):
    fields = form_field("ユーザー名（半角の英数字 3〜20 文字）", "username", "text", "username", name, focus=True) \
        + form_field(tr("パスワード（{0} 文字以上）", accounts.MIN_PASSWORD), "password", autocomplete="new-password") \
        + form_field("パスワード（もう一度）", "password2", autocomplete="new-password") \
        + form_field("招待コード（このサイトの管理者から聞いたもの）", "invite")
    return form_page("アカウントを作る", fields, "アカウントを作る", message,
                     '<p class="muted">キャラクターなどのデータは、パスワードで暗号化して保存します。'
                     'パスワードを忘れると、データを元に戻せません（アカウントを作り直すことになります）。</p>'
                     '<p class="muted">アカウントがある方は <a href="/signin">サインイン</a></p>')


def account_page(message="", ok=""):
    user = accounts.get(accounts.current_uid())
    fields = form_field("今のパスワード", "current", autocomplete="current-password") \
        + form_field(tr("新しいパスワード（{0} 文字以上）", accounts.MIN_PASSWORD), "password", autocomplete="new-password") \
        + form_field("新しいパスワード（もう一度）", "password2", autocomplete="new-password")
    return form_page(tr("アカウント（{0}）", escape(user['name'])), fields, "パスワードを変える", message,
                     '<p class="muted"><a href="/">← ホームに戻る</a> · <a href="/signout">サインアウト</a></p>', ok)


def safe_next(target):
    """サインイン後の戻り先（このサイトの中だけ）。"""
    return target if target.startswith("/") and not target.startswith("//") and "\\" not in target else "/"


def check_form_origin():
    """よそのサイトからのフォーム送信は受け付けない。"""
    origin = request.headers.get("Origin")
    if origin and urllib.parse.urlsplit(origin).netloc != request.host:
        abort(403)


def start_session(user, key):
    """サインイン済みにする。データの鍵はサーバーに保存せず、ブラウザーのクッキー（セッション）に持たせる。"""
    session.clear()
    session.permanent = True
    session["uid"] = user["id"]
    session["key"] = key


@app.route("/signin", methods=["GET", "POST"])
def signin():
    if not app_password():
        return redirect("/")
    if request.method == "GET":
        return signin_page()
    check_form_origin()
    name = request.form.get("username", "").strip()[:50]
    if signin_locked(name.lower()):
        return signin_page(LOCKED_MESSAGE, name), 429
    found = accounts.check(name, request.form.get("password", ""))
    if not found:
        signin_failed(name.lower())
        return signin_page("ユーザー名かパスワードがちがいます。", name), 401
    start_session(*found)
    return redirect(safe_next(request.args.get("next", "/")))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if not app_password():
        return redirect("/")
    if request.method == "GET":
        return signup_page()
    check_form_origin()
    name = request.form.get("username", "").strip()[:50]
    if signin_locked("signup"):
        return signup_page(LOCKED_MESSAGE, name), 429
    if not hmac.compare_digest(request.form.get("invite", "").encode(), app_password().encode()):
        signin_failed("signup")
        return signup_page("招待コードがちがいます。", name), 401
    if request.form.get("password", "") != request.form.get("password2", ""):
        return signup_page("パスワード（もう一度）が一致しません。", name), 400
    try:
        created = accounts.create(name, request.form.get("password", ""))
    except ValueError as e:
        return signup_page(str(e), name), 400
    start_session(*created)
    return redirect("/")


@app.route("/account", methods=["GET", "POST"])
def account():
    if not accounts.current_uid():
        return redirect("/")
    if request.method == "GET":
        return account_page()
    check_form_origin()
    user = accounts.get(accounts.current_uid())
    key = user["name"].lower()
    if signin_locked(key):
        return account_page(LOCKED_MESSAGE), 429
    if not accounts.check(user["name"], request.form.get("current", "")):
        signin_failed(key)
        return account_page("今のパスワードがちがいます。"), 401
    if request.form.get("password", "") != request.form.get("password2", ""):
        return account_page("新しいパスワード（もう一度）が一致しません。"), 400
    try:
        accounts.set_password(user["id"], request.form.get("password", ""))
    except ValueError as e:
        return account_page(str(e)), 400
    return account_page(ok="パスワードを変えました。")


@app.get("/api/account")
def api_account():
    """サインイン中のアカウント（アカウントなしで使っているときは name が None）。"""
    user = accounts.get(accounts.current_uid())
    return jsonify({"name": user and user["name"]})


@app.get("/signout")
def signout():
    session.clear()
    return redirect("/signin" if app_password() else "/")


def back_to_index(**params):
    """EVE ログインのあとは、スキルチェッカーのページに戻る。"""
    return redirect("/skills?" + urllib.parse.urlencode(params))


def error(message, status=400):
    return jsonify({"error": message}), status


def get_skill_names():
    global skill_names
    if skill_names is None:
        skill_names = core.load_skill_catalog()
    return skill_names


ATTRIBUTE_KEYS = ["perception", "memory", "willpower", "intelligence", "charisma"]
MAX_BOOST = 50


def boost_from_request():
    """?boost=知覚,記憶,意志,知性,魅力（例: 3,3,3,3,3）を {属性: 加算値} に。指定なし・不正なら {}。"""
    raw = request.args.get("boost", "") if has_request_context() else ""
    try:
        values = [int(v) for v in raw.split(",")] if raw else []
    except ValueError:
        return {}
    if len(values) != len(ATTRIBUTE_KEYS):
        return {}
    return {k: max(0, min(v, MAX_BOOST)) for k, v in zip(ATTRIBUTE_KEYS, values) if v > 0}


def apply_boost(character, boost):
    """ブースト分を属性値に足したキャラクターデータ（元の値は base_attributes に残す）。"""
    attrs = character.get("attributes")
    if not boost or not attrs:
        return character
    boosted = {**attrs, **{k: attrs.get(k, 0) + v for k, v in boost.items()}}
    return {**character, "attributes": boosted, "base_attributes": attrs, "boost": boost}


def load_characters():
    """登録済みキャラクターの保存データ（ブースト指定があれば属性値に反映）。未取得は "missing": True。"""
    boost = boost_from_request()
    chars = []
    for char_id, name in store.characters():
        data = core.load_saved_output(name)
        for f in (data or {}).get("fittings") or []:  # 保存済みの古いデータのフィット名（翻訳タグ付き）も整える
            f["name"] = core.clean_ship_name(f["name"])
        chars.append(apply_boost(data, boost) if data else {"character_id": char_id, "character_name": name, "missing": True})
    return chars


def check_all(type_id, characters):
    return {
        str(c["character_id"]): skill_check.check_target(type_cache, type_id, c)
        for c in characters if not c.get("missing")
    }


def item_label(type_id):
    item = catalog.get(type_id)
    if item:
        return item["ja"], item["en"], item["category"]
    info = type_cache.get(type_id)
    return info["name"], info["name"], "その他"


def summarize(result):
    return {k: result[k] for k in ("status", "total_minutes", "ready_at")}


def enrich_character(c):
    """画面用に、日本語名・所持艦の判定・不足スコープを付け足す（フィットは別 API で送る）。"""
    out = {k: v for k, v in c.items() if k not in ("fittings", "hangar")}
    out["missing_scopes"] = store.missing_scopes(c["character_id"])
    if c.get("missing"):
        return out

    out["ships"] = None  # None = 所持艦を取得していない（スコープ不足など）
    out["ships_pending"] = c.get("hangar") is not None and not catalog.ready
    if c.get("hangar") is not None and catalog.ready:
        ships = []
        for h in c["hangar"]:
            item = catalog.get(h["type_id"])
            if item and item["category"] == "艦船":
                result = skill_check.check_target(type_cache, h["type_id"], c)
                ships.append({**h, "ja": item["ja"], "en": item["en"], "group": item["group"], **summarize(result)})
        ships.sort(key=lambda x: (x["group"], x["ja"]))
        out["ships"] = ships

    if c.get("implants") is not None:
        out["implants"] = [{"type_id": t, "ja": item_label(t)[0], "en": item_label(t)[1]} for t in c["implants"]]
    if c.get("current_ship"):
        ja, en, _ = item_label(c["current_ship"]["type_id"])
        name = core.clean_ship_name(c["current_ship"].get("name"))  # 保存済みの古いデータ用
        out["current_ship"] = {**c["current_ship"], "name": name, "ja": ja, "en": en}
    return out


def fit_checks(type_ids, characters, ship_type_id=None, fitted=None):
    """フィット（複数アイテム）の判定を、原因モジュール付きでキャラクターごとに。

    ship_type_id と fitted（装着モジュールの type_id、個数分）を渡すと、CPU・PG・キャリブレーションも判定する。
    """
    checks = {}
    for c in characters:
        result = skill_check.check_types(type_cache, type_ids, c)
        blockers = skill_check.find_blockers(type_cache, type_ids, c)
        for b in blockers:
            b["ja"], b["en"], _ = item_label(b["type_id"])
        entry = {**result, "blockers": blockers}
        if ship_type_id and fitted is not None:
            try:
                # 不足時の「必要なスキルレベル」の訓練時間は、前提スキル込みのスキルプランで見積もる
                cost = lambda targets, c=c: skill_check.build_plan(type_cache, [], c, targets)["total_minutes"]  # noqa: E731
                entry["resources"] = fitting.check_resources(fitting_data, type_cache, ship_type_id, fitted, c, cost)
            except (RuntimeError, requests.RequestException, KeyError) as e:
                entry["resources_error"] = str(e).splitlines()[0]
        checks[str(c["character_id"])] = entry
    fitting_data.save()
    return checks


def load_groups():
    """キャラクターグループ [{"id", "name", "character_ids"}]。"""
    try:
        return json.loads(accounts.user_file("groups.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_groups(groups):
    accounts.user_file("groups.json").write_text(json.dumps(groups, ensure_ascii=False, indent=2), encoding="utf-8")


def ready_characters():
    return [c for c in load_characters() if not c.get("missing")]


def targets_file():
    return accounts.user_file(skill_check.TARGETS_JSON_FILE.name)


def load_or_import_targets():
    """targets.json を読む。なければ targets.txt から取り込んで作る。"""
    targets = skill_check.load_target_list(targets_file())
    if targets is not None:
        return targets
    entries = skill_check.load_targets()
    resolved = type_cache.resolve_names([name for _, name in entries]) if entries else {}
    targets, seen = [], set()
    for category, name in entries:
        if name in resolved and resolved[name][0] not in seen:
            seen.add(resolved[name][0])
            targets.append({"type_id": resolved[name][0], "label": name, "category": category})
    skill_check.save_target_list(targets, targets_file())
    type_cache.save()
    return targets


# ---------- ページ ----------

_page_cache = {}  # (ページ, 言語) → (更新時刻, HTML)


def page(name):
    """static/<name>.html を今の言語にして返す（言語の辞書 /i18n.js も読み込ませる）。"""
    language = i18n.lang()
    path = core.BASE_DIR / "static" / f"{name}.html"
    stamp = (path.stat().st_mtime, i18n.dict_stamp(language))
    cached = _page_cache.get((name, language))
    if not cached or cached[0] != stamp:
        html = i18n.translate_html(path.read_text(encoding="utf-8"), language)
        script = f'<script src="/i18n.js?lang={language}&v={int(stamp[1])}"></script>'
        html = html.replace('<script src="/static/common.js">', script + '\n  <script src="/static/common.js">', 1)
        cached = _page_cache[(name, language)] = (stamp, html)
    return Response(cached[1], mimetype="text/html")


@app.get("/i18n.js")
def i18n_js():
    """画面の言語と訳の辞書（static/i18n.js の前に入れる）。"""
    language = i18n.lang()
    head = (f"window.LANG = {json.dumps(language)};\nwindow.LANG_NAMES = {json.dumps(i18n.LANG_NAMES, ensure_ascii=False)};\n"
            f"window.I18N_DICT = {json.dumps(i18n.dict_for(language), ensure_ascii=False)};\n")
    body = (core.BASE_DIR / "static" / "i18n.js").read_text(encoding="utf-8")
    res = Response(head + body, mimetype="text/javascript")
    res.headers["Cache-Control"] = "no-cache"
    res.headers["Vary"] = "Cookie"
    return res


@app.get("/lang")
def switch_lang():
    """言語を切り替えて、元のページに戻る。?to=ja|en|de|…&next=/path"""
    res = redirect(safe_next(request.args.get("next", "/")))
    if request.args.get("to") in i18n.LANGS:
        res.set_cookie(i18n.COOKIE, request.args["to"], max_age=400 * 24 * 3600, samesite="Lax", secure=CLOUD)
    return res


@app.get("/")
def home():
    return page("home")


# 機能のページ
for _page in ("skills", "market", "recommend", "ships", "wormhole",
              "wallet", "industry", "pi", "travel", "fitting", "skilllist", "pve", "pvp", "signals", "assets", "appraise", "remap", "trade", "intel", "compare", "nes", "haul", "dist", "lp"):
    app.add_url_rule(f"/{_page}", f"{_page}_page", lambda _p=_page: page(_p))


@app.get("/login")
def login():
    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state
    challenge = None
    if not credentials[1]:  # 秘密鍵なし（.exe）: PKCE でログインする
        session["pkce_verifier"], challenge = core.pkce_pair()
    return redirect(core.build_auth_url(credentials[0], state, challenge))


@app.get("/callback")
def callback():
    expected = session.pop("oauth_state", None)
    if "error" in request.args:
        message = request.args.get("error_description", request.args["error"])
        if "scope" in message.lower():
            message += "（EVE の開発者サイトのアプリ設定に、このツールが使うスコープがすべて追加されているか確認してください）"
        return back_to_index(error=message)
    if not expected or not secrets.compare_digest(request.args.get("state", ""), expected):
        return back_to_index(error="state が一致しません。もう一度追加してください。")
    try:
        data = {"grant_type": "authorization_code", "code": request.args.get("code", "")}
        if session.get("pkce_verifier"):
            data["code_verifier"] = session.pop("pkce_verifier")
        tokens = core.request_token(credentials, data)
        with store_lock:
            char_id, name = core.save_login(store, tokens)
        core.refresh_character(store, credentials, char_id, name, get_skill_names(), tokens["access_token"])
    except (RuntimeError, requests.RequestException) as e:
        return back_to_index(error=str(e).splitlines()[0])
    return back_to_index(added=name)


# ---------- API ----------

@app.get("/api/state")
def api_state():
    characters = load_characters()
    targets = []
    for t in load_or_import_targets():
        ja, en, _ = item_label(t["type_id"])
        targets.append({**t, "ja": ja, "en": en, "checks": check_all(t["type_id"], characters)})
    type_cache.save()
    return jsonify({
        "characters": [enrich_character(c) for c in characters],
        "targets": targets,
        "category_order": CATEGORY_ORDER,
        "groups": load_groups(),
        "catalog": catalog.status,
    })


@app.post("/api/refresh")
def api_refresh():
    """全キャラクター（または character_id で指定した 1 人）を ESI から取り直す。"""
    only = (request.get_json(silent=True) or {}).get("character_id")
    errors = []
    for char_id, name in store.characters():
        if only and char_id != only:
            continue
        try:
            with store_lock:
                token = core.get_access_token(store, credentials, char_id)
            core.refresh_character(store, credentials, char_id, name, get_skill_names(), token)
        except core.TokenRevokedError:
            errors.append(tr("{0}: ログイン情報が無効です。いったん削除して追加し直してください。", name))
        except (RuntimeError, requests.RequestException) as e:
            errors.append(f"{name}: {str(e).splitlines()[0]}")
    return jsonify({"errors": errors})


@app.get("/api/search")
def api_search():
    results = catalog.search(request.args.get("q", ""))
    if request.args.get("checks") != "0":  # マーケットページなど、判定が不要なときは checks=0
        characters = [c for c in load_characters() if not c.get("missing")]
        for item in results:
            item["checks"] = {cid: {"status": r["status"]} for cid, r in check_all(item["id"], characters).items()}
    type_cache.save()
    return jsonify({"catalog": catalog.status, "results": results})


@app.get("/api/check/<int:type_id>")
def api_check(type_id):
    ja, en, category = item_label(type_id)
    result = check_all(type_id, load_characters())
    type_cache.save()
    return jsonify({"type_id": type_id, "ja": ja, "en": en, "category": category, "checks": result})


@app.post("/api/targets")
def api_add_target():
    type_id = (request.get_json(silent=True) or {}).get("type_id")
    if not isinstance(type_id, int):
        return error("type_id が必要です")
    targets = load_or_import_targets()
    if any(t["type_id"] == type_id for t in targets):
        return jsonify({"ok": True})
    ja, _, category = item_label(type_id)
    targets.append({"type_id": type_id, "label": ja, "category": category})
    skill_check.save_target_list(targets, targets_file())
    return jsonify({"ok": True})


@app.delete("/api/targets/<int:type_id>")
def api_remove_target(type_id):
    targets = [t for t in load_or_import_targets() if t["type_id"] != type_id]
    skill_check.save_target_list(targets, targets_file())
    return jsonify({"ok": True})


@app.delete("/api/characters/<int:char_id>")
def api_remove_character(char_id):
    with store_lock:
        store.remove(char_id)
    return jsonify({"ok": True})


@app.post("/api/groups")
def api_save_group():
    """グループの作成（id なし）または更新（id あり）。"""
    body = request.get_json(silent=True) or {}
    name = str(body.get("name", "")).strip()
    ids = body.get("character_ids")
    if not 0 < len(name) <= 30:
        return error("グループ名は 1〜30 文字で入力してください")
    if not (isinstance(ids, list) and ids and all(isinstance(i, int) for i in ids)):
        return error("キャラクターを 1 人以上選んでください")

    groups = load_groups()
    group_id = body.get("id")
    group = next((g for g in groups if g["id"] == group_id), None) if group_id else None
    if group_id and not group:
        return error("グループが見つかりません", 404)
    if any(g["name"] == name and g is not group for g in groups):
        return error(tr("「{0}」という名前のグループはすでにあります", name))
    if group:
        group.update(name=name, character_ids=ids)
    else:
        group = {"id": secrets.token_hex(4), "name": name, "character_ids": ids}
        groups.append(group)
    save_groups(groups)
    return jsonify(group)


@app.delete("/api/groups/<group_id>")
def api_delete_group(group_id):
    save_groups([g for g in load_groups() if g["id"] != group_id])
    return jsonify({"ok": True})


# ---------- フィット ----------

# EFT 形式でのスロットの並び順（ゲームのインポートもこの順）
EFT_SLOT_ORDER = ["LoSlot", "MedSlot", "HiSlot", "RigSlot", "SubSystemSlot"]
EFT_BAY_ORDER = ["DroneBay", "FighterBay", "Cargo"]


def build_eft(name, ship_type_id, items):
    """ESI のフィット（スロット情報付き）から、ゲームにインポートできる EFT 形式のテキストを作る。"""
    en = lambda type_id: item_label(type_id)[1]  # noqa: E731 - ゲームのインポートは英語名
    lines = [f"[{en(ship_type_id)}, {name}]"]
    for prefix in EFT_SLOT_ORDER:
        slot_items = sorted(
            (i for i in items if i["flag"].startswith(prefix)),
            key=lambda i: int("".join(ch for ch in i["flag"][len(prefix):] if ch.isdigit()) or 0),
        )
        if slot_items:
            lines += [en(i["type_id"]) for i in slot_items] + [""]
    for bay in EFT_BAY_ORDER:
        bay_items = [i for i in items if i["flag"] == bay]
        if bay_items:
            lines += ["", *(f"{en(i['type_id'])} x{i['quantity']}" for i in bay_items)]
    return "\n".join(lines).strip() + "\n"


def make_bom(ship_type_id, fitted_ids, bay):
    """フィットの部品表 [{"type_id", "qty", "kind", "ja", "en"}]。kind: ship / module / bay（ドローン・カーゴ）"""
    counts = {}
    for type_id, qty, kind in [(ship_type_id, 1, "ship"), *((t, 1, "module") for t in fitted_ids),
                               *((t, q, "bay") for t, q in bay)]:
        counts[(type_id, kind)] = counts.get((type_id, kind), 0) + qty
    bom = []
    for (type_id, kind), qty in counts.items():
        ja, en, _ = item_label(type_id)
        bom.append({"type_id": type_id, "qty": qty, "kind": kind, "ja": ja, "en": en})
    return bom


def resolve_eft(text):
    """EFT 形式のテキストを解析して ID に変換する。失敗時は ValueError。"""
    fit = skill_check.parse_eft(text)
    names = list(dict.fromkeys([fit["ship"], *fit["items"]]))
    ids = {name: catalog.find_by_name(name) for name in names}
    rest = [name for name, type_id in ids.items() if not type_id]
    if rest:  # 名前一覧に無いもの（作成中など）は ESI で探す
        for name, (type_id, _) in type_cache.resolve_names(rest).items():
            ids[name] = type_id
    if not ids.get(fit["ship"]):
        raise ValueError(tr("艦「{0}」が見つかりません。", fit['ship']))
    fitted = [ids[name] for name in fit["fitted"] if ids.get(name)]
    bay = [(ids[name], qty) for name, qty in fit["bay"] if ids.get(name)]
    return {
        "name": fit["name"],
        "ship_type_id": ids[fit["ship"]],
        "fitted": fitted,
        "bom": make_bom(ids[fit["ship"]], fitted, bay),
        "type_ids": sorted({type_id for type_id in ids.values() if type_id}),
        "unresolved": [name for name in names if not ids.get(name)],
        "eft": text.strip() + "\n",
    }


def resolve_saved_fit(fit):
    """保存したフィットの EFT を解析し直す（装着モジュール・部品表）。失敗したら None。"""
    try:
        return resolve_eft(fit["eft"])
    except ValueError:
        return None


def load_saved_fits():
    """このアプリに保存したフィット [{"id", "name", "ship_type_id", "type_ids", "eft", "saved_at"}]。"""
    try:
        return json.loads(accounts.user_file("saved_fits.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_saved_fits(fits):
    accounts.user_file("saved_fits.json").write_text(json.dumps(fits, ensure_ascii=False, indent=2), encoding="utf-8")


@app.get("/api/fittings")
def api_fittings():
    """このアプリに保存したフィットと、全キャラクターのゲーム内フィット（同じものはまとめる）の判定。"""
    characters = ready_characters()
    result = []

    for f in load_saved_fits():
        ship_ja, ship_en, _ = item_label(f["ship_type_id"])
        resolved = resolve_saved_fit(f)
        result.append({**f, "source": "app", "key": f"app:{f['id']}", "ship_ja": ship_ja, "ship_en": ship_en,
                       "bom": resolved["bom"] if resolved else [],
                       "checks": fit_checks(f["type_ids"], characters, f["ship_type_id"],
                                            resolved["fitted"] if resolved else None)})

    game_fits = {}
    for c in characters:
        for f in c.get("fittings") or []:
            type_ids = sorted({f["ship_type_id"], *(i["type_id"] for i in f["items"])})
            key = (f["name"], f["ship_type_id"], tuple(type_ids))
            entry = game_fits.setdefault(key, {"name": f["name"], "ship_type_id": f["ship_type_id"],
                                               "type_ids": type_ids, "items": f["items"], "owners": []})
            entry["owners"].append(c["character_name"])
    game_result = []
    for n, entry in enumerate(game_fits.values()):
        items = entry.pop("items")
        fitted = fitting.fitted_type_ids(items)
        bay = [(i["type_id"], i["quantity"]) for i in items if i["flag"] in ("DroneBay", "FighterBay", "Cargo")]
        entry["bom"] = make_bom(entry["ship_type_id"], fitted, bay)
        entry["ship_ja"], entry["ship_en"], _ = item_label(entry["ship_type_id"])
        entry.update(source="game", key=f"game:{n}", eft=build_eft(entry["name"], entry["ship_type_id"], items),
                     checks=fit_checks(entry["type_ids"], characters, entry["ship_type_id"], fitted))
        game_result.append(entry)
    game_result.sort(key=lambda e: (e["ship_ja"], e["name"]))

    type_cache.save()
    no_scope = [c["character_name"] for c in characters if c.get("fittings") is None]
    return jsonify({"fittings": result + game_result, "without_scope": no_scope})


@app.post("/api/fit/check")
def api_fit_check():
    """EFT 形式のテキストを判定する。"""
    try:
        fit = resolve_eft((request.get_json(silent=True) or {}).get("eft", ""))
    except ValueError as e:
        return error(str(e))
    ship_ja, ship_en, _ = item_label(fit["ship_type_id"])
    checks = fit_checks(fit["type_ids"], ready_characters(), fit["ship_type_id"], fit["fitted"])
    type_cache.save()
    return jsonify({**fit, "key": "eft", "ship_ja": ship_ja, "ship_en": ship_en, "checks": checks})


@app.post("/api/saved-fits")
def api_save_fit():
    """EFT 形式のフィットをこのアプリに保存する（name を渡すとフィット名を上書き）。"""
    body = request.get_json(silent=True) or {}
    try:
        fit = resolve_eft(body.get("eft", ""))
    except ValueError as e:
        return error(str(e))
    name = str(body.get("name") or fit["name"]).strip()[:100] or fit["name"]
    if name != fit["name"]:  # EFT の 1 行目のフィット名も合わせる
        first, _, rest = fit["eft"].partition("\n")
        fit["eft"] = f"[{first[1:first.index(',')] if ',' in first else first[1:-1]}, {name}]\n{rest}"
    fits = load_saved_fits()
    saved = {"id": secrets.token_hex(4), "name": name, "ship_type_id": fit["ship_type_id"],
             "type_ids": fit["type_ids"], "eft": fit["eft"],
             "saved_at": core.dt.datetime.now(core.dt.timezone.utc).isoformat(timespec="seconds")}
    fits.append(saved)
    save_saved_fits(fits)
    return jsonify(saved)


@app.delete("/api/saved-fits/<fit_id>")
def api_delete_fit(fit_id):
    save_saved_fits([f for f in load_saved_fits() if f["id"] != fit_id])
    return jsonify({"ok": True})


@app.post("/api/plan")
def api_plan():
    """type_ids を使えるようにする訓練手順（スキルプラン）。

    skills: [[skill_id, level], ...] を渡すと、そのスキルをそのレベルまで上げる手順も加える
    （CPU・PG を足りさせるためのスキルなど）。
    """
    body = request.get_json(silent=True) or {}
    type_ids = body.get("type_ids") or []
    skills = body.get("skills") or []
    char_id = body.get("character_id")
    if not (isinstance(type_ids, list) and len(type_ids) <= 300 and all(isinstance(t, int) for t in type_ids)):
        return error("type_ids が不正です")
    if not (isinstance(skills, list) and len(skills) <= 50
            and all(isinstance(s, list) and len(s) == 2 and all(isinstance(v, int) for v in s) and 1 <= s[1] <= 5 for s in skills)):
        return error("skills が不正です")
    if not type_ids and not skills:
        return error("type_ids か skills が必要です")
    character = next((c for c in ready_characters() if c["character_id"] == char_id), None)
    if not character:
        return error("キャラクターが見つかりません")
    plan = skill_check.build_plan(type_cache, type_ids, character, {s: lv for s, lv in skills})
    type_cache.save()
    return jsonify({**plan, "text": skill_check.plan_to_text(plan), "character_name": character["character_name"]})


def market_location_arg():
    try:
        location_id = int(request.args.get("location", market.DEFAULT_LOCATION_ID))
        market.Market.kind(location_id)
    except (ValueError, market.MarketError):
        raise ValueError("location が不正です")
    return location_id


def location_label(location_id, fallback=None):
    try:
        return markets.location_name(location_id, fallback)
    except (RuntimeError, requests.RequestException):
        return fallback or str(location_id)


@app.get("/api/market/locations")
def api_market_locations():
    """マーケットの場所の候補: 主要な取引拠点と、キャラクターの艦が置いてある場所。"""
    owned = {}
    for c in ready_characters():
        for h in c.get("hangar") or []:
            if h["location_id"] in market.STATION_IDS or h["location_id"] >= market.STRUCTURE_MIN_ID:
                entry = owned.setdefault(h["location_id"], {"id": h["location_id"], "name": h["location"],
                                                            "kind": market.Market.kind(h["location_id"]), "count": 0})
                entry["count"] += 1
    hubs = {hub["id"] for hub in market.TRADE_HUBS}
    others = sorted((o for o in owned.values() if o["id"] not in hubs), key=lambda o: (-o["count"], o["name"]))
    can_structures = any(core.SCOPE_STRUCTURE_MARKETS in v.get("scopes", []) for v in store.data.values())
    return jsonify({"hubs": market.TRADE_HUBS, "owned": others, "default": market.DEFAULT_LOCATION_ID,
                    "structure_markets": can_structures})


@app.get("/api/market/resolve")
def api_market_resolve():
    """NPC ステーションの名前（完全一致）→ 場所。"""
    name = request.args.get("name", "").strip()
    if not name:
        return error("ステーション名を入力してください")
    found = core.esi_post("/universe/ids/", [name]).get("stations", [])
    if not found:
        return error(tr("「{0}」という NPC ステーションが見つかりません（名前は完全一致で入力してください）。", name), 404)
    return jsonify({"id": found[0]["id"], "name": found[0]["name"], "kind": "station"})


@app.get("/api/market/prices")
def api_market_prices():
    """指定した場所での最安の売り値・最高の買い値。?location=ID&type_ids=1,2,3"""
    try:
        location_id = market_location_arg()
        type_ids = [int(t) for t in request.args.get("type_ids", "").split(",") if t][:300]
    except ValueError as e:
        return error(str(e))
    try:
        prices = markets.prices(location_id, type_ids)
    except market.MarketError as e:
        return error(str(e), 403)
    except (RuntimeError, requests.RequestException) as e:
        return error(tr("マーケットの取得に失敗しました: {0}", str(e).splitlines()[0]), 502)
    return jsonify({"location": {"id": location_id, "name": location_label(location_id, request.args.get("name"))},
                    "prices": {str(k): v for k, v in prices.items()}})


@app.get("/api/market/orders")
def api_market_orders():
    """指定した場所の、1 アイテムの売り・買いの注文一覧。?location=ID&type_id=X"""
    try:
        location_id = market_location_arg()
        type_id = int(request.args.get("type_id", ""))
    except ValueError:
        return error("location・type_id が不正です")
    try:
        orders = markets.orders(location_id, [type_id])[type_id]
    except market.MarketError as e:
        return error(str(e), 403)
    except (RuntimeError, requests.RequestException) as e:
        return error(tr("マーケットの取得に失敗しました: {0}", str(e).splitlines()[0]), 502)
    ja, en, category = item_label(type_id)
    return jsonify({"location": {"id": location_id, "name": location_label(location_id, request.args.get("name"))},
                    "item": {"type_id": type_id, "ja": ja, "en": en, "category": category},
                    "best": market.summarize(orders), **market.order_view(orders)})


@app.get("/api/characters")
def api_characters():
    """キャラクターの軽い一覧（ホーム・マーケットページ用）。取引スキルのレベル付き。"""
    result = []
    for c in load_characters():
        entry = {"character_id": c["character_id"], "character_name": c["character_name"],
                 "missing": bool(c.get("missing")), "missing_scopes": store.missing_scopes(c["character_id"])}
        if not c.get("missing"):
            levels = {s["skill_id"]: s["trained_level"] for s in c["skills"]}
            queue = c.get("skill_queue") or []
            entry.update(
                total_sp=c.get("total_sp", 0), unallocated_sp=c.get("unallocated_sp", 0),
                fetched_at=c.get("fetched_at"), queue_length=len(queue),
                queue_end=queue[-1].get("finish_date") if queue else None,
                trade_skills={k: levels.get(sid, 0) for k, sid in TRADE_SKILLS.items()},
                industry_skills={k: levels.get(sid, 0) for k, sid in INDUSTRY_SKILLS.items()},
            )
        result.append(entry)
    return jsonify({"characters": result, "groups": load_groups()})


# ---------- 相場の比較 ----------

_item_volumes = {}


def item_volume(type_id):
    """梱包時の体積（m³）。艦は梱包すると小さくなる。"""
    if type_id not in _item_volumes:
        data = core.esi_get(f"/universe/types/{type_id}/")
        _item_volumes[type_id] = data.get("packaged_volume") or data.get("volume") or 0
    return _item_volumes[type_id]


def load_watchlist():
    try:
        return json.loads(accounts.user_file("market_watchlist.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_watchlist(items):
    accounts.user_file("market_watchlist.json").write_text(json.dumps(items), encoding="utf-8")


@app.get("/api/market/watchlist")
def api_watchlist():
    items = []
    for type_id in load_watchlist():
        ja, en, category = item_label(type_id)
        items.append({"type_id": type_id, "ja": ja, "en": en, "category": category})
    return jsonify({"items": items})


@app.post("/api/market/watchlist")
def api_watchlist_add():
    type_id = (request.get_json(silent=True) or {}).get("type_id")
    if not isinstance(type_id, int):
        return error("type_id が必要です")
    items = load_watchlist()
    if type_id not in items:
        items.append(type_id)
        save_watchlist(items)
    return jsonify({"ok": True})


@app.delete("/api/market/watchlist/<int:type_id>")
def api_watchlist_remove(type_id):
    save_watchlist([t for t in load_watchlist() if t != type_id])
    return jsonify({"ok": True})


@app.get("/api/market/compare")
def api_market_compare():
    """複数の場所での最安の売り値・最高の買い値。?type_ids=1,2&locations=60003760,60008494"""
    try:
        type_ids = [int(t) for t in request.args.get("type_ids", "").split(",") if t][:100]
        location_ids = [int(t) for t in request.args.get("locations", "").split(",") if t][:12]
        for location_id in location_ids:
            market.Market.kind(location_id)
    except (ValueError, market.MarketError):
        return error("type_ids・locations が不正です")

    def fetch(location_id):
        try:
            return location_id, markets.prices(location_id, type_ids), None
        except (RuntimeError, requests.RequestException) as e:
            return location_id, {}, str(e).splitlines()[0]

    with ThreadPoolExecutor(max_workers=6) as pool:
        fetched = list(pool.map(fetch, location_ids))

    items = {}
    for type_id in type_ids:
        ja, en, category = item_label(type_id)
        try:
            volume = item_volume(type_id)
        except (RuntimeError, requests.RequestException):
            volume = None
        items[str(type_id)] = {"ja": ja, "en": en, "category": category, "volume": volume}
    return jsonify({
        "items": items,
        "locations": [{"id": loc, "name": location_label(loc)} for loc in location_ids],
        "prices": {str(loc): {str(t): v for t, v in prices.items()} for loc, prices, _ in fetched},
        "errors": {str(loc): err for loc, _, err in fetched if err},
    })


# ---------- おすすめ ----------

_recommender = None


def recommender():
    global _recommender
    if _recommender is None:
        _recommender = Recommender(type_cache, catalog, fitting_data, resolve_eft)
    return _recommender


def user_fit_candidates(characters):
    """このアプリに保存したフィットと、ゲーム内のフィット（おすすめの候補）。"""
    rec = recommender()
    cands = []
    for f in load_saved_fits():
        try:
            cand = rec._from_eft(f["eft"], None, "app", f"app:{f['id']}")
        except (ValueError, KeyError):
            continue
        cand["name"] = f["name"]
        cands.append(cand)
    seen = set()
    for c in characters:
        for f in c.get("fittings") or []:
            type_ids = sorted({f["ship_type_id"], *(i["type_id"] for i in f["items"])})
            key = (f["name"], f["ship_type_id"], tuple(type_ids))
            if key in seen:
                continue
            seen.add(key)
            fitted = fitting.fitted_type_ids(f["items"])
            bay = [(i["type_id"], i["quantity"]) for i in f["items"] if i["flag"] in ("DroneBay", "FighterBay", "Cargo")]
            cands.append({"key": f"game:{len(seen)}", "source": "game", "name": f["name"],
                          "ship_type_id": f["ship_type_id"], "fitted": fitted, "loaded": [None] * len(fitted),
                          "bay": bay, "type_ids": type_ids, "eft": build_eft(f["name"], f["ship_type_id"], f["items"])})
    return cands


def recommend_character():
    try:
        char_id = int(request.args.get("character_id", ""))
    except ValueError:
        return None, error("character_id が必要です")
    characters = ready_characters()
    character = next((c for c in characters if c["character_id"] == char_id), None)
    if not character:
        return None, error("キャラクターが見つかりません", 404)
    return (character, characters), None


@app.get("/api/recommend/fits")
def api_recommend_fits():
    """キャラクターのおすすめフィット（役割ごと・今すぐ／10 日以内）。"""
    found, err = recommend_character()
    if err:
        return err
    character, characters = found
    purpose = request.args.get("purpose") if request.args.get("purpose") in ("pve", "pvp") else None
    roles = recommender().recommend_fits(character, user_fit_candidates(characters), wcs=request.args.get("wcs") == "1",
                                         purpose=purpose)
    type_cache.save()
    # 役割の並び順を保つため配列で返す（辞書だと JSON のキーが並べ替えられる）
    return jsonify({"character_id": character["character_id"], "character_name": character["character_name"],
                    "roles": [{"role": k, **v} for k, v in roles.items()]})


@app.get("/api/recommend/ship-fits")
def api_recommend_ship_fits():
    """1 隻分のフィット（定番・自分のフィット。無ければ役割に合わせて自動で組む）。"""
    found, err = recommend_character()
    if err:
        return err
    character, characters = found
    try:
        type_id = int(request.args.get("type_id", ""))
    except ValueError:
        return error("type_id が必要です")
    ja, en, _ = item_label(type_id)
    result = recommender().fits_for_ship(character, type_id, user_fit_candidates(characters),
                                         wcs=request.args.get("wcs") == "1")
    type_cache.save()
    return jsonify({"character_id": character["character_id"], "type_id": type_id, "ja": ja, "en": en, **result})


@app.get("/api/recommend/ships")
def api_recommend_ships():
    """キャラクターのおすすめ艦船（役割ごと・今乗れる／10 日以内）。"""
    found, err = recommend_character()
    if err:
        return err
    character, _ = found
    if not catalog.ready:
        return error("艦船の名前一覧を作成中です。しばらくしてから開き直してください。", 503)
    roles = recommender().recommend_ships(character)
    type_cache.save()
    return jsonify({"character_id": character["character_id"], "character_name": character["character_name"],
                    "roles": [{"role": k, **v} for k, v in roles.items()]})


# ---------- ワームホール ----------

@app.get("/api/wormhole/types")
def api_wormhole_types():
    """ワームホールの種類（コード → 行き先・寿命・質量）。"""
    try:
        return jsonify({"types": wormholes.types()})
    except (RuntimeError, requests.RequestException) as e:
        return error(tr("ワームホールのデータを取得できませんでした: {0}", str(e).splitlines()[0]), 502)


def character_location(char_id, name):
    """1 人分の今いる星系と搭乗中の艦（ESI から直接）。"""
    entry = {"character_id": char_id, "character_name": name}
    scopes = store.data.get(str(char_id), {}).get("scopes", [])
    if core.SCOPE_LOCATION not in scopes:
        entry["needs_login"] = True
        return entry
    try:
        token = cached_access_token(char_id)
        loc = core.esi_get(f"/characters/{char_id}/location/", token)
        entry["system"] = universe.system(loc["solar_system_id"])
        entry["docked"] = bool(loc.get("station_id") or loc.get("structure_id"))
        if core.SCOPE_SHIP in scopes:
            ship = core.esi_get(f"/characters/{char_id}/ship/", token)
            ja, en, _ = item_label(ship["ship_type_id"])
            entry["ship"] = {"type_id": ship["ship_type_id"], "name": core.clean_ship_name(ship.get("ship_name")),
                             "ja": ja, "en": en}
    except (RuntimeError, requests.RequestException, KeyError) as e:
        entry["error"] = str(e).splitlines()[0]
    return entry


@app.get("/api/wormhole/locations")
def api_wormhole_locations():
    """全キャラクターの今いる星系（J 空間のクラス・セキュリティ）と搭乗中の艦。"""
    chars = store.characters()
    with ThreadPoolExecutor(max_workers=5) as pool:
        result = list(pool.map(lambda c: character_location(*c), chars))
    return jsonify({"characters": result})


@app.get("/api/wormhole/ships")
def api_wormhole_ships():
    """キャラクターの艦の質量（ワームホールを通れるかの判定用）。フィット・所持艦・搭乗中の艦。"""
    found, err = recommend_character()
    if err:
        return err
    character, characters = found
    ships = []

    def add(label, source, ship_type_id, fitted, location=None):
        try:
            masses = wormhole.ship_masses(fitting_data, ship_type_id, fitted)
        except (RuntimeError, requests.RequestException, KeyError):
            return
        ja, en, _ = item_label(ship_type_id)
        ships.append({"label": label, "source": source, "type_id": ship_type_id, "ship_ja": ja, "ship_en": en,
                      "location": location, **masses})

    for f in load_saved_fits():
        resolved = resolve_saved_fit(f)
        if resolved:
            add(f["name"], "保存したフィット", f["ship_type_id"], resolved["fitted"])
    for f in character.get("fittings") or []:
        add(f["name"], "ゲーム内のフィット", f["ship_type_id"], fitting.fitted_type_ids(f["items"]))
    seen = set()
    for h in character.get("hangar") or []:
        item = catalog.get(h["type_id"])
        if item and item["category"] == "艦船" and (h["type_id"], h["location"]) not in seen:
            seen.add((h["type_id"], h["location"]))
            add(item["ja"], "所持艦（装備は含まない）", h["type_id"], [], h["location"])
    fitting_data.save()
    ships.sort(key=lambda s: -s["hot"])
    return jsonify({"character_id": character["character_id"], "ships": ships,
                    "hangar_known": character.get("hangar") is not None})


@app.get("/api/wormhole/ship-mass")
def api_wormhole_ship_mass():
    """艦 1 隻の素の質量（装備なし）。?type_id="""
    try:
        type_id = int(request.args.get("type_id", ""))
        masses = wormhole.ship_masses(fitting_data, type_id, [])
    except ValueError:
        return error("type_id が必要です")
    except (RuntimeError, requests.RequestException, KeyError):
        return error("艦の情報を取得できませんでした", 502)
    fitting_data.save()
    ja, en, _ = item_label(type_id)
    return jsonify({"type_id": type_id, "ship_ja": ja, "ship_en": en, **masses})


@app.post("/api/catalog/rebuild")
def api_rebuild_catalog():
    catalog.build_async(type_cache)
    return jsonify({"catalog": catalog.status})


features.register(app, features.Ctx(
    core=core, store=store, live=live, sde=sde, markets=markets, catalog=catalog, universe=universe,
    item_label=item_label, ready_characters=ready_characters, token=cached_access_token,
    type_cache=type_cache, fitting_data=fitting_data, recommender=lambda: recommender(),
))


# ---------- 起動 ----------

def prepare():
    """起動の準備（ログインの設定・キャッシュ）。問題があればそのメッセージを返す（.exe の起動でも使う）。"""
    global credentials
    try:
        credentials = core.get_credentials()
    except RuntimeError as e:
        return str(e)
    core.migrate_legacy_token(store, credentials)
    if not catalog.ready or catalog.outdated:
        print("アイテムの名前一覧を作成しています（数分かかります）。進み具合は画面に表示されます。")
        catalog.build_async(type_cache)
    if sde.ready and sde.outdated:  # 古い版の静的データは、使いながら裏で作り直す
        print("静的データ（SDE）を新しい版に作り直しています（数分。そのあいだも今のデータで使えます）。")
        sde.build_async()

    if HOST not in ("127.0.0.1", "localhost", "::1") and not app_password():
        return "自分の PC 以外からも開けるように起動するときは、APP_PASSWORD（アカウントを作るときの招待コード）を設定してください。"
    return None


def serve_forever():
    """サーバーを動かす（止まるまで戻らない）。待ち受けられないときは OSError。"""
    # Windows では localhost が先に IPv6（::1）を指すため、IPv4 だけで待ち受けると接続のたびに約 2 秒待たされる。
    # IPv6 のループバックでも待ち受け、使えない環境では IPv4 だけにする。
    if HOST != "127.0.0.1":
        serve(app, host=HOST, port=PORT, threads=8, _quiet=True)
        return
    try:
        serve(app, listen=f"{HOST}:{PORT} [::1]:{PORT}", threads=8, _quiet=True)
    except OSError:
        serve(app, host=HOST, port=PORT, threads=8, _quiet=True)


def main():
    problem = prepare()
    if problem:
        print(f"エラー: {problem}")
        sys.exit(1)
    open_browser = "--no-browser" not in sys.argv and not CLOUD
    # Windows では同じポートで 2 つ目のサーバーが起動できてしまうことがあるので、先に確認する
    if port_in_use(PORT):
        print(f"ポート {PORT} はすでに使われています。スキルチェッカーが起動済みなら、ブラウザで {APP_URL} を開いてください。")
        print("古いバージョンが動いている場合は、そちらを Ctrl+C で止めてから起動し直してください。")
        if open_browser:
            webbrowser.open(APP_URL)
        sys.exit(1)

    print(f"EVE スキルチェッカーを起動しました: {APP_URL}")
    print("終了するには Ctrl+C を押してください。")
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(APP_URL)).start()
    try:
        serve_forever()
    except OSError as e:
        print(f"ポート {PORT} で起動できませんでした（{e}）。")
        sys.exit(1)


def port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1" if HOST == "0.0.0.0" else HOST, port)) == 0


if __name__ == "__main__":
    main()
