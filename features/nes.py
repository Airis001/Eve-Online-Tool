"""PLEX とニューエデンストア: ストアの商品（バンドル含む）を PLEX で買ってマーケットで売るのと、PLEX をそのまま売るのとで
どちらが得かを比べる。

ストアの商品と PLEX での価格は ESI に無いので、ページで登録してもらう（nes_offers.json）。
PLEX の価格は全宇宙共通の PLEX マーケット（ESI の地域 19000001）、商品の価格は Jita 4-4。
"""

import json
import re
import secrets
import threading
from datetime import datetime, timezone

import requests
from flask import jsonify, request

import accounts
from accounts import ThreadPoolExecutor
from i18n import tr
from live import safe

from .common import JITA_REGION_ID, JITA_STATION_ID, error, jita_prices, type_name
from .money import standing_reductions
from .tools import clean_name, parse_qty

PLEX_TYPE_ID = 44992
PLEX_REGION_ID = 19000001  # PLEX は全宇宙共通のマーケットで取引される
# よく売られる（マーケットで売れる）商品。価格はストアで変わるので、ページで入力してもらう
COMMON_ITEMS = ["Large Skill Injector", "Skill Extractor", "Multiple Pilot Training Certificate", "Daily Alpha Injector",
                "Mini Skill Injector", "Small Skill Injector"]
_lock = threading.Lock()


def offers_file():
    return accounts.user_file("nes_offers.json")


