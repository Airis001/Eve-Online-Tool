"""ハブ間の転売: 交易ハブ（Jita など）で売り注文から買い、別のハブで売ると利益が出る品目を探す。

2 つの地域の全注文を読み込み、仕入れ先のステーションの最安の売り値と、売り先のステーションの
最高の買い値（すぐ売る）・最安の売り値（売り注文を出す）を比べる。売り先の 7 日の取引量で、
実際に売れているか・価格がおかしくないか（釣りの注文）を確かめる。
"""

import contextvars
import threading
from datetime import datetime, timedelta, timezone

import requests
from flask import jsonify, request

import accounts
from accounts import ThreadPoolExecutor
from live import EsiForbidden, ScopeMissing, safe

from .common import error, skill_levels, type_name
from .money import standing_reductions

# 交易ハブ: ステーション ID → (名前, 地域 ID)
HUBS = {
    60003760: ("Jita", 10000002),     # Jita IV - Moon 4 - Caldari Navy Assembly Plant
    60008494: ("Amarr", 10000043),    # Amarr VIII (Oris) - Emperor Family Academy
    60011866: ("Dodixie", 10000032),  # Dodixie IX - Moon 20 - Federation Navy Assembly Plant
    60004588: ("Rens", 10000030),     # Rens VI - Moon 8 - Brutor Tribe Treasury
    60005686: ("Hek", 10000042),      # Hek VIII - Moon 12 - Boundless Creation Factory
}
SKILL_ACCOUNTING, SKILL_BROKER_RELATIONS = 16622, 3446
MAX_MARGIN = 300        # これより大きい利益率は、ありえない価格の注文（釣り）がほとんど
MIN_VOLUME = 5          # 売り先の 1 日の取引量（7 日平均）の下限
SHARE = 0.1             # 1 日に売れる見込み = 売り先の取引量の 1 割
CANDIDATES = 300        # 取引量を調べる候補の数（利益の額の順・利益率の順でそれぞれ）
ACTIVE_ORDERS = 20      # 注文の件数はここまでで頭打ち（売買の活発さの目安）
RESULTS = 150
SAME_PRICE = 1.02       # 仕入れの「最安の売り値」とみなす幅（最安 + 2% までの注文の数量を足す）
FRESH = timedelta(minutes=15)
RECENT_DAYS = 2         # 「直近の取引件数」の日数

_jobs = {}
_lock = threading.Lock()


def job():
    """いまのアカウントのジョブ。"""
    return _jobs.setdefault(accounts.current_uid(), {"state": "idle", "progress": 0, "at": None, "result": None, "error": None})


