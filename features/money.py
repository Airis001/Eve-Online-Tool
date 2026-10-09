"""お金: ウォレット・収支・転売の実績・契約・LP・コーポレーション・自分の注文・相場の推移・スタンディング・保険。"""

from datetime import datetime, timedelta, timezone

import requests
from flask import jsonify, request


from accounts import ThreadPoolExecutor
from i18n import tr
from live import EsiForbidden, ScopeMissing, safe

from .common import (JITA_REGION_ID, STATION_IDS, average_prices, error, int_arg, jita_prices, location_names,
                     per_character, resolve_names, selected_characters, skill_levels, type_name)

# 収支の種類（ESI の ref_type）→ 表示名。ここに無いものは英語のまま
REF_TYPES = {
    "bounty_prizes": "バウンティ", "bounty_prize": "バウンティ", "ess_escrow_transfer": "ESS",
    "agent_mission_reward": "ミッション報酬", "agent_mission_time_bonus_reward": "ミッションのボーナス",
    "market_transaction": "マーケットの売買", "market_escrow": "買い注文の預け金", "brokers_fee": "仲介手数料",
    "transaction_tax": "売上税", "player_trading": "プレイヤー間の取引", "player_donation": "送金",
    "corporation_account_withdrawal": "コーポの口座から", "contract_price": "契約の代金", "contract_reward": "契約の報酬",
    "contract_collateral": "契約の担保", "contract_collateral_refund": "担保の返却", "contract_brokers_fee": "契約の手数料",
    "contract_price_payment_corp": "契約の代金（コーポ）", "contract_sales_tax": "契約の売上税",
    "contract_deposit": "契約の預け金", "contract_deposit_refund": "預け金の返却", "contract_reward_deposited": "契約の報酬（預け）",
    "industry_job_tax": "生産の手数料", "manufacturing": "製造費", "researching_time_productivity": "研究費",
    "researching_material_productivity": "研究費", "copying": "コピー費", "reaction": "リアクション費",
    "planetary_import_tax": "PI の輸入税", "planetary_export_tax": "PI の輸出税", "planetary_construction": "PI の設備",
    "skill_purchase": "スキルの購入", "insurance": "保険", "jump_clone_installation_fee": "クローンの設置",
    "jump_clone_activation_fee": "クローンジャンプ", "reprocessing_tax": "再処理の税", "structure_gate_jump": "ゲートの利用料",
    "daily_goal_payouts": "デイリー目標", "corporate_reward_payout": "コーポの報酬", "project_discovery_reward": "Project Discovery",
    "asset_safety_recovery_tax": "アセットセーフティ", "office_rental_fee": "オフィスの賃料", "medal_creation": "メダル",
    "war_fee": "戦争の費用", "clone_activation": "クローン",
}
CONTRACT_TYPES = {"item_exchange": "アイテム交換", "auction": "オークション", "courier": "輸送", "loan": "貸し出し",
                  "unknown": "不明"}
CONTRACT_STATUS = {"outstanding": "募集中", "in_progress": "進行中", "finished_issuer": "完了", "finished_contractor": "完了",
                   "finished": "完了", "cancelled": "取り消し", "rejected": "拒否", "failed": "失敗", "deleted": "削除",
                   "reversed": "取り消し"}
INSURANCE_LEVELS = {"Basic": "ベーシック", "Standard": "スタンダード", "Bronze": "ブロンズ", "Silver": "シルバー",
                    "Gold": "ゴールド", "Platinum": "プラチナ"}
SKILL_CONNECTIONS = 3359
SKILL_DIPLOMACY = 3357
NPC_CORP_MAX_ID = 2_000_000


