"""資産の一覧（全キャラクター）と、やることリスト（対応が必要なもののまとめ）。"""

from datetime import datetime, timedelta, timezone

import requests
from flask import copy_current_request_context, jsonify

from accounts import ThreadPoolExecutor
from i18n import item_name, tr

from .common import average_prices, location_names, per_character, selected_characters, type_name


def parse_time(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def register(app, ctx):
    core, live = ctx.core, ctx.live

    # ---------- 2. 資産の一覧 ----------

    @app.get("/api/assets")
    def api_assets():
        def load(cid, name):
            return live.get(cid, f"/characters/{cid}/assets/", core.SCOPE_ASSETS, ttl=3600, pages=True)

        rows = per_character(selected_characters(ctx), load, workers=3)
        try:
            prices = average_prices(ctx)
        except (RuntimeError, requests.RequestException):
            prices = {}
        items, locations, chars = [], {}, []
        for r in rows:
            data = r.pop("data")
            chars.append(r)
            if not data:
                continue
            by_item = {a["item_id"]: a for a in data}

            def root(a):  # 艦・コンテナの中のものは、一番外側の場所（ステーション・建造物・星系）へ
                inside = None
                for _ in range(10):
                    parent = by_item.get(a["location_id"])
                    if not parent:
                        break
                    inside = parent
                    a = parent
                return a["location_id"], inside
            grouped = {}
            for a in data:
                loc, inside = root(a)
                key = (loc, a["type_id"], inside["type_id"] if inside else None)
                grouped[key] = grouped.get(key, 0) + a.get("quantity", 1)
            names = location_names(ctx, {k[0] for k in grouped}, r["character_id"])
            for (loc, t, inside_type), qty in grouped.items():
                value = ((prices.get(t) or {}).get("average") or 0) * qty
                ja, en = type_name(ctx, t)
                items.append({"character_id": r["character_id"], "character_name": r["character_name"], "location_id": loc,
                              "type_id": t, "ja": ja, "en": en, "qty": qty, "value": value,
                              "inside": type_name(ctx, inside_type)[0] if inside_type else None})
                entry = locations.setdefault(loc, {"location_id": loc, "name": names.get(loc) or str(loc), "value": 0.0,
                                                   "count": 0, "characters": set()})
                entry["value"] += value
                entry["count"] += 1
                entry["characters"].add(r["character_name"])
        for loc in locations.values():
            loc["characters"] = sorted(loc["characters"])
        for it in items:
            it["location"] = locations[it["location_id"]]["name"]
        return jsonify({"characters": chars, "items": sorted(items, key=lambda i: -i["value"]),
                        "locations": sorted(locations.values(), key=lambda l: -l["value"]),
                        "total": sum(l["value"] for l in locations.values())})

    # ---------- 1. やることリスト ----------

    def call(endpoint):
        """同じアプリの API を呼んで結果（dict）を返す。失敗したら None。"""
        @copy_current_request_context
        def run():
            try:
                res = app.view_functions[endpoint]()
                res = res[0] if isinstance(res, tuple) else res
                return res.get_json() if res.status_code == 200 else None
            except Exception:  # noqa: BLE001 - 1 つ失敗しても他は出す
                return None
        return run

    @app.get("/api/todo")
    def api_todo():
        endpoints = {"jobs": "api_industry_jobs", "orders": "api_my_orders", "contracts": "api_wallet_contracts",
                     "pi": "api_pi_colonies", "clones": "api_travel_clones"}
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = {k: pool.submit(call(v)) for k, v in endpoints.items()}
            results = {k: f.result() for k, f in futures.items()}
        now = datetime.now(timezone.utc)
        items = []

        def add(level, category, char, text, link, key):
            items.append({"level": level, "category": category, "character_name": char, "text": text, "link": link, "key": key})

        # スキルキュー（保存データ）
        for c in ctx.ready_characters():
            queue = c.get("skill_queue") or []
            ends = [parse_time(q.get("finish_date")) for q in queue if q.get("finish_date")]
            end = max(ends) if ends else None
            if not end or end <= now:
                add("high", "スキル", c["character_name"], "スキルキューが空です", "/skills", f"queue-empty:{c['character_id']}")
            elif end - now < timedelta(hours=24):
                hours = (end - now).total_seconds() / 3600
                add("mid", "スキル", c["character_name"], tr("スキルキューがあと {0:.0f} 時間で空きます", hours),
                    "/skills", f"queue-soon:{c['character_id']}:{end.date()}")
        # 生産ジョブ
        for j in (results["jobs"] or {}).get("jobs", []):
            end = parse_time(j["end_date"])
            if j["status"] == "ready" or (j["status"] == "active" and end <= now):
                add("high", "生産", j["character_name"], tr("{0}「{1}」が完了（受け取り待ち）", j['activity'], j.get('product') or j['blueprint']),
                    "/industry", f"job:{j['job_id']}")
        # マーケットの注文
        for o in (results["orders"] or {}).get("orders", []):
            if o.get("beaten"):
                add("mid", "マーケット", o["character_name"], tr("{0}注文「{1}」が他の注文に{2}います", '買い' if o['is_buy_order'] else '売り', item_name(o), '上回られて' if o['is_buy_order'] else '下回られて'),
                    "/market", f"order-beaten:{o['order_id']}:{o['price']}")
            if o.get("days_left") is not None and o["days_left"] < 1:
                add("mid", "マーケット", o["character_name"], tr("注文「{0}」の期限があと 1 日未満です", item_name(o)), "/market", f"order-exp:{o['order_id']}")
        # 契約
        for c in (results["contracts"] or {}).get("contracts", []):
            if not c.get("active"):
                continue
            left = parse_time(c["date_expired"]) - now
            if left < timedelta(hours=24):
                add("mid", "契約", c["character_name"], tr("{0}の契約{1}の期限があと {2:.0f} 時間です", c['type_label'], ('「' + c['title'] + '」') if c.get('title') else '', (max(left.total_seconds() / 3600, 0))),
                    "/wallet", f"contract:{c['contract_id']}")
        # PI の抽出機
        for r in (results["pi"] or {}).get("characters", []):
            for col in (r.get("data") or {}).get("colonies", []):
                for ex in col["extractors"]:
                    if not ex["active"]:
                        add("high", "PI", r["character_name"], tr("{0} の抽出機（{1}）が止まっています", col.get('planet_name'), item_name(ex)),
                            "/pi", f"pi-stop:{r['character_id']}:{col['planet_id']}:{ex.get('expiry')}")
                    elif ex["hours_left"] is not None and ex["hours_left"] < 12:
                        add("mid", "PI", r["character_name"], tr("{0} の抽出機（{1}）があと {2:.0f} 時間で止まります", col.get('planet_name'), item_name(ex), ex['hours_left']),
                            "/pi", f"pi-soon:{r['character_id']}:{col['planet_id']}:{ex.get('expiry')}")
        # クローンジャンプ・ジャンプ疲労
        for c in (results["clones"] or {}).get("characters", []):
            if c.get("jump_clones") is not None and not c.get("clone_ready_at") and c.get("last_clone_jump"):
                last = parse_time(c["last_clone_jump"])
                if now - last < timedelta(hours=c.get("cooldown_hours", 24) + 6):  # 使えるようになってまだ間もない
                    add("info", "クローン", c["character_name"], "クローンジャンプが使えるようになりました", "/travel",
                        f"clone:{c['character_id']}:{c['last_clone_jump']}")
        order = {"high": 0, "mid": 1, "info": 2}
        items.sort(key=lambda i: (order[i["level"]], i["category"], i["character_name"]))
        failed = [k for k, v in results.items() if v is None]
        return jsonify({"items": items, "checked_at": now.isoformat(), "failed": failed})