def register(app, ctx):
    core, live = ctx.core, ctx.live

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
        """トレードスキル（Broker Relations → Accounting）が一番高いキャラクター。"""
        def key(c):
            lv = {s["skill_id"]: s["trained_level"] for s in c.get("skills", [])}
            return (lv.get(SKILL_BROKER_RELATIONS, 0), lv.get(SKILL_ACCOUNTING, 0))
        chars = ctx.ready_characters()
        return max(chars, key=key) if chars else None

    def station_book(region, station, progress):
        """地域の全注文から、そのステーションの品目ごとの最安の売り値・最高の買い値・件数。"""
        first, headers = core._esi_request("GET", f"/markets/{region}/orders/", params={"order_type": "all", "page": 1},
                                           with_headers=True)
        pages = int(headers.get("X-Pages", 1))
        orders = list(first)
        done = [1]

        def page(n):
            data = core._esi_request("GET", f"/markets/{region}/orders/", params={"order_type": "all", "page": n})
            done[0] += 1
            progress(done[0] / pages)
            return data
        with ThreadPoolExecutor(max_workers=12) as pool:
            for data in pool.map(page, range(2, pages + 1)):
                orders += data
        book = {}
        for o in orders:
            if o["location_id"] != station:
                continue
            b = book.setdefault(o["type_id"], {"sell": None, "buy": None, "sell_orders": 0, "buy_orders": 0, "sells": []})
            if o["is_buy_order"]:
                b["buy_orders"] += 1
                b["buy"] = max(b["buy"] or 0, o["price"])
            else:
                b["sell_orders"] += 1
                b["sell"] = o["price"] if b["sell"] is None else min(b["sell"], o["price"])
                b["sells"].append((o["price"], o["volume_remain"]))
        for b in book.values():  # 最安に近い値段で買える数量
            b["sell_qty"] = sum(q for p, q in b.pop("sells") if b["sell"] and p <= b["sell"] * SAME_PRICE)
        return book, len(orders)

    def history(region, type_id):
        """(7 日の 1 日の平均取引量, 平均価格, 直近 2 日の取引件数, 直近 2 日の取引数量)。

        取引件数は ESI の履歴の order_count（その日に成立した取引の数）。履歴は取引の無い日が抜けるので、日付で区切る。
        """
        rows, _ = safe(live.public, f"/markets/{region}/history/", 3600, {"type_id": type_id})
        rows = rows or []
        cutoff = (datetime.now(timezone.utc) - timedelta(days=RECENT_DAYS)).date().isoformat()
        recent = [r for r in rows if r["date"] >= cutoff]
        rows = rows[-7:]
        volume = sum(r["volume"] for r in rows)
        return (volume / 7 if volume else 0, sum(r["average"] * r["volume"] for r in rows) / volume if volume else None,
                sum(r["order_count"] for r in recent), sum(r["volume"] for r in recent))

    def build(src, dst, min_price, min_margin, cargo):
        j = job()
        try:
            src_book, n_src = station_book(HUBS[src][1], src, lambda f: j.update(progress=int(f * 40)))
            dst_book, n_dst = station_book(HUBS[dst][1], dst, lambda f: j.update(progress=40 + int(f * 40)))
            trader = best_trader()
            tax, broker = fees(trader["character_id"], dst) if trader else (7.5, 3.0)
            cands = []
            for t, s in src_book.items():
                d = dst_book.get(t)
                if not d or not s["sell"] or s["sell"] < min_price:
                    continue
                cost = s["sell"]  # 売り注文から買う（手数料なし）
                instant = d["buy"] * (1 - tax / 100) - cost if d["buy"] else None
                listed = (d["sell"] - 0.01) * (1 - (tax + broker) / 100) - cost if d["sell"] else None
                profit = max(p for p in (instant, listed) if p is not None) if instant is not None or listed is not None else None
                if profit is None or not min_margin <= profit / cost * 100 <= MAX_MARGIN:
                    continue
                cands.append({"type_id": t, "cost": cost, "src_qty": s["sell_qty"], "src_orders": s["sell_orders"],
                              "dst_sell": d["sell"], "dst_buy": d["buy"], "dst_sell_orders": d["sell_orders"],
                              "dst_buy_orders": d["buy_orders"], "instant": instant, "listed": listed, "profit": profit})
            # 取引量を調べる前の絞り込み: 注文が多い（売買が活発な）もののうち、利益の額が大きいものと、利益率が高いもの。
            # 額だけで選ぶと、高くてほとんど売れない品目ばかりになる
            def activity(c):
                return min(max(c["dst_sell_orders"], c["dst_buy_orders"]), c["src_orders"], ACTIVE_ORDERS)
            first = len(cands)
            by_profit = sorted(cands, key=lambda c: -c["profit"] * activity(c))[:CANDIDATES]
            by_margin = sorted(cands, key=lambda c: -c["profit"] / c["cost"] * activity(c))[:CANDIDATES]
            cands = list({c["type_id"]: c for c in by_profit + by_margin}.values())
            done = [0]

            def check(c):
                c["volume"], c["average"], c["recent_orders"], c["recent_volume"] = history(HUBS[dst][1], c["type_id"])
                done[0] += 1
                j["progress"] = 80 + int(done[0] / max(len(cands), 1) * 15)
                return c
            with ThreadPoolExecutor(max_workers=10) as pool:
                cands = list(pool.map(check, cands))
            items = []
            for c in cands:
                avg = c["average"]
                if c["volume"] < MIN_VOLUME or not avg:
                    continue
                # 売り先の売り値が実際の取引価格よりずっと高いなら、その値段では売れない（売り注文は数えない）
                if c["listed"] is not None and c["dst_sell"] > avg * 1.5:
                    c["listed"] = None
                # すぐ売る値段が実際の取引価格よりずっと高いのは、釣りの買い注文
                if c["instant"] is not None and c["dst_buy"] > avg * 1.3:
                    c["instant"] = None
                options = [p for p in (c["instant"], c["listed"]) if p is not None]
                if not options or max(options) <= 0 or max(options) / c["cost"] * 100 < min_margin:
                    continue
                c["profit"] = max(options)
                c["method"] = "instant" if c["instant"] is not None and c["instant"] >= c["profit"] else "listed"
                c["margin"] = c["profit"] / c["cost"] * 100
                c["units"] = min(max(c["volume"] * SHARE, 1), c["src_qty"])  # 1 日に回せる数量の目安（少なくとも 1 個）
                c["potential"] = c["profit"] * c["units"]
                items.append(c)
            items.sort(key=lambda c: -c["potential"])
            items = items[:RESULTS]

            def size(c):
                info, _ = safe(live.public, f"/universe/types/{c['type_id']}/", 86400 * 7)
                c["m3"] = (info or {}).get("packaged_volume") or (info or {}).get("volume")
                c["ja"], c["en"] = type_name(ctx, c["type_id"])
                return c
            with ThreadPoolExecutor(max_workers=10) as pool:
                items = list(pool.map(size, items))
            for c in items:
                c["per_m3"] = c["profit"] / c["m3"] if c["m3"] else None
                if cargo and c["m3"]:  # カーゴいっぱいに積んだときの数量・利益（1 日に売れる見込みまで）
                    c["load"] = int(min(cargo // c["m3"], max(c["units"], 1)))
                    c["load_profit"] = c["load"] * c["profit"]
            j.update(state="ready", progress=100, at=datetime.now(timezone.utc).isoformat(), error=None,
                     result={"items": items, "tax": tax, "broker": broker, "trader": trader and trader["character_name"],
                             "orders": n_src + n_dst, "compared": first, "checked": len(cands), "src": src, "dst": dst, "cargo": cargo,
                             "src_name": HUBS[src][0], "dst_name": HUBS[dst][0]})
        except Exception as e:  # noqa: BLE001 - 失敗は画面に出す
            j.update(state="error", error=str(e).splitlines()[0] if str(e) else repr(e))

    @app.get("/api/haul/hubs")
    def api_haul_hubs():
        return jsonify({"hubs": [{"station_id": s, "name": n} for s, (n, _) in HUBS.items()]})

    @app.post("/api/haul")
    def api_haul_start():
        body = request.get_json(silent=True) or {}
        try:
            src, dst = int(body.get("src")), int(body.get("dst"))
            min_price = float(body.get("min_price") or 0)
            min_margin = float(body.get("min_margin") or 0)
            cargo = float(body.get("cargo") or 0)
        except (TypeError, ValueError):
            return error("条件の値が正しくありません")
        if src not in HUBS or dst not in HUBS or src == dst:
            return error("仕入れ先と売り先に、ちがう交易ハブを選んでください")
        params = {"src": src, "dst": dst, "min_price": min_price, "min_margin": min_margin, "cargo": cargo}
        j = job()
        with _lock:
            if j["state"] == "running":
                return jsonify(j)
            fresh = j["state"] == "ready" and j["at"] and datetime.now(timezone.utc) - datetime.fromisoformat(j["at"]) < FRESH
            if fresh and j.get("params") == params:
                return jsonify(j)
            j.update(state="running", progress=0, error=None, params=params)
        # スレッドの中でも、どのアカウントのジョブかが分かるようにする
        threading.Thread(target=contextvars.copy_context().run, args=(build, src, dst, min_price, min_margin, cargo),
                         daemon=True).start()
        return jsonify(j)

    @app.get("/api/haul")
    def api_haul():
        return jsonify(job())
