"""LP の換金: 持っている LP で、LP ストアのどの交換品を交換して売るのが良いか。

1 LP あたりの利益（交換に必要な ISK・アイテムの代金と、売るときの手数料を引いた後）と、
売り先の地域の直近の取引量・取引件数（ESI のマーケットの履歴）を並べる。
何をどれだけ交換するかの組み合わせ（プラン）は、ページで条件を変えながら計算する。
"""

from datetime import datetime, timedelta, timezone

import requests
from flask import jsonify

from accounts import ThreadPoolExecutor
from i18n import tr
from live import EsiForbidden, ScopeMissing, safe
from market import TRADE_HUBS

from .common import (average_prices, error, int_arg, per_character, resolve_names, selected_characters, skill_levels,
                     type_name)
from .money import standing_reductions

SKILL_ACCOUNTING, SKILL_BROKER_RELATIONS = 16622, 3446
CANDIDATES = 100     # CCP の平均価格で見積もった上位から、実際の価格と取引量を調べる数
RECENT_DAYS = 7      # 「直近の取引」の日数
LISTED_LIMIT = 1.5   # 売り値が実際の取引価格（7 日平均）のこの倍より高ければ、その値段では売れない
INSTANT_LIMIT = 1.3  # 買い値が実際の取引価格のこの倍より高ければ、釣りの買い注文


