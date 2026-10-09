"""トレード × 生産の損益: 生産キャラクターが作り、材料はコーポの資産を使って足りない分をトレードキャラクターが買い、
製品をトレードキャラクターが売ったときに、利益が出るかどうか。

  - 材料・生産の手数料・時間は、製造コストの計算（features/industry.py）と同じ式。
  - 手数料・税は、トレードキャラクターの Accounting・Broker Relations と、Jita でのスタンディングで計算する。
  - コーポの資産にある材料は「買わなくてよい」分として差し引く。ただし在庫を使うと、その在庫を売れば得られた
    お金（Jita の買値 − 売上税）を失うので、「在庫の価値を含めた利益」も出す。
"""

import math

import requests
from flask import jsonify, request

from accounts import ThreadPoolExecutor
from i18n import tr
from live import EsiForbidden, ScopeMissing, safe

from .common import (JITA_REGION_ID, JITA_STATION_ID, average_prices, error, float_arg, int_arg, jita_prices,
                     location_names, skill_levels, type_name)
from .industry import SCC_SURCHARGE, SKILL_ADVANCED_INDUSTRY, SKILL_INDUSTRY, SKILL_REACTIONS
from .money import standing_reductions

SKILL_ACCOUNTING = 16622
SKILL_BROKER_RELATIONS = 3446
BASE_SALES_TAX = 7.5
BASE_BROKER_FEE = 3.0
MAX_BLUEPRINTS = 40