def parse_time(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def register(app, ctx):
    core, live = ctx.core, ctx.live

    def since(days):
        return datetime.now(timezone.utc) - timedelta(days=days)

    # ---------- ウォレット・収支 ----------

    @app.get("/api/wallet/summary")
    def api_wallet_summary():
        days = int_arg("days", 30, 1, 30)
        start = since(days)

        def load(cid, name):
            balance = live.get(cid, f"/characters/{cid}/wallet/", core.SCOPE_WALLET, ttl=120)
            journal = live.get(cid, f"/characters/{cid}/wallet/journal/", core.SCOPE_WALLET, ttl=3600, pages=True)
            return {"balance": balance, "journal": journal}

        rows = per_character(selected_characters(ctx), load)
        categories = {}
        dates = [(start + timedelta(days=i + 1)).date() for i in range(days)]
        daily_total = [0.0] * len(dates)
        daily_net = [0.0] * len(dates)
        chars = []
        for r in rows:
            data = r.pop("data")
            if data is None:
                chars.append(r)
                continue
            journal = sorted(data["journal"], key=lambda e: e["date"])
            income = expense = 0.0
            for e in journal:
                when = parse_time(e["date"])
                if when < start:
                    continue
                amount = e.get("amount", 0) or 0
                key = e["ref_type"]
                cat = categories.setdefault(key, {"ref_type": key, "label": REF_TYPES.get(key, key), "income": 0.0,
                                                  "expense": 0.0, "count": 0})
                cat["count"] += 1
                if amount >= 0:
                    cat["income"] += amount
                    income += amount
                else:
                    cat["expense"] += amount
                    expense += amount
                idx = (when.date() - dates[0]).days
                if 0 <= idx < len(dates):
                    daily_net[idx] += amount
            # 日ごとの残高（その日の最後の記録の残高。記録の無い日は前日のまま）
            first = journal[0] if journal else None
            bal = (first["balance"] - first.get("amount", 0)) if first and "balance" in first else data["balance"]
            j = 0
            for i, d in enumerate(dates):
                while j < len(journal) and parse_time(journal[j]["date"]).date() <= d:
                    bal = journal[j].get("balance", bal)
                    j += 1
                daily_total[i] += bal if i < len(dates) - 1 else data["balance"]
            chars.append({**r, "balance": data["balance"], "income": income, "expense": expense})
        cats = sorted(categories.values(), key=lambda c: -(c["income"] - c["expense"]))
        return jsonify({"days": days, "characters": chars, "categories": cats,
                        "daily": [{"date": d.isoformat(), "balance": b, "net": n}
                                  for d, b, n in zip(dates, daily_total, daily_net)]})

    # ---------- 転売の実績 ----------

    @app.get("/api/wallet/trades")
    def api_wallet_trades():
        days = int_arg("days", 30, 1, 90)
        start = since(days)

        def load(cid, name):
            tx = live.get(cid, f"/characters/{cid}/wallet/transactions/", core.SCOPE_WALLET, ttl=3600)
            journal = live.get(cid, f"/characters/{cid}/wallet/journal/", core.SCOPE_WALLET, ttl=3600, pages=True)
            return {"tx": tx, "journal": journal}

        rows = per_character(selected_characters(ctx), load)
        items = {}
        fees = {"brokers_fee": 0.0, "transaction_tax": 0.0}
        chars = []
        for r in rows:
            data = r.pop("data")
            chars.append(r)
            if data is None:
                continue
            for t in data["tx"]:
                if parse_time(t["date"]) < start or not t.get("is_personal", True):
                    continue
                it = items.setdefault(t["type_id"], {"type_id": t["type_id"], "buy_qty": 0, "buy_value": 0.0,
                                                     "sell_qty": 0, "sell_value": 0.0, "last": t["date"]})
                side = "buy" if t["is_buy"] else "sell"
                it[f"{side}_qty"] += t["quantity"]
                it[f"{side}_value"] += t["quantity"] * t["unit_price"]
                it["last"] = max(it["last"], t["date"])
            for e in data["journal"]:
                if e["ref_type"] in fees and parse_time(e["date"]) >= start:
                    fees[e["ref_type"]] += -(e.get("amount") or 0)
        result = []
        for it in items.values():
            ja, en = type_name(ctx, it["type_id"])
            avg_buy = it["buy_value"] / it["buy_qty"] if it["buy_qty"] else None
            avg_sell = it["sell_value"] / it["sell_qty"] if it["sell_qty"] else None
            matched = min(it["buy_qty"], it["sell_qty"])
            profit = (avg_sell - avg_buy) * matched if avg_buy is not None and avg_sell is not None else None
            result.append({**it, "ja": ja, "en": en, "avg_buy": avg_buy, "avg_sell": avg_sell, "matched": matched,
                           "profit": profit, "stock": it["buy_qty"] - it["sell_qty"]})
        result.sort(key=lambda x: -(x["profit"] or 0))
        gross = sum(x["profit"] or 0 for x in result)
        return jsonify({"days": days, "characters": chars, "items": result, "fees": fees,
                        "gross": gross, "net": gross - fees["brokers_fee"] - fees["transaction_tax"]})

    # ---------- 契約 ----------

    @app.get("/api/wallet/contracts")
    def api_wallet_contracts():
        start = since(30)

        def load(cid, name):
            return live.get(cid, f"/characters/{cid}/contracts/", core.SCOPE_CONTRACTS, ttl=300, pages=True)

        rows = per_character(selected_characters(ctx), load)
        contracts, chars, seen = [], [], set()
        for r in rows:
            data = r.pop("data")
            chars.append(r)
            for c in data or []:
                if c["contract_id"] in seen:
                    continue
                active = c["status"] in ("outstanding", "in_progress")
                if not active and parse_time(c["date_issued"]) < start:
                    continue
                seen.add(c["contract_id"])
                contracts.append({**c, "character_id": r["character_id"], "character_name": r["character_name"],
                                  "type_label": CONTRACT_TYPES.get(c["type"], c["type"]),
                                  "status_label": CONTRACT_STATUS.get(c["status"], c["status"]), "active": active})
        party_ids = {c.get(k) for c in contracts for k in ("issuer_id", "assignee_id", "acceptor_id") if c.get(k)}
        names = resolve_names(ctx, party_ids)
        locs = {}
        for c in contracts:
            ids = {c.get("start_location_id"), c.get("end_location_id")} - {None}
            missing = ids - set(locs)
            if missing:
                locs.update(location_names(ctx, missing, c["character_id"]))
        for c in contracts:
            for k in ("issuer", "assignee", "acceptor"):
                c[f"{k}_name"] = names.get(c.get(f"{k}_id"))
            c["start_location"] = locs.get(c.get("start_location_id"))
            c["end_location"] = locs.get(c.get("end_location_id"))
        contracts.sort(key=lambda c: (not c["active"], c["date_expired"] if c["active"] else "", c["date_issued"]),
                       reverse=False)
        return jsonify({"characters": chars, "contracts": contracts})

    # ---------- LP ----------

    @app.get("/api/wallet/lp")
    def api_wallet_lp():
        def load(cid, name):
            return live.get(cid, f"/characters/{cid}/loyalty/points/", core.SCOPE_LOYALTY, ttl=3600)

        rows = per_character(selected_characters(ctx), load)
        corps = {}
        chars = []
        for r in rows:
            data = r.pop("data")
            chars.append(r)
            for lp in data or []:
                if lp["loyalty_points"] <= 0:
                    continue
                entry = corps.setdefault(lp["corporation_id"], {"corporation_id": lp["corporation_id"], "total": 0,
                                                                "by_character": []})
                entry["total"] += lp["loyalty_points"]
                entry["by_character"].append({"character_name": r["character_name"], "points": lp["loyalty_points"]})
        names = resolve_names(ctx, corps)
        try:
            avg = average_prices(ctx)
        except (RuntimeError, requests.RequestException):
            avg = {}
        limit = int_arg("limit", 15, 5, 50)

        def offers_for(corp_id):
            try:
                offers = live.public(f"/loyalty/stores/{corp_id}/offers/", ttl=86400)
            except (RuntimeError, requests.RequestException):
                return []
            valued = []
            for o in offers:
                if not o.get("lp_cost"):
                    continue
                value = (avg.get(o["type_id"], {}).get("average") or 0) * o["quantity"] - o.get("isk_cost", 0) \
                    - sum((avg.get(i["type_id"], {}).get("average") or 0) * i["quantity"] for i in o.get("required_items", []))
                valued.append({**o, "estimate_per_lp": value / o["lp_cost"]})
            valued.sort(key=lambda o: -o["estimate_per_lp"])
            return valued[:limit * 2]

        with ThreadPoolExecutor(max_workers=5) as pool:
            top = dict(zip(corps, pool.map(offers_for, corps)))
        # 見積もりの上位だけ、Jita の実際の価格で計算し直す
        ids = {o["type_id"] for offers in top.values() for o in offers}
        ids |= {i["type_id"] for offers in top.values() for o in offers for i in o.get("required_items", [])}
        try:
            prices = jita_prices(ctx, ids)
        except (RuntimeError, requests.RequestException):
            prices = {}
        # 1 日の取引量（The Forge の 7 日平均）。取引の少ない品目は、価格が高く見えても売れにくい
        def volume(t):
            try:
                rows = live.public(f"/markets/{JITA_REGION_ID}/history/", ttl=3600, params={"type_id": t})[-7:]
                return t, sum(r["volume"] for r in rows) / 7 if rows else 0
            except (RuntimeError, requests.RequestException):
                return t, None
        with ThreadPoolExecutor(max_workers=8) as pool:
            volumes = dict(pool.map(volume, {o["type_id"] for offers in top.values() for o in offers}))
        result = []
        for corp_id, entry in corps.items():
            offers = []
            for o in top.get(corp_id, []):
                p = prices.get(o["type_id"], {})
                req = [{**i, "ja": type_name(ctx, i["type_id"])[0], "en": type_name(ctx, i["type_id"])[1], "price": prices.get(i["type_id"], {}).get("sell")}
                       for i in o.get("required_items", [])]
                req_cost = sum((i["price"] or 0) * i["quantity"] for i in req)
                sell = p.get("sell")
                buy = p.get("buy")
                offers.append({
                    "offer_id": o["offer_id"], "type_id": o["type_id"], "ja": type_name(ctx, o["type_id"])[0], "en": type_name(ctx, o["type_id"])[1],
                    "quantity": o["quantity"], "lp_cost": o["lp_cost"], "isk_cost": o.get("isk_cost", 0),
                    "required": req, "sell": sell, "buy": buy,
                    "per_lp_sell": ((sell or 0) * o["quantity"] - o.get("isk_cost", 0) - req_cost) / o["lp_cost"] if sell else None,
                    "per_lp_buy": ((buy or 0) * o["quantity"] - o.get("isk_cost", 0) - req_cost) / o["lp_cost"] if buy else None,
                    "affordable": entry["total"] // o["lp_cost"],
                    "daily_volume": volumes.get(o["type_id"]),
                })
            # 1 日に 1 個も売れていない品目は下に回す
            offers.sort(key=lambda o: ((o["daily_volume"] or 0) < 1, -(o["per_lp_sell"] or -1e18)))
            result.append({**entry, "name": names.get(corp_id) or str(corp_id), "offers": offers[:limit]})
        result.sort(key=lambda e: -e["total"])
        return jsonify({"characters": chars, "corporations": result})

    # ---------- コーポレーション ----------

    @app.get("/api/wallet/corp")
    def api_wallet_corp():
        chars = selected_characters(ctx)

        def affiliation(c):
            try:
                return c, live.public(f"/characters/{c[0]}/", ttl=3600)["corporation_id"]
            except (RuntimeError, requests.RequestException, KeyError):
                return c, None
        with ThreadPoolExecutor(max_workers=5) as pool:
            aff = list(pool.map(affiliation, chars))
        by_corp = {}
        for c, corp_id in aff:
            if corp_id:
                by_corp.setdefault(corp_id, []).append(c)
        names = resolve_names(ctx, by_corp)
        try:
            avg = average_prices(ctx)
        except (RuntimeError, requests.RequestException):
            avg = {}

        def corp_view(corp_id, members):
            view = {"corporation_id": corp_id, "name": names.get(corp_id) or str(corp_id),
                    "members": [m[1] for m in members], "npc": corp_id < NPC_CORP_MAX_ID}
            if view["npc"]:
                return view
            errors = []
            for cid, cname in members:  # 役職のあるキャラクターが見つかるまで順に試す
                if "wallets" not in view:
                    data, err = safe(live.get, cid, f"/corporations/{corp_id}/wallets/", core.SCOPE_CORP_WALLETS, ttl=300)
                    if data is not None:
                        view["wallets"] = data
                        view["wallet_by"] = cname
                        div, _ = safe(live.get, cid, f"/corporations/{corp_id}/divisions/", core.SCOPE_CORP_DIVISIONS, ttl=3600)
                        view["division_names"] = {d["division"]: d.get("name") for d in (div or {}).get("wallet", [])}
                    else:
                        errors.append({"what": "wallets", "character_name": cname, **err})
                if "assets" not in view:
                    data, err = safe(live.get, cid, f"/corporations/{corp_id}/assets/", core.SCOPE_CORP_ASSETS,
                                     ttl=3600, pages=True)
                    if data is not None:
                        view["assets"] = summarize_assets(ctx, data, avg)
                        view["assets_by"] = cname
                    else:
                        errors.append({"what": "assets", "character_name": cname, **err})
            if "wallets" in view:
                errors = [e for e in errors if e["what"] != "wallets"]
            if "assets" in view:
                errors = [e for e in errors if e["what"] != "assets"]
            view["errors"] = errors
            return view

        with ThreadPoolExecutor(max_workers=3) as pool:
            result = list(pool.map(lambda kv: corp_view(*kv), by_corp.items()))
        result.sort(key=lambda v: (v["npc"], v["name"]))
        return jsonify({"corporations": result})

    # ---------- 自分の注文 ----------

    @app.get("/api/market/my-orders")
    def api_my_orders():
        force = request.args.get("force") == "1"  # スレッドの中では request を読めないので先に取り出す

        def load(cid, name):
            return live.get(cid, f"/characters/{cid}/orders/", core.SCOPE_ORDERS, ttl=300, force=force)

        rows = per_character(selected_characters(ctx), load)
        orders, chars = [], []
        for r in rows:
            data = r.pop("data")
            chars.append(r)
            for o in data or []:
                orders.append({**o, "character_id": r["character_id"], "character_name": r["character_name"],
                               "is_buy_order": bool(o.get("is_buy_order"))})
        my_ids = {o["order_id"] for o in orders}
        by_location = {}
        for o in orders:
            by_location.setdefault(o["location_id"], set()).add(o["type_id"])
        market_orders, market_errors = {}, {}

        def fetch(loc):
            try:
                return loc, ctx.markets.orders(loc, sorted(by_location[loc])), None
            except Exception as e:  # noqa: BLE001 - 建造物の権限なしなど。注文ごとに「不明」と出す
                return loc, {}, str(e).splitlines()[0]
        with ThreadPoolExecutor(max_workers=4) as pool:
            for loc, data, err in pool.map(fetch, by_location):
                market_orders[loc] = data
                if err:
                    market_errors[loc] = err
        locs = {}
        for o in orders:
            if o["location_id"] not in locs:
                locs.update(location_names(ctx, {o["location_id"]}, o["character_id"]))
        now = datetime.now(timezone.utc)
        for o in orders:
            ja, en = type_name(ctx, o["type_id"])
            others = [m for m in market_orders.get(o["location_id"], {}).get(o["type_id"], [])
                      if m["order_id"] not in my_ids and m["is_buy_order"] == o["is_buy_order"]]
            if o["is_buy_order"]:
                best = max((m["price"] for m in others), default=None)
                beaten = best is not None and best > o["price"]
            else:
                best = min((m["price"] for m in others), default=None)
                beaten = best is not None and best < o["price"]
            expires = parse_time(o["issued"]) + timedelta(days=o["duration"])
            o.update(ja=ja, en=en, location=locs.get(o["location_id"]), best_other=best, beaten=beaten,
                     market_error=market_errors.get(o["location_id"]), expires=expires.isoformat(),
                     days_left=(expires - now).total_seconds() / 86400)
        orders.sort(key=lambda o: (not o["beaten"], o["is_buy_order"], o["ja"]))
        return jsonify({"characters": chars, "orders": orders})

    # ---------- 相場の推移 ----------

    @app.get("/api/market/history")
    def api_market_history():
        type_id = int_arg("type_id")
        region_id = int_arg("region", JITA_REGION_ID)
        if not type_id:
            return error("type_id が必要です")
        try:
            rows = live.public(f"/markets/{region_id}/history/", ttl=3600, params={"type_id": type_id})
        except (RuntimeError, requests.RequestException) as e:
            return error(tr("相場の履歴を取得できませんでした: {0}", str(e).splitlines()[0]), 502)
        rows = rows[-120:]

        def avg(key, n):
            part = rows[-n:]
            return sum(r[key] for r in part) / len(part) if part else None
        return jsonify({"type_id": type_id, "region_id": region_id, "history": rows,
                        "volume_7": avg("volume", 7), "volume_30": avg("volume", 30),
                        "price_7": avg("average", 7), "price_30": avg("average", 30)})

    # ---------- スタンディング（仲介手数料の軽減） ----------

    @app.get("/api/market/standings")
    def api_market_standings():
        char_id = int_arg("character_id")
        loc_ids = [int(x) for x in request.args.get("locations", "").split(",") if x.strip().isdigit()]
        try:
            result, levels = standing_reductions(ctx, char_id, loc_ids)
        except ScopeMissing:
            return jsonify({"needs_scope": core.SCOPE_STANDINGS, "locations": {}})
        except (EsiForbidden, RuntimeError, requests.RequestException) as e:
            return error(str(e).splitlines()[0], 502)
        names = resolve_names(ctx, {v["faction_id"] for v in result.values() if v["faction_id"]})
        for v in result.values():
            v["faction"] = names.get(v["faction_id"])
        return jsonify({"locations": {str(k): v for k, v in result.items()},
                        "skills": {"connections": levels.get(SKILL_CONNECTIONS, 0),
                                   "diplomacy": levels.get(SKILL_DIPLOMACY, 0)}})

    # ---------- 保険 ----------

    @app.get("/api/market/insurance")
    def api_insurance():
        type_id = int_arg("type_id")
        if not type_id:
            return error("type_id が必要です")
        try:
            table = {r["type_id"]: r["levels"] for r in live.public("/insurance/prices/", ttl=3600)}
        except (RuntimeError, requests.RequestException) as e:
            return error(tr("保険の情報を取得できませんでした: {0}", str(e).splitlines()[0]), 502)
        if type_id not in table:
            return error("この艦は保険に入れません", 404)
        try:
            price = jita_prices(ctx, [type_id]).get(type_id, {})
        except (RuntimeError, requests.RequestException):
            price = {}
        ja, en = type_name(ctx, type_id)
        levels = [{"name": INSURANCE_LEVELS.get(lv["name"], lv["name"]), "cost": lv["cost"], "payout": lv["payout"],
                   "net": lv["payout"] - lv["cost"]} for lv in table[type_id]]
        return jsonify({"type_id": type_id, "ja": ja, "en": en, "levels": levels,
                        "jita_sell": price.get("sell"), "jita_buy": price.get("buy")})

    # ---------- ゲームのマーケット画面を開く ----------

    @app.post("/api/ui/market")
    def api_ui_market():
        body = request.get_json(silent=True) or {}
        return ui_post(ctx, body.get("character_id"), core.SCOPE_OPEN_WINDOW, "/ui/openwindow/marketdetails/",
                       {"type_id": int(body.get("type_id") or 0)})


def standing_reductions(ctx, char_id, loc_ids):
    """NPC ステーションごとの、スタンディングによる仲介手数料の軽減（%ポイント）。

    返り値: ({station_id: {...}}, スキルのレベル)。スタンディングの権限が無ければ ScopeMissing。
    """
    live, core = ctx.live, ctx.core
    standings = live.get(char_id, f"/characters/{char_id}/standings/", core.SCOPE_STANDINGS, ttl=3600)
    raw = {(s["from_type"], s["from_id"]): s["standing"] for s in standings}
    levels = skill_levels(ctx, char_id)

    def effective(s):  # Connections・Diplomacy を加味した値
        if s > 0:
            return s + (10 - s) * 0.04 * levels.get(SKILL_CONNECTIONS, 0)
        if s < 0:
            return s + (10 - s) * 0.04 * levels.get(SKILL_DIPLOMACY, 0)
        return 0.0

    result = {}
    for loc in loc_ids:
        if loc not in STATION_IDS:
            continue
        try:
            station = live.public(f"/universe/stations/{loc}/", ttl=86400)
            corp_id = station.get("owner")
            corp = live.public(f"/corporations/{corp_id}/", ttl=86400) if corp_id else {}
        except (RuntimeError, requests.RequestException):
            continue
        # ESI の NPC コーポの情報には勢力が無いので、静的データ（SDE）から引く
        faction_id = corp.get("faction_id") or (ctx.sde.npc_factions.get(corp_id) if ctx.sde.ready else None)
        corp_s = effective(raw.get(("npc_corp", corp_id), 0.0))
        faction_s = effective(raw.get(("faction", faction_id), 0.0)) if faction_id else 0.0
        result[loc] = {"corporation_id": corp_id, "corporation": corp.get("name"), "faction_id": faction_id,
                       "corp_standing": corp_s, "faction_standing": faction_s,
                       "reduction": 0.03 * faction_s + 0.02 * corp_s}
    return result, levels


def ui_post(ctx, char_id, scope, path, params):
    """ゲームの操作（ESI の UI 系 API）。キャラクターがログイン中でないとゲームには反映されない。"""
    try:
        char_id = int(char_id)
    except (TypeError, ValueError):
        return error("character_id が必要です")
    if not ctx.live.has(char_id, scope):
        return error("このキャラクターは、ゲームの操作の権限がありません。再ログインしてください。", 403)
    try:
        ctx.core.esi_post(path, None, params=params, access_token=ctx.token(char_id))
    except (RuntimeError, requests.RequestException) as e:
        return error(tr("ゲームに送れませんでした: {0}", str(e).splitlines()[0]), 502)
    return jsonify({"ok": True})


def summarize_assets(ctx, assets, avg):
    """コーポの資産: 件数と、平均価格で見積もった合計額・上位の品目。"""
    totals = {}
    for a in assets:
        if a.get("is_blueprint_copy"):
            continue
        totals[a["type_id"]] = totals.get(a["type_id"], 0) + a.get("quantity", 1)
    rows = []
    for t, qty in totals.items():
        price = (avg.get(t) or {}).get("average") or 0
        rows.append({"type_id": t, "quantity": qty, "value": price * qty})
    rows.sort(key=lambda r: -r["value"])
    for r in rows[:30]:
        r["ja"], r["en"] = type_name(ctx, r["type_id"])
    return {"count": len(assets), "types": len(totals), "value": sum(r["value"] for r in rows), "top": rows[:30]}