def register(app, ctx):
    core, live = ctx.core, ctx.live
    hubs = {h["id"]: h for h in TRADE_HUBS}

    def fees(char_id, station_id):
        """(売上税 %, 仲介手数料 %)。仲介手数料は NPC ステーションならスタンディングで下げる。"""
        lv = skill_levels(ctx, char_id)
        tax = 7.5 * (1 - 0.11 * lv.get(SKILL_ACCOUNTING, 0))
        broker = 3.0 - 0.3 * lv.get(SKILL_BROKER_RELATIONS, 0)
        try:
            st, _ = standing_reductions(ctx, char_id, [station_id])
            broker -= st.get(station_id, {}).get("reduction", 0)
        except (ScopeMissing, EsiForbidden, RuntimeError, requests.RequestException):
            pass
        return max(tax, 0), max(broker, 0)

    def best_trader():
        def key(c):
            lv = {s["skill_id"]: s["trained_level"] for s in c.get("skills", [])}
            return (lv.get(SKILL_BROKER_RELATIONS, 0), lv.get(SKILL_ACCOUNTING, 0))
        chars = ctx.ready_characters()
        return max(chars, key=key) if chars else None

    def history(region, type_id):
        """直近 7 日の 1 日あたりの取引量・取引件数と、平均価格（取引量で重み付け）。"""
        rows, _ = safe(live.public, f"/markets/{region}/history/", 3600, {"type_id": type_id})
        if rows is None:
            return None
        cutoff = (datetime.now(timezone.utc) - timedelta(days=RECENT_DAYS)).date().isoformat()
        recent = [r for r in rows if r["date"] >= cutoff]  # 取引の無い日は履歴に無いので、日付で区切る
        volume = sum(r["volume"] for r in recent)
        return {"volume": volume / RECENT_DAYS, "orders": sum(r["order_count"] for r in recent) / RECENT_DAYS,
                "average": sum(r["average"] * r["volume"] for r in recent) / volume if volume else None}

    @app.get("/api/lp/corps")
    def api_lp_corps():
        """選んだキャラクターが LP を持っているコーポレーション（LP の多い順）と、売り先に選べる交易ハブ。"""
        def load(cid, name):
            return live.get(cid, f"/characters/{cid}/loyalty/points/", core.SCOPE_LOYALTY, ttl=600)

        rows = per_character(selected_characters(ctx), load)
        corps, chars = {}, []
        for r in rows:
            data = r.pop("data")
            chars.append(r)
            for lp in data or []:
                if lp["loyalty_points"] <= 0:
                    continue
                entry = corps.setdefault(lp["corporation_id"], {"corporation_id": lp["corporation_id"], "total": 0,
                                                                "by_character": []})
                entry["total"] += lp["loyalty_points"]
                entry["by_character"].append({"character_id": r["character_id"], "character_name": r["character_name"],
                                              "points": lp["loyalty_points"]})
        # LP を持っていないコーポの LP ストアも見られるように（どこの仕事をするか決めるとき用）
        npc, _ = safe(live.public, "/corporations/npccorps/", 86400)
        others = [c for c in npc or [] if c not in corps]
        names = resolve_names(ctx, [*corps, *others])
        result = [{**e, "name": names.get(c) or str(c)} for c, e in corps.items()]
        result.sort(key=lambda e: -e["total"])
        others = sorted(({"corporation_id": c, "name": names.get(c) or str(c), "total": 0, "by_character": []}
                         for c in others), key=lambda e: e["name"].lower())
        return jsonify({"characters": chars, "corporations": result, "others": others,
                        "hubs": [{"station_id": h["id"], "name": h["short"]} for h in TRADE_HUBS]})

    @app.get("/api/lp/store")
    def api_lp_store():
        """コーポレーションの LP ストアの交換品を、売り先のハブの価格・取引量で評価する。"""
        corp_id = int_arg("corp_id")
        hub_id = int_arg("hub", TRADE_HUBS[0]["id"])
        if not corp_id:
            return error(tr("コーポレーションを選んでください。"))
        hub = hubs.get(hub_id) or TRADE_HUBS[0]
        try:
            offers = live.public(f"/loyalty/stores/{corp_id}/offers/", ttl=86400)
        except (RuntimeError, requests.RequestException) as e:
            return error(tr("LP ストアを取得できませんでした: {0}", str(e).splitlines()[0]), 502)
        try:
            avg = average_prices(ctx)
        except (RuntimeError, requests.RequestException):
            avg = {}

        # 設計図（BPC）はマーケットで売られている BPO とは別物なので、価格で評価できない
        skipped = 0
        cands = []
        for o in offers:
            if not o.get("lp_cost") or type_name(ctx, o["type_id"])[1].endswith("Blueprint"):
                skipped += 1
                continue
            estimate = (avg.get(o["type_id"], {}).get("average") or 0) * o["quantity"] - o.get("isk_cost", 0) \
                - sum((avg.get(i["type_id"], {}).get("average") or 0) * i["quantity"] for i in o.get("required_items", []))
            cands.append((estimate / o["lp_cost"], o))
        cands.sort(key=lambda c: -c[0])
        cands = [o for _, o in cands[:CANDIDATES]]

        ids = {o["type_id"] for o in cands} | {i["type_id"] for o in cands for i in o.get("required_items", [])}
        try:
            prices = ctx.markets.prices(hub["id"], list(ids)) if ids else {}
        except (RuntimeError, requests.RequestException) as e:
            return error(tr("マーケットの取得に失敗しました: {0}", str(e).splitlines()[0]), 502)
        with ThreadPoolExecutor(max_workers=10) as pool:
            hist = dict(zip((o["type_id"] for o in cands), pool.map(lambda o: history(hub["region_id"], o["type_id"]), cands)))

        trader = best_trader()
        tax, broker = fees(trader["character_id"], hub["id"]) if trader else (7.5, 3.0)

        def best(t, side):
            return ((prices.get(t) or {}).get(side) or {}).get("price")

        result = []
        for o in cands:
            t = o["type_id"]
            ja, en = type_name(ctx, t)
            req = []
            for i in o.get("required_items", []):
                rja, ren = type_name(ctx, i["type_id"])
                req.append({"type_id": i["type_id"], "quantity": i["quantity"], "ja": rja, "en": ren,
                            "price": best(i["type_id"], "sell")})
            req_cost = sum((i["price"] or 0) * i["quantity"] for i in req)
            h = hist.get(t) or {}
            sell, buy, average = best(t, "sell"), best(t, "buy"), h.get("average")
            listed_out = bool(sell and average and sell > average * LISTED_LIMIT)
            instant_out = bool(buy and average and buy > average * INSTANT_LIMIT)
            cost = o.get("isk_cost", 0) + req_cost
            # 1 回の交換の手取り。売り注文は最安より 0.01 ISK 安く出す（売上税 + 仲介手数料）、すぐ売るは買い注文へ（売上税のみ）
            listed = (sell - 0.01) * (1 - (tax + broker) / 100) * o["quantity"] - cost if sell and not listed_out else None
            instant = buy * (1 - tax / 100) * o["quantity"] - cost if buy and not instant_out else None
            result.append({
                "offer_id": o["offer_id"], "type_id": t, "ja": ja, "en": en, "quantity": o["quantity"],
                "lp_cost": o["lp_cost"], "isk_cost": o.get("isk_cost", 0), "required": req,
                "missing_required": any(i["price"] is None for i in req), "cost": cost,
                "sell": sell, "buy": buy, "average": average, "listed_out": listed_out, "instant_out": instant_out,
                "listed": listed, "instant": instant,
                "volume": h.get("volume"), "orders": h.get("orders"),
            })
        names = resolve_names(ctx, [corp_id])
        return jsonify({"corporation_id": corp_id, "name": names.get(corp_id) or str(corp_id), "hub": hub["short"],
                        "hub_id": hub["id"], "trader": trader["character_name"] if trader else None,
                        "tax": tax, "broker": broker, "offers": result, "total_offers": len(offers),
                        "skipped": skipped, "candidates": CANDIDATES, "recent_days": RECENT_DAYS})