def register(app, ctx):
    core, live, sde = ctx.core, ctx.live, ctx.sde

    def fees_for(trader_id):
        """トレードキャラクターの売上税・仲介手数料（%）。"""
        lv = skill_levels(ctx, trader_id)
        tax = BASE_SALES_TAX * (1 - 0.11 * lv.get(SKILL_ACCOUNTING, 0))
        broker = BASE_BROKER_FEE - 0.3 * lv.get(SKILL_BROKER_RELATIONS, 0)
        reduction, note = 0.0, None
        try:
            st, _ = standing_reductions(ctx, trader_id, [JITA_STATION_ID])
            reduction = st.get(JITA_STATION_ID, {}).get("reduction", 0.0)
        except ScopeMissing:
            note = "スタンディングの権限が無いため、スタンディングによる軽減は含めていません"
        except (EsiForbidden, RuntimeError, requests.RequestException):
            note = "スタンディングを取得できませんでした"
        return {"tax": max(tax, 0.0), "broker": max(broker - reduction, 0.0), "standing_reduction": reduction,
                "accounting": lv.get(SKILL_ACCOUNTING, 0), "broker_relations": lv.get(SKILL_BROKER_RELATIONS, 0),
                "note": note}

    def corp_of(char_ids):
        """(コーポ ID, 取得を試すキャラクターの順番)。NPC コーポなら コーポ ID は None。"""
        corp_id = None
        for cid in char_ids:
            info, _ = safe(live.public, f"/characters/{cid}/", 3600)
            if info:
                corp_id = info["corporation_id"]
                break
        if not corp_id or corp_id < 2_000_000:
            return None, []
        members = [cid for cid, _ in ctx.store.characters()
                   if (safe(live.public, f"/characters/{cid}/", 3600)[0] or {}).get("corporation_id") == corp_id]
        return corp_id, list(dict.fromkeys([*char_ids, *members]))

    def corp_get(corp_id, ordered, path, scope):
        """コーポの ESI を、見られる（役職・権限のある）キャラクターが見つかるまで順に試す。(データ, 理由)"""
        reasons = []
        for cid in ordered:
            data, err = safe(live.get, cid, f"/corporations/{corp_id}/{path}/", scope, ttl=3600, pages=True)
            if data is not None:
                return data, None
            reasons.append(err)
        if any(r.get("needs_scope") for r in reasons) and not any(r.get("forbidden") for r in reasons):
            return None, "再ログインが必要です"
        return None, "見られる役職（ディレクター）のキャラクターがいません"

    def corp_blueprints(char_ids):
        """コーポの設計図。一覧（ME・TE・残り回数あり）が取れなければ、資産の中の設計図（ME・TE 不明）。"""
        corp_id, ordered = corp_of(char_ids)
        if not corp_id:
            return [], None
        bps, why = corp_get(corp_id, ordered, "blueprints", core.SCOPE_CORP_BLUEPRINTS)
        if bps is not None:
            return [{**b, "source": "corp"} for b in bps], None
        assets, why2 = corp_get(corp_id, ordered, "assets", core.SCOPE_CORP_ASSETS)
        if assets is None:
            return [], tr("コーポの設計図を取得できませんでした（{0}）", why)
        found = [{"type_id": a["type_id"], "quantity": -2 if a.get("is_blueprint_copy") else -1, "runs": 0,
                  "material_efficiency": None, "time_efficiency": None, "source": "corp_assets"}
                 for a in assets if a["type_id"] in sde.blueprints]
        return found, tr("コーポの設計図の一覧を取得できないため（{0}）、資産の中の設計図を使っています（ME・TE は入力した値と仮定）", why)

    def corp_inventory(char_ids, location=None):
        """コーポの資産の {type_id: 数量}（場所を指定すればその場所の中だけ）と、場所の一覧。取れなければ理由。"""
        corp_id, ordered = corp_of(char_ids)
        if not corp_id:
            return None, [], "NPC コーポの所属のため、コーポの資産はありません"
        assets, why = corp_get(corp_id, ordered, "assets", core.SCOPE_CORP_ASSETS)
        if assets is None:
            return None, [], tr("コーポの資産を取得できませんでした（{0}）", why)
        by_item = {a["item_id"]: a for a in assets}

        def root(a):  # コンテナ・オフィスの中のものは、一番外側の場所にまとめる
            seen = 0
            while a["location_id"] in by_item and seen < 10:
                a = by_item[a["location_id"]]
                seen += 1
            return a["location_id"]

        stock, per_loc = {}, {}
        for a in assets:
            if a["type_id"] in sde.blueprints:  # 設計図は材料ではない
                continue
            loc = root(a)
            per_loc[loc] = per_loc.get(loc, 0) + 1
            if location and loc != location:
                continue
            stock[a["type_id"]] = stock.get(a["type_id"], 0) + a.get("quantity", 1)
        names = location_names(ctx, set(per_loc), ordered[0])
        locations = [{"id": k, "name": names.get(k) or str(k), "count": v}
                     for k, v in sorted(per_loc.items(), key=lambda kv: -kv[1])[:30]]
        return stock, locations, None

    @app.get("/api/industry/trade-build")
    def api_trade_build():
        if not sde.ready:
            sde.build_async()
            return error("静的データ（SDE）を準備しています。しばらくしてから開き直してください。", 503)
        trader, maker = int_arg("trader_id"), int_arg("maker_id")
        if not trader or not maker:
            return error("トレードキャラクターと生産キャラクターを選んでください")
        type_id = int_arg("type_id")
        buy_mode = "buy" if request.args.get("buy_mode") == "buy" else "sell"
        sell_mode = "buy" if request.args.get("sell_mode") == "buy" else "sell"
        facility_tax = float_arg("facility_tax", 0.25)
        material_bonus = float_arg("material_bonus", 0.0)
        system = request.args.get("system", "").strip()
        use_corp = request.args.get("use_corp", "1") == "1"
        location = int_arg("location") or None

        # 作るもの: 指定の品目、または生産キャラクターの持っている設計図すべて
        owned = {}
        bps, bp_err = safe(live.get, maker, f"/characters/{maker}/blueprints/", core.SCOPE_BLUEPRINTS, ttl=3600, pages=True)
        corp_bps, corp_bp_note = corp_blueprints([maker, trader]) if request.args.get("corp_bps", "1") == "1" else ([], None)

        def rank(b):  # ME・TE が分かっていて高いもの → BPO の順に優先
            return (b.get("material_efficiency") is not None, b.get("material_efficiency") or 0, b["quantity"] == -1)
        for b in [*({**x, "source": "character"} for x in bps or []), *corp_bps]:
            if b["type_id"] not in sde.blueprints:
                continue
            best = owned.get(b["type_id"])
            if not best or rank(b) > rank(best):
                owned[b["type_id"]] = b
        if type_id:
            bp_id = type_id if type_id in sde.blueprints else sde.product_bp.get(type_id)
            if not bp_id:
                return error("この品目の設計図が見つかりません")
            targets = [bp_id]
        else:
            if not owned:
                why = "設計図の権限が無いため再ログインが必要です" if (bp_err or {}).get("needs_scope") else "製造・リアクションの設計図がありません"
                return error(tr("生産キャラクター・コーポの設計図を調べられません（{0}）。品目を指定してください。", why)
                             + (f" {corp_bp_note}" if corp_bp_note else ""))
            targets = list(owned)[:MAX_BLUEPRINTS]

        stock, locations, stock_note = ({}, [], "コーポの資産は使わない設定です")
        if use_corp:
            stock, locations, stock_note = corp_inventory([maker, trader], location)
            stock = stock or {}
        maker_levels = skill_levels(ctx, maker)
        fees = fees_for(trader)

        # 必要な価格をまとめて取る
        ids = set()
        for bp_id in targets:
            bp = sde.blueprints[bp_id]
            ids.add(bp["product"][0])
            ids.update(t for t, _ in bp["materials"])
        try:
            prices = jita_prices(ctx, ids)
            adjusted = average_prices(ctx)
        except (RuntimeError, requests.RequestException) as e:
            return error(tr("価格を取得できませんでした: {0}", str(e).splitlines()[0]), 502)
        index = {}
        system_name = None
        if system:
            found, _ = safe(core.esi_post, "/universe/ids/", [system])
            found = (found or {}).get("systems", [])
            if found:
                system_name = found[0]["name"]
                for s in live.public("/industry/systems/", ttl=3600):
                    if s["solar_system_id"] == found[0]["id"]:
                        index = {c["activity"]: c["cost_index"] for c in s["cost_indices"]}

        def volume(t):
            rows, _ = safe(live.public, f"/markets/{JITA_REGION_ID}/history/", 3600, {"type_id": t})
            rows = (rows or [])[-7:]
            return t, sum(r["volume"] for r in rows) / 7 if rows else None
        with ThreadPoolExecutor(max_workers=8) as pool:
            volumes = dict(pool.map(volume, {sde.blueprints[b]["product"][0] for b in targets}))

        def evaluate(bp_id, owned_bp):
            bp = sde.blueprints[bp_id]
            reaction = bp["activity"] == "reaction"
            known = owned_bp and owned_bp.get("material_efficiency") is not None
            me = 0 if reaction else (owned_bp["material_efficiency"] if known else int_arg("me", 10, 0, 10))
            te = 0 if reaction else (owned_bp["time_efficiency"] if known else int_arg("te", 20, 0, 20))
            runs = int_arg("runs", 0, 0, 100000) or (owned_bp["runs"] if owned_bp and owned_bp["runs"] > 0 else 1)
            materials, purchase, inventory_value, missing = [], 0.0, 0.0, 0
            for t, q in bp["materials"]:
                need = max(runs, math.ceil(round(q * runs * (1 - me / 100) * (1 - material_bonus / 100), 2)))
                have = min(need, stock.get(t, 0))
                buy = need - have
                p = prices.get(t, {})
                unit = p.get("sell") if buy_mode == "sell" else (p.get("buy") * (1 + fees["broker"] / 100) if p.get("buy") else None)
                if buy and unit is None:
                    missing += 1
                cost = buy * (unit or 0)
                # 在庫を使う分の価値 = その在庫を今すぐ売った額（買い注文に売る・売上税を引く）
                inv = have * (p.get("buy") or 0) * (1 - fees["tax"] / 100)
                purchase += cost
                inventory_value += inv
                materials.append({"type_id": t, "ja": type_name(ctx, t)[0], "en": type_name(ctx, t)[1], "need": need, "have": have, "buy": buy,
                                  "unit": unit, "cost": cost, "inventory_value": inv})
            eiv = sum((adjusted.get(t, {}).get("adjusted") or 0) * q * runs for t, q in bp["materials"])
            act_index = index.get("reaction" if reaction else "manufacturing", 0.0)
            job_cost = eiv * (act_index + facility_tax / 100 + SCC_SURCHARGE)
            product, per_run = bp["product"]
            units = per_run * runs
            pp = prices.get(product, {})
            if sell_mode == "sell":
                unit_price = pp.get("sell")
                net_unit = unit_price * (1 - (fees["tax"] + fees["broker"]) / 100) if unit_price else None
            else:
                unit_price = pp.get("buy")
                net_unit = unit_price * (1 - fees["tax"] / 100) if unit_price else None
            revenue = (net_unit or 0) * units
            cash_profit = revenue - purchase - job_cost
            full_profit = cash_profit - inventory_value
            seconds = bp["time"] * runs * (1 - te / 100)
            if reaction:
                seconds *= 1 - 0.04 * maker_levels.get(SKILL_REACTIONS, 0)
            else:
                seconds *= (1 - 0.04 * maker_levels.get(SKILL_INDUSTRY, 0)) * (1 - 0.03 * maker_levels.get(SKILL_ADVANCED_INDUSTRY, 0))
            missing_skills = [{"skill_id": s, "name": type_name(ctx, s)[1], "level": lv, "have": maker_levels.get(s, 0)}
                              for s, lv in bp.get("skills", []) if maker_levels.get(s, 0) < lv]
            if net_unit is None:
                verdict = "no_price"
            elif full_profit > 0:
                verdict = "profit"
            elif cash_profit > 0:
                verdict = "stock_only"   # 現金では黒字だが、在庫をそのまま売った方が得
            else:
                verdict = "loss"
            cost_total = purchase + job_cost + inventory_value
            return {
                "blueprint_id": bp_id, "blueprint": type_name(ctx, bp_id)[0], "activity": bp["activity"],
                "owned": bool(owned_bp), "kind": ("BPO" if owned_bp and owned_bp["quantity"] == -1 else "BPC") if owned_bp else None,
                "bp_source": owned_bp.get("source") if owned_bp else None, "me_known": bool(known) or reaction,
                "type_id": product, "ja": type_name(ctx, product)[0], "en": type_name(ctx, product)[1], "units": units, "runs": runs, "me": me, "te": te,
                "materials": materials, "purchase": purchase, "inventory_value": inventory_value, "job_cost": job_cost,
                "unit_price": unit_price, "net_unit": net_unit, "revenue": revenue,
                "cash_profit": cash_profit, "full_profit": full_profit,
                "margin": full_profit / cost_total * 100 if cost_total else None,
                "seconds": seconds, "profit_per_hour": full_profit / (seconds / 3600) if seconds else None,
                "daily_volume": volumes.get(product), "missing_prices": missing,
                "missing_skills": missing_skills, "verdict": verdict,
            }

        results = [evaluate(bp_id, owned.get(bp_id)) for bp_id in targets]
        results.sort(key=lambda r: -(r["profit_per_hour"] if r["profit_per_hour"] is not None else -1e18))
        names = {c: n for c, n in ctx.store.characters()}
        return jsonify({
            "trader": {"id": trader, "name": names.get(trader), **fees},
            "maker": {"id": maker, "name": names.get(maker), "industry": maker_levels.get(SKILL_INDUSTRY, 0),
                      "advanced_industry": maker_levels.get(SKILL_ADVANCED_INDUSTRY, 0)},
            "buy_mode": buy_mode, "sell_mode": sell_mode, "system": system_name, "cost_indices": index,
            "use_corp": use_corp, "stock_note": stock_note, "locations": locations, "location": location,
            "stock_types": len(stock), "results": results,
            "blueprints_note": None if owned or type_id else "設計図がありません", "corp_bp_note": corp_bp_note,
            "corp_bp_count": len({b["type_id"] for b in corp_bps if b["type_id"] in sde.blueprints}),
        })
