"""生産: 製造・研究ジョブ、設計図と製造コスト、採掘の記録、静的データ（SDE）の状態。"""

import math
from datetime import datetime, timedelta, timezone

import requests
from flask import jsonify, request

from i18n import tr

from .common import (average_prices, error, float_arg, int_arg, jita_prices, location_names, per_character,
                     resolve_names, selected_characters, skill_levels, type_name)

ACTIVITIES = {1: "製造", 3: "TE 研究", 4: "ME 研究", 5: "コピー", 7: "リバースエンジニアリング", 8: "発明",
              9: "リアクション", 11: "リアクション"}
JOB_STATUS = {"active": "作業中", "paused": "一時停止", "ready": "完了（受け取り待ち）", "delivered": "受け取り済み",
              "cancelled": "取り消し", "reverted": "取り消し"}
SKILL_INDUSTRY = 3380
SKILL_ADVANCED_INDUSTRY = 3388
SKILL_REACTIONS = 45746
SCC_SURCHARGE = 0.04  # 生産の手数料に加わる SCC の割増（4%）


def register(app, ctx):
    core, live, sde = ctx.core, ctx.live, ctx.sde

    def need_sde():
        if not sde.ready:
            if sde.status["state"] not in ("building",):
                sde.build_async()
            return error(tr("静的データ（SDE）を準備しています（{0}%）。しばらくしてから開き直してください。", (sde.status.get('progress', 0))), 503)
        return None

    @app.get("/api/sde/status")
    def api_sde_status():
        return jsonify(sde.status)

    @app.post("/api/sde/rebuild")
    def api_sde_rebuild():
        sde.build_async()
        return jsonify(sde.status)

    # ---------- ジョブ ----------

    @app.get("/api/industry/jobs")
    def api_industry_jobs():
        force = request.args.get("force") == "1"  # スレッドの中では request を読めないので先に取り出す

        def load(cid, name):
            return live.get(cid, f"/characters/{cid}/industry/jobs/", core.SCOPE_JOBS, ttl=300,
                            params={"include_completed": "true"}, force=force)

        rows = per_character(selected_characters(ctx), load)
        jobs, chars = [], []
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        for r in rows:
            data = r.pop("data")
            chars.append(r)
            for j in data or []:
                end = datetime.fromisoformat(j["end_date"].replace("Z", "+00:00"))
                if j["status"] in ("delivered", "cancelled", "reverted") and end < cutoff:
                    continue
                jobs.append({**j, "character_id": r["character_id"], "character_name": r["character_name"]})
        locs = {}
        for j in jobs:
            if j["facility_id"] not in locs:
                locs.update(location_names(ctx, {j["facility_id"], j["station_id"]}, j["character_id"]))
        for j in jobs:
            j["blueprint"] = type_name(ctx, j["blueprint_type_id"])[0]
            j["product"] = type_name(ctx, j["product_type_id"])[0] if j.get("product_type_id") else None
            j["activity"] = ACTIVITIES.get(j["activity_id"], str(j["activity_id"]))
            j["status_label"] = JOB_STATUS.get(j["status"], j["status"])
            j["facility"] = locs.get(j["facility_id"]) or locs.get(j["station_id"])
        order = {"ready": 0, "active": 1, "paused": 2}
        jobs.sort(key=lambda j: (order.get(j["status"], 3), j["end_date"]))
        return jsonify({"characters": chars, "jobs": jobs})

    # ---------- 設計図 ----------

    @app.get("/api/industry/blueprints")
    def api_industry_blueprints():
        err = need_sde()
        if err:
            return err

        def load(cid, name):
            return live.get(cid, f"/characters/{cid}/blueprints/", core.SCOPE_BLUEPRINTS, ttl=3600, pages=True)

        rows = per_character(selected_characters(ctx), load)
        bps, chars = [], []
        for r in rows:
            data = r.pop("data")
            chars.append(r)
            for b in data or []:
                info = sde.blueprints.get(b["type_id"])
                if not info:
                    continue
                bps.append({**b, "character_id": r["character_id"], "character_name": r["character_name"],
                            "activity": info["activity"], "product_type_id": info["product"][0]})
        locs = {}
        for b in bps:
            if b["location_id"] not in locs:
                locs.update(location_names(ctx, {b["location_id"]}, b["character_id"]))
        for b in bps:
            b["ja"], b["en"] = type_name(ctx, b["type_id"])
            b["product"] = type_name(ctx, b["product_type_id"])[0]
            b["location"] = locs.get(b["location_id"])  # コンテナの中などは名前が出ない
            b["kind"] = "BPO" if b["quantity"] == -1 else "BPC"
        bps.sort(key=lambda b: (b["product"], b["kind"], -b["material_efficiency"]))
        return jsonify({"characters": chars, "blueprints": bps})

    @app.get("/api/industry/search")
    def api_industry_search():
        """設計図のある製品を名前で探す。"""
        err = need_sde()
        if err:
            return err
        results = [r for r in ctx.catalog.search(request.args.get("q", ""), limit=80) if r["id"] in sde.product_bp]
        return jsonify({"results": results[:30]})

    # ---------- 製造コスト ----------

    @app.get("/api/industry/cost")
    def api_industry_cost():
        err = need_sde()
        if err:
            return err
        type_id = int_arg("type_id")
        bp_id = type_id if type_id in sde.blueprints else sde.product_bp.get(type_id)
        if not bp_id:
            return error("この品目の設計図が見つかりません")
        bp = sde.blueprints[bp_id]
        runs = int_arg("runs", 1, 1, 100000)
        reaction = bp["activity"] == "reaction"
        me = 0 if reaction else int_arg("me", 10, 0, 10)
        te = 0 if reaction else int_arg("te", 20, 0, 20)
        facility_tax = float_arg("facility_tax", 0.25)
        material_bonus = float_arg("material_bonus", 0.0)
        levels = skill_levels(ctx, int_arg("character_id", 0)) if request.args.get("character_id") else {}

        materials = []
        for t, q in bp["materials"]:
            qty = max(runs, math.ceil(round(q * runs * (1 - me / 100) * (1 - material_bonus / 100), 2)))
            materials.append({"type_id": t, "base": q, "quantity": qty})
        product_id, product_qty = bp["product"]
        ids = [m["type_id"] for m in materials] + [product_id]
        try:
            prices = jita_prices(ctx, ids)
            adjusted = average_prices(ctx)
        except (RuntimeError, requests.RequestException) as e:
            return error(tr("価格を取得できませんでした: {0}", str(e).splitlines()[0]), 502)
        total_sell = total_buy = 0.0
        missing = 0
        for m in materials:
            ja, en = type_name(ctx, m["type_id"])
            p = prices.get(m["type_id"], {})
            m.update(ja=ja, en=en, sell=p.get("sell"), buy=p.get("buy"),
                     buildable=m["type_id"] in sde.product_bp)
            if p.get("sell") is None:
                missing += 1
            total_sell += (p.get("sell") or 0) * m["quantity"]
            total_buy += (p.get("buy") or 0) * m["quantity"]
        eiv = sum((adjusted.get(t, {}).get("adjusted") or 0) * q * runs for t, q in bp["materials"])

        system = request.args.get("system", "").strip()
        index, system_name = None, None
        if system:
            try:
                found = core.esi_post("/universe/ids/", [system]).get("systems", [])
                if found:
                    system_name = found[0]["name"]
                    for s in live.public("/industry/systems/", ttl=3600):
                        if s["solar_system_id"] == found[0]["id"]:
                            act = "reaction" if reaction else "manufacturing"
                            index = next((c["cost_index"] for c in s["cost_indices"] if c["activity"] == act), None)
            except (RuntimeError, requests.RequestException):
                pass
        job_cost = eiv * ((index or 0) + facility_tax / 100 + SCC_SURCHARGE)

        seconds = bp["time"] * runs * (1 - te / 100)
        if reaction:
            seconds *= 1 - 0.04 * levels.get(SKILL_REACTIONS, 0)
        else:
            seconds *= (1 - 0.04 * levels.get(SKILL_INDUSTRY, 0)) * (1 - 0.03 * levels.get(SKILL_ADVANCED_INDUSTRY, 0))
        pp = prices.get(product_id, {})
        units = product_qty * runs
        pja, pen = type_name(ctx, product_id)
        return jsonify({
            "blueprint_id": bp_id, "blueprint": type_name(ctx, bp_id)[0], "activity": bp["activity"],
            "product": {"type_id": product_id, "ja": pja, "en": pen, "units": units, "sell": pp.get("sell"), "buy": pp.get("buy")},
            "runs": runs, "me": me, "te": te, "materials": materials, "materials_sell": total_sell, "materials_buy": total_buy,
            "missing_prices": missing, "eiv": eiv, "system": system_name, "cost_index": index, "facility_tax": facility_tax,
            "job_cost": job_cost, "seconds": seconds, "skills_used": bool(levels),
            "cost_per_unit": (total_sell + job_cost) / units if units else None,
        })

    # ---------- 採掘の記録 ----------

    @app.get("/api/industry/mining")
    def api_industry_mining():
        days = int_arg("days", 30, 1, 30)
        start = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()

        def load(cid, name):
            return live.get(cid, f"/characters/{cid}/mining/", core.SCOPE_MINING, ttl=600, pages=True)

        rows = per_character(selected_characters(ctx), load)
        entries, chars = [], []
        for r in rows:
            data = r.pop("data")
            chars.append(r)
            for e in data or []:
                if e["date"] >= start:
                    entries.append({**e, "character_id": r["character_id"], "character_name": r["character_name"]})
        types = {e["type_id"] for e in entries}
        try:
            prices = jita_prices(ctx, types) if types else {}
        except (RuntimeError, requests.RequestException):
            prices = {}
        systems = resolve_names(ctx, {e["solar_system_id"] for e in entries})
        by_type, by_day, by_char = {}, {}, {}
        for e in entries:
            p = prices.get(e["type_id"], {})
            value = (p.get("buy") or 0) * e["quantity"]
            e["value"] = value
            t = by_type.setdefault(e["type_id"], {"type_id": e["type_id"], "quantity": 0, "value": 0.0,
                                                  "buy": p.get("buy"), "sell": p.get("sell")})
            t["quantity"] += e["quantity"]
            t["value"] += value
            d = by_day.setdefault(e["date"], {"date": e["date"], "quantity": 0, "value": 0.0})
            d["quantity"] += e["quantity"]
            d["value"] += value
            c = by_char.setdefault(e["character_id"], {"character_name": e["character_name"], "quantity": 0, "value": 0.0})
            c["quantity"] += e["quantity"]
            c["value"] += value
        for t in by_type.values():
            t["ja"], t["en"] = type_name(ctx, t["type_id"])
        for e in entries:
            e["system"] = systems.get(e["solar_system_id"])
            e["ja"], e["en"] = type_name(ctx, e["type_id"])
        entries.sort(key=lambda e: e["date"], reverse=True)
        return jsonify({"days": days, "characters": chars, "entries": entries[:500],
                        "by_type": sorted(by_type.values(), key=lambda t: -t["value"]),
                        "by_day": sorted(by_day.values(), key=lambda d: d["date"]),
                        "by_character": sorted(by_char.values(), key=lambda c: -c["value"])})