def load_offers():
    try:
        return json.loads(offers_file().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_offers(offers):
    offers_file().write_text(json.dumps(offers, ensure_ascii=False, indent=2), encoding="utf-8")


def register(app, ctx):
    core, catalog = ctx.core, ctx.catalog

    def plex_market():
        """PLEX の最安の売り値・最高の買い値（全ページ）。"""
        first, headers = core._esi_request("GET", f"/markets/{PLEX_REGION_ID}/orders/",
                                           params={"type_id": PLEX_TYPE_ID, "order_type": "all", "page": 1}, with_headers=True)
        orders = list(first)
        for page in range(2, int(headers.get("X-Pages", 1)) + 1):
            orders += core._esi_request("GET", f"/markets/{PLEX_REGION_ID}/orders/",
                                        params={"type_id": PLEX_TYPE_ID, "order_type": "all", "page": page})
        sells = [o["price"] for o in orders if not o["is_buy_order"]]
        buys = [o["price"] for o in orders if o["is_buy_order"]]
        return {"sell": min(sells) if sells else None, "buy": max(buys) if buys else None, "orders": len(orders)}

    def parse_items(text):
        """「名前 x数量」「名前\\t数量」「数量 名前」の行 → [[type_id, 数量]]、見つからない名前。"""
        items, unknown = {}, []
        for line in (text or "").splitlines():
            line = line.strip()
            if not line:
                continue
            cols = [c.strip() for c in line.split("\t")]
            name, qty = cols[0], 1
            if len(cols) > 1 and parse_qty(cols[1]) is not None:
                qty = parse_qty(cols[1])
            else:
                m = re.match(r"^(.*?)\s*[x×]\s?([\d,]+)$", line) or re.match(r"^([\d,]+)\s*[x×]?\s+(.*)$", line)
                if m:
                    a, b = m.groups()
                    name, qty = (a, parse_qty(b)) if parse_qty(b) is not None else (b, parse_qty(a))
            name = clean_name(name)
            t = catalog.find_by_name(name)
            if not t:
                found = ctx.type_cache.resolve_names([name])
                t = found[name][0] if name in found else None
            if t:
                items[t] = items.get(t, 0) + max(qty or 1, 1)
            else:
                unknown.append(name)
        return [[t, q] for t, q in items.items()], unknown

    def trader_fees():
        """トレードスキルが一番高いキャラクターの売上税・仲介手数料（Jita）。"""
        chars = ctx.ready_characters()
        if not chars:
            return None, 7.5, 3.0
        def lv(c):
            return {s["skill_id"]: s["trained_level"] for s in c.get("skills", [])}
        best = max(chars, key=lambda c: (lv(c).get(3446, 0), lv(c).get(16622, 0)))
        levels = lv(best)
        tax = 7.5 * (1 - 0.11 * levels.get(16622, 0))
        broker = 3.0 - 0.3 * levels.get(3446, 0)
        reduction, _ = safe(standing_reductions, ctx, best["character_id"], [JITA_STATION_ID])
        if reduction:
            broker -= reduction[0].get(JITA_STATION_ID, {}).get("reduction", 0)
        return best["character_name"], max(tax, 0), max(broker, 0)

    @app.get("/api/nes")
    def api_nes():
        try:
            plex = plex_market()
        except (RuntimeError, requests.RequestException) as e:
            return error(tr("PLEX の価格を取得できませんでした: {0}", str(e).splitlines()[0]), 502)
        trader, tax, broker = trader_fees()
        offers = load_offers()
        ids = {t for o in offers for t, _ in o["items"]}
        try:
            prices = jita_prices(ctx, ids) if ids else {}
        except (RuntimeError, requests.RequestException) as e:
            return error(tr("商品の価格を取得できませんでした: {0}", str(e).splitlines()[0]), 502)

        def volume(t):
            rows, _ = safe(ctx.live.public, f"/markets/{JITA_REGION_ID}/history/", 3600, {"type_id": t})
            rows = (rows or [])[-7:]
            return t, sum(r["volume"] for r in rows) / 7 if rows else None
        with ThreadPoolExecutor(max_workers=8) as pool:
            volumes = dict(pool.map(volume, ids))
        plex_rows, _ = safe(ctx.live.public, f"/markets/{PLEX_REGION_ID}/history/", 3600, {"type_id": PLEX_TYPE_ID})
        plex_rows = (plex_rows or [])[-7:]
        plex_volume = sum(r["volume"] for r in plex_rows) / 7 if plex_rows else None
        # PLEX 1 個を売ったときの手取り
        plex_instant = plex["buy"] * (1 - tax / 100) if plex["buy"] else None
        plex_list = (plex["sell"] - 0.01) * (1 - (tax + broker) / 100) if plex["sell"] else None
        results = []
        for o in offers:
            rows, inst, lst, missing = [], 0.0, 0.0, 0
            for t, q in o["items"]:
                p = prices.get(t, {})
                ja, en = type_name(ctx, t)
                i_net = p["buy"] * (1 - tax / 100) * q if p.get("buy") else None
                l_net = (p["sell"] - 0.01) * (1 - (tax + broker) / 100) * q if p.get("sell") else None
                if i_net is None and l_net is None:
                    missing += 1
                inst += i_net or 0
                lst += l_net or 0
                rows.append({"type_id": t, "ja": ja, "en": en, "qty": q, "buy": p.get("buy"), "sell": p.get("sell"),
                             "instant": i_net, "list": l_net, "daily_volume": volumes.get(t)})
            n = o["plex"] or 0
            via_plex_instant = n * plex_instant if plex_instant else None
            via_plex_list = n * plex_list if plex_list else None
            # ループ: ISK で PLEX を買う → 商品を買う → 売る。PLEX の買い方 × 商品の売り方の 4 通り
            cost_instant = n * plex["sell"] if plex["sell"] else None                        # 売り注文から即買い（手数料なし）
            cost_order = n * plex["buy"] * (1 + broker / 100) if plex["buy"] else None       # 買い注文を出す（仲介手数料）
            loops = []
            for buy_label, cost in (("PLEX を即買い", cost_instant), ("PLEX を買い注文で", cost_order)):
                for sell_label, net in (("商品を売り注文で", lst), ("商品を即売り", inst)):
                    if cost and net:
                        loops.append({"buy": buy_label, "sell": sell_label, "cost": cost, "net": net,
                                      "profit": net - cost, "roi": (net - cost) / cost * 100})
            best_loop = max(loops, key=lambda x: x["profit"]) if loops else None
            # 1 日に回せる回数の目安: 各品目の 1 日の取引量の 1 割を売れるとして、一番少ない品目で決まる
            shares = [(volumes.get(t) or 0) * 0.1 / q for t, q in o["items"] if q]
            if n and plex_volume:  # PLEX の買い付けも 1 日の取引量の 1 割まで
                shares.append(plex_volume * 0.1 / n)
            per_day = min(shares) if shares and all(s > 0 for s in shares) else None
            results.append({
                **o, "rows": rows, "missing": missing, "items_instant": inst, "items_list": lst,
                "plex_instant": via_plex_instant, "plex_list": via_plex_list,
                "per_plex_instant": inst / n if n else None, "per_plex_list": lst / n if n else None,
                "gain_instant": inst - via_plex_instant if via_plex_instant is not None else None,
                "gain_list": lst - via_plex_list if via_plex_list is not None else None,
                "loops": loops, "best_loop": best_loop, "loops_per_day": per_day,
                "loop_profit_per_day": best_loop["profit"] * per_day if best_loop and per_day and best_loop["profit"] > 0 else None,
            })
        results.sort(key=lambda r: -((r["per_plex_list"] or 0) / (plex_list or 1)))
        return jsonify({"plex": {**plex, "net_instant": plex_instant, "net_list": plex_list},
                        "trader": trader, "tax": tax, "broker": broker, "offers": results,
                        "common": [{"en": n, "type_id": catalog.find_by_name(n), "ja": (catalog.get(catalog.find_by_name(n)) or {}).get("ja", n)}
                                   for n in COMMON_ITEMS]})

    @app.post("/api/nes/offers")
    def api_nes_save():
        body = request.get_json(silent=True) or {}
        name = str(body.get("name") or "").strip()[:100]
        try:
            plex = float(body.get("plex"))
        except (TypeError, ValueError):
            return error("PLEX の価格を入力してください")
        if plex <= 0:
            return error("PLEX の価格を入力してください")
        items, unknown = parse_items(body.get("text", ""))
        if unknown:
            return error(tr("分からない名前があります: {0}", '、'.join(unknown)))
        if not items:
            return error("中身（アイテムと数量）を入力してください")
        with _lock:
            offers = load_offers()
            oid = body.get("id") or secrets.token_hex(4)
            entry = {"id": oid, "name": name or type_name(ctx, items[0][0])[0], "plex": plex, "items": items,
                     "text": body.get("text", ""), "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            offers = [o for o in offers if o["id"] != oid] + [entry]
            save_offers(offers)
        return jsonify(entry)

    @app.delete("/api/nes/offers/<oid>")
    def api_nes_delete(oid):
        with _lock:
            save_offers([o for o in load_offers() if o["id"] != oid])
        return jsonify({"ok": True})
