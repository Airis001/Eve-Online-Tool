"""追加機能で共通に使うもの（キャラクターの選択・名前の解決・並列取得）。"""

import math
import threading
from dataclasses import dataclass
from typing import Any, Callable

import requests
from flask import jsonify, request

from accounts import ThreadPoolExecutor
from live import safe

JITA_STATION_ID = 60003760
JITA_REGION_ID = 10000002
STATION_IDS = range(60_000_000, 64_000_000)
STRUCTURE_MIN_ID = 1_000_000_000_000


@dataclass
class Ctx:
    core: Any              # fetch_skills
    store: Any             # CharacterStore
    live: Any              # live.Live
    sde: Any               # sde.SdeData
    markets: Any           # market.Market
    catalog: Any           # ItemCatalog
    universe: Any          # wormhole.Universe
    item_label: Callable   # type_id → (ja, en, category)
    ready_characters: Callable
    token: Callable        # char_id → アクセストークン
    type_cache: Any = None     # skill_check.TypeCache
    fitting_data: Any = None   # fitting.FittingData
    recommender: Callable = None  # () → Recommender（DPS の計算などに使う）


def error(message, status=400):
    return jsonify({"error": message}), status


def selected_characters(ctx):
    """?ids=1,2,3 のキャラクター（指定なしは全員）。[(character_id, name)]"""
    all_chars = ctx.store.characters()
    raw = request.args.get("ids", "")
    if not raw:
        return all_chars
    wanted = {int(x) for x in raw.split(",") if x.strip().isdigit()}
    return [c for c in all_chars if c[0] in wanted]


def per_character(chars, fn, workers=5):
    """fn(char_id, name) をキャラクターごとに並列で実行し、[{character_id, character_name, data | エラー}] を返す。"""
    def run(c):
        data, err = safe(fn, *c)
        return {"character_id": c[0], "character_name": c[1], "data": data, **(err or {})}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(run, chars))


_names = {}
_names_lock = threading.Lock()


def resolve_names(ctx, ids):
    """キャラクター・コーポレーション・星系・ステーション・アイテムなどの ID → 名前（公開情報のみ）。"""
    ids = {int(i) for i in ids if i and int(i) < STRUCTURE_MIN_ID}
    with _names_lock:
        todo = sorted(i for i in ids if i not in _names)

    def fetch(chunk):
        try:
            return ctx.core.esi_post("/universe/names/", chunk)
        except (RuntimeError, requests.RequestException):
            if len(chunk) == 1:
                return []
            mid = len(chunk) // 2  # 無効な ID が混ざると全体が 404 になるので半分ずつ試す
            return fetch(chunk[:mid]) + fetch(chunk[mid:])
    for i in range(0, len(todo), 1000):
        for entry in fetch(todo[i:i + 1000]):
            with _names_lock:
                _names[entry["id"]] = entry["name"]
    with _names_lock:
        return {i: _names.get(i) for i in ids}


def location_names(ctx, ids, char_id=None):
    """ステーション・プレイヤー建造物・星系の名前。建造物はそのキャラクターの権限で読む。"""
    ids = {i for i in ids if i}
    token = None
    if char_id and any(i >= STRUCTURE_MIN_ID for i in ids) and ctx.core.SCOPE_STRUCTURES in \
            ctx.store.data.get(str(char_id), {}).get("scopes", []):
        try:
            token = ctx.token(char_id)
        except (RuntimeError, requests.RequestException):
            token = None
    try:
        return ctx.core.resolve_location_names(ids, token)
    except (RuntimeError, requests.RequestException):
        return {}


def type_name(ctx, type_id):
    """(日本語名, 英語名)。名前一覧 → SDE → ESI の順に探す。"""
    item = ctx.catalog.get(type_id)
    if item:
        return item["ja"], item["en"]
    if ctx.sde.ready and type_id in ctx.sde.names:
        return ctx.sde.name(type_id)
    try:
        ja, en, _ = ctx.item_label(type_id)
        return ja, en
    except (RuntimeError, requests.RequestException, KeyError):
        return f"#{type_id}", f"#{type_id}"


def skill_levels(ctx, char_id):
    for c in ctx.ready_characters():
        if c["character_id"] == char_id:
            return {s["skill_id"]: s["trained_level"] for s in c.get("skills", [])}
    return {}


def jita_prices(ctx, type_ids):
    """Jita 4-4 の {type_id: {"sell": 最安の売り値, "buy": 最高の買い値}}（無ければ None）。"""
    prices = ctx.markets.prices(JITA_STATION_ID, list(type_ids))
    return {t: {"sell": (p["sell"] or {}).get("price"), "buy": (p["buy"] or {}).get("price")} for t, p in prices.items()}


def undercut(price):
    """最安の売り注文のすぐ下の、出品できる価格。注文の価格は有効数字 4 桁まで（最小 0.01 ISK 刻み）。"""
    if not price or price <= 0.01:
        return price
    step = max(10 ** (math.floor(math.log10(price * (1 - 1e-9))) - 3), 0.01)
    return round((math.ceil(price / step - 1e-9) - 1) * step, 2)


def average_prices(ctx):
    """CCP の全体の平均価格・調整価格 {type_id: {"average", "adjusted"}}（1 時間キャッシュ）。"""
    rows = ctx.live.public("/markets/prices/", ttl=3600)
    return {r["type_id"]: {"average": r.get("average_price"), "adjusted": r.get("adjusted_price")} for r in rows}


def int_arg(name, default=None, lo=None, hi=None):
    try:
        v = int(request.args.get(name, default))
    except (TypeError, ValueError):
        v = default
    if v is not None:
        if lo is not None:
            v = max(lo, v)
        if hi is not None:
            v = min(hi, v)
    return v


def float_arg(name, default=0.0):
    try:
        return float(request.args.get(name, default))
    except (TypeError, ValueError):
        return default
