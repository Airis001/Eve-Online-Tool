"""PI（惑星開発）: 全キャラクターのコロニーの一覧と、余り・不足をなくすための提案。"""

import json
import math
import threading
from datetime import datetime, timezone

import requests
from flask import jsonify, request

import accounts
import pi
import pi_planner
from accounts import ThreadPoolExecutor
from i18n import tr
from live import safe

from .common import error, float_arg, jita_prices, per_character, resolve_names, selected_characters, skill_levels

SMALL_PLANET_SHARE = 0.3  # 抽出惑星これ未満の追加は「今の抽出機の見直し」で済む目安
MAX_LAYOUTS = 2000
_layouts_lock = threading.Lock()


def layouts_file():
    return accounts.user_file("pi_layouts.json")


def load_layouts():
    """記録した抽出機の配置 {キー: 記録}。キーは キャラクター:惑星:設備:設置日時（同じ抽出は上書き）。"""
    try:
        return json.loads(layouts_file().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def record_layouts(sde, rows):
    """読み込んだコロニーの抽出機の配置を記録する（破棄したあとも参考にできるように）。記録した件数を返す。"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    added = 0
    with _layouts_lock:
        layouts = load_layouts()
        for r in rows:
            for c in (r.get("data") or {}).get("colonies", []):
                for ex in c["extractors"]:
                    if not ex.get("head_positions") or ex["ecu"][0] is None:
                        continue
                    key = f"{r['character_id']}:{c['planet_id']}:{ex['pin_id']}:{ex.get('install_time')}"
                    added += key not in layouts
                    layouts[key] = {
                        "character_id": r["character_id"], "character_name": r["character_name"],
                        "planet_id": c["planet_id"], "planet_name": c.get("planet_name"), "planet_type": c["planet_type"],
                        "system": c.get("system"), "resource": ex["type_id"], "resource_ja": sde.name(ex["type_id"])[0], "resource_en": sde.name(ex["type_id"])[1],
                        "ecu": ex["ecu"], "heads": ex["head_positions"], "head_radius": ex["head_radius"],
                        "cycle_time": ex["cycle_time"], "qty_per_cycle": ex["qty_per_cycle"], "per_day": ex["per_day"],
                        "per_head_day": ex["per_day"] / len(ex["head_positions"]),
                        "install_time": ex.get("install_time"), "expiry": ex.get("expiry"), "recorded_at": now,
                    }
        if len(layouts) > MAX_LAYOUTS:  # 古いものから消す
            keep = sorted(layouts.items(), key=lambda kv: kv[1].get("install_time") or "")[-MAX_LAYOUTS:]
            layouts = dict(keep)
        layouts_file().write_text(json.dumps(layouts, ensure_ascii=False), encoding="utf-8")
    return added


def register(app, ctx):
    core, live, sde = ctx.core, ctx.live, ctx.sde

    def need_sde():
        if not sde.ready:
            if sde.status["state"] != "building":
                sde.build_async()
            return error(tr("静的データ（SDE）を準備しています（{0}%）。しばらくしてから開き直してください。", (sde.status.get('progress', 0))), 503)
        return None

    def planet_info(planet_id):
        try:
            return live.public(f"/universe/planets/{planet_id}/", ttl=86400 * 7)
        except (RuntimeError, requests.RequestException):
            return {"name": str(planet_id), "type_id": None}

    def colony_loader(force):
        """キャラクター 1 人分のコロニーを読む関数（スレッドの中では request を読めないので force を先に渡す）。"""
        return lambda cid, name: load_colonies(cid, name, force)

    def load_colonies(cid, name, force=False):
        planets = live.get(cid, f"/characters/{cid}/planets/", core.SCOPE_PLANETS, ttl=600, force=force)

        def detail(p):
            d = live.get(cid, f"/characters/{cid}/planets/{p['planet_id']}/", core.SCOPE_PLANETS, ttl=600, force=force)
            view = pi.colony_view(sde, p, d)
            view["planet_name"] = planet_info(p["planet_id"])["name"]
            return view
        with ThreadPoolExecutor(max_workers=4) as pool:
            colonies = list(pool.map(detail, planets))
        levels = skill_levels(ctx, cid)
        return {"colonies": colonies, "max_planets": 1 + levels.get(pi.SKILL_INTERPLANETARY_CONSOLIDATION, 0)}

    def name_all(rows):
        systems = resolve_names(ctx, {c["solar_system_id"] for r in rows for c in (r.get("data") or {}).get("colonies", [])})
        for r in rows:
            for c in (r.get("data") or {}).get("colonies", []):
                c["system"] = systems.get(c["solar_system_id"])
                for ex in c["extractors"]:
                    ex["ja"], ex["en"] = sde.name(ex["type_id"])
                c["factory_list"] = [{"schematic_id": sid, "count": n, "ja": sde.schematics[sid]["name"][0] or sde.schematics[sid]["name"][1], "en": sde.schematics[sid]["name"][1] or sde.schematics[sid]["name"][0],
                                      "tier": sde.pi_tiers.get(sde.schematics[sid]["output"][0], 0)}
                                     for sid, n in sorted(c["factories"].items(), key=lambda kv: -kv[1])]
                c["factories"] = {str(k): v for k, v in c["factories"].items()}

    @app.get("/api/pi/colonies")
    def api_pi_colonies():
        err = need_sde()
        if err:
            return err
        rows = per_character(selected_characters(ctx), colony_loader(request.args.get("force") == "1"), workers=3)
        name_all(rows)
        recorded = record_layouts(sde, rows)  # 開くたびに今の配置を記録する
        return jsonify({"characters": rows, "recorded": recorded})

    @app.get("/api/pi/layouts")
    def api_pi_layouts():
        """記録した抽出機の配置（ヘッド 1 本あたりの抽出量が多い順）。"""
        layouts = sorted(load_layouts().values(), key=lambda x: -(x.get("per_head_day") or 0))
        for x in layouts:  # 英語名の無い古い記録
            x.setdefault("resource_en", sde.name(x["resource"])[1])
        return jsonify({"layouts": layouts})

    @app.get("/api/pi/plan")
    def api_pi_plan():
        err = need_sde()
        if err:
            return err
        rows = per_character(selected_characters(ctx), colony_loader(request.args.get("force") == "1"), workers=3)
        colonies = []
        for r in rows:
            for c in (r.get("data") or {}).get("colonies", []):
                colonies.append({**c, "character_id": r["character_id"], "character_name": r["character_name"]})
        items, factories = pi.simulate(sde, colonies)
        measured = pi.p0_per_planet(colonies) if any(c["extractors"] for c in colonies) else None
        per_planet = float_arg("per_planet", 0) or measured or pi.DEFAULT_P0_PER_PLANET
        result = pi.suggestions(sde, items, factories, per_planet)

        # 拠点の星系（指定が無ければコロニーが一番多い星系）
        system_arg = request.args.get("system", "").strip()
        counts = {}
        for c in colonies:
            counts[c["solar_system_id"]] = counts.get(c["solar_system_id"], 0) + 1
        system_id = None
        if system_arg.isdigit():
            system_id = int(system_arg)
        elif system_arg:
            try:
                found = core.esi_post("/universe/ids/", [system_arg]).get("systems", [])
                system_id = found[0]["id"] if found else None
            except (RuntimeError, requests.RequestException):
                system_id = None
            if not system_id:
                return error(tr("「{0}」という星系が見つかりません", system_arg))
        elif counts:
            system_id = max(counts, key=counts.get)
        home = home_planets(system_id, colonies) if system_id else None

        free = {}
        for r in rows:
            data = r.get("data")
            if data:
                free[r["character_id"]] = {"name": r["character_name"],
                                           "free": data["max_planets"] - len(data["colonies"]),
                                           "max": data["max_planets"], "used": len(data["colonies"])}
        assign_actions(result, home, free, colonies, per_planet)
        values = end_product_values(items, factories, result)
        system_names = resolve_names(ctx, counts)
        return jsonify({
            "characters": [{k: v for k, v in r.items() if k != "data"} for r in rows],
            "items": [describe_item(t, v) for t, v in sorted(items.items(), key=lambda kv: (kv[1]["tier"], sde.name(kv[0])[0]))],
            "factories": [describe_factory(sid, f) for sid, f in sorted(factories.items(), key=lambda kv: -sde.pi_tiers.get(kv[1]["type_id"], 0))],
            "plans": [describe_plan(p) for p in result["plans"]],
            "leftover": [{**x, "ja": sde.name(x["type_id"])[0], "en": sde.name(x["type_id"])[1]} for x in result["leftover"]],
            "per_planet": per_planet, "per_planet_measured": measured,
            "home": home, "systems": [{"id": k, "name": system_names.get(k) or str(k), "count": v}
                                      for k, v in sorted(counts.items(), key=lambda kv: -kv[1])],
            "free": [{"character_id": k, **v} for k, v in free.items()], "values": values,
            "stopped_extractors": sum(not ex["active"] for c in colonies for ex in c["extractors"]),
        })

    def resolve_home(system_arg, colonies):
        """拠点の星系 ID（指定 → コロニーが一番多い星系）。見つからなければ ValueError。"""
        if system_arg.isdigit():
            return int(system_arg)
        if system_arg:
            try:
                found = core.esi_post("/universe/ids/", [system_arg]).get("systems", [])
            except (RuntimeError, requests.RequestException):
                found = []
            if not found:
                raise ValueError(tr("「{0}」という星系が見つかりません", system_arg))
            return found[0]["id"]
        counts = {}
        for c in colonies:
            counts[c["solar_system_id"]] = counts.get(c["solar_system_id"], 0) + 1
        return max(counts, key=counts.get) if counts else None

    @app.get("/api/pi/redesign")
    def api_pi_redesign():
        """全キャラクターのコロニーを作り直す前提で、一番稼げる配置を計算する。"""
        err = need_sde()
        if err:
            return err
        chars = selected_characters(ctx)
        rows = per_character(chars, colony_loader(False), workers=3)
        colonies = [{**c, "character_id": r["character_id"], "character_name": r["character_name"]}
                    for r in rows for c in (r.get("data") or {}).get("colonies", [])]
        try:
            system_id = resolve_home(request.args.get("system", "").strip(), colonies)
        except ValueError as e:
            return error(str(e))
        if not system_id:
            return error("拠点の星系を入力してください（今のコロニーが無いため自動で決められません）")
        home = home_planets(system_id, colonies)
        if not home:
            return error("星系の情報を取得できませんでした", 502)

        # ヘッド 1 本の 1 日の抽出量: 指定 → 今の抽出機の平均 → 目安
        heads = sum(ex["heads"] for c in colonies for ex in c["extractors"])
        measured = sum(ex["per_day"] for c in colonies for ex in c["extractors"]) / heads if heads else None
        per_head = float_arg("per_head", 0) or measured or pi_planner.DEFAULT_PER_HEAD

        slots, levels = [], []
        for cid, name in chars:
            lv = skill_levels(ctx, cid)
            if not lv:
                continue  # スキルを取得していないキャラクター
            n = 1 + lv.get(pi.SKILL_INTERPLANETARY_CONSOLIDATION, 0)
            ccu = lv.get(pi_planner.SKILL_COMMAND_CENTER_UPGRADES, 0)
            levels.append({"character_id": cid, "name": name, "slots": n, "ccu": ccu,
                           "design": pi_planner.extraction_design(ccu, per_head),
                           "factory_capacity": pi_planner.factory_capacity(ccu)})
            slots += [{"character_id": cid, "name": name, "level": ccu, "slot": i} for i in range(n)]
        if not slots:
            return error("キャラクターのスキルが取得できていません。スキルチェッカーで更新してください。")

        products = [t for t, tier in sde.pi_tiers.items() if tier >= 1]
        side = "buy" if request.args.get("price") == "buy" else "sell"
        prices_raw, _ = safe(jita_prices, ctx, products)
        prices = {t: (p or {}).get(side) for t, p in (prices_raw or {}).items()}
        target = int(request.args.get("target")) if request.args.get("target", "").isdigit() else None
        result = pi_planner.redesign(sde, slots, home, prices, per_head, target)

        # 今の配置の 1 日の生産額（比較用）
        items, factories = pi.simulate(sde, colonies)
        consumed = {t for sid in factories for t, _ in sde.schematics[sid]["inputs"]}
        current = sum(v["supply"] * (prices.get(t) or 0) for t, v in items.items()
                      if v["tier"] >= 1 and t not in consumed)

        def p1_of(p0):
            for sid, sc in sde.schematics.items():
                if len(sc["inputs"]) == 1 and sc["inputs"][0][0] == p0:
                    return sc["output"][0], sc["output"][1] / sc["inputs"][0][1]
            return None, 0

        layout = []
        for x in result["layout"]:
            row = {"character_id": x["character_id"], "name": x["name"], "slot": x["slot"], "role": x["role"],
                   "level": x["level"], "product": x["product"], "product_ja": sde.name(x["product"])[0], "product_en": sde.name(x["product"])[1],
                   "planet": {k: x["planet"][k] for k in ("planet_id", "name", "kind")}}
            if x["role"] == "extract":
                p1, ratio = p1_of(x["resource"])
                row.update(resource=x["resource"], resource_ja=sde.name(x["resource"])[0], resource_en=sde.name(x["resource"])[1],
                           ecus=x["ecus"],
                           heads=x["heads"], heads_per_ecu=x["heads_per_ecu"], basic=x["basic"],
                           launchpad=x["launchpad"], p0_per_day=x["p0_per_day"],
                           p1=p1, p1_ja=sde.name(p1)[0] if p1 else None, p1_en=sde.name(p1)[1] if p1 else None, p1_per_day=x["p0_per_day"] * ratio)
            else:
                row["factories"] = [{"schematic_id": sid, "ja": sde.schematics[sid]["name"][0] or sde.schematics[sid]["name"][1], "en": sde.schematics[sid]["name"][1] or sde.schematics[sid]["name"][0],
                                     "tier": sde.pi_tiers.get(sde.schematics[sid]["output"][0], 0), "count": n}
                                    for sid, n in sorted(x.get("factories", {}).items(),
                                                         key=lambda kv: -sde.pi_tiers.get(sde.schematics[kv[0]]["output"][0], 0))]
            layout.append(row)
        layout.sort(key=lambda r: (r["name"], r["role"] != "factory", r["planet"]["name"] or ""))
        return jsonify({
            "home": {k: home[k] for k in ("id", "name", "security")},
            "home_planets": [{k: p[k] for k in ("planet_id", "name", "kind", "resources")} for p in home["planets"]],
            "per_head": per_head, "per_head_measured": measured, "price_side": side,
            "characters": levels, "total_slots": len(slots),
            "ranking": [{**r, "ja": sde.name(r["type_id"])[0], "en": sde.name(r["type_id"])[1], "price": prices.get(r["type_id"])} for r in result["ranking"]],
            "products": [{"type_id": c["type_id"], "ja": sde.name(c["type_id"])[0], "en": sde.name(c["type_id"])[1], "tier": c["tier"], "per_day": c["per_day"],
                          "isk_per_day": c["isk_per_day"], "price": prices.get(c["type_id"]),
                          "p0": [{"type_id": t, "ja": sde.name(t)[0], "en": sde.name(t)[1], "per_day": a * c["per_day"]} for t, a in c["chain"]["p0"].items()]}
                         for c in result["products"]],
            "layout": layout, "unused": len(result["unused"]),
            "total_isk_per_day": sum(c["isk_per_day"] for c in result["products"]), "current_isk_per_day": current,
            "errors": [{k: v for k, v in r.items() if k != "data"} for r in rows if not r.get("data")],
        })

    def home_planets(system_id, colonies):
        try:
            system = live.public(f"/universe/systems/{system_id}/", ttl=86400)
        except (RuntimeError, requests.RequestException):
            return None
        with ThreadPoolExecutor(max_workers=6) as pool:
            infos = list(pool.map(lambda p: planet_info(p["planet_id"]), system.get("planets", [])))
        planets = []
        for p, info in zip(system.get("planets", []), infos):
            kind = sde.planet_types.get(info.get("type_id"))
            users = sorted({c["character_name"] for c in colonies if c["planet_id"] == p["planet_id"]})
            planets.append({"planet_id": p["planet_id"], "name": info.get("name"), "kind": kind,
                            "resources": [{"type_id": t, "ja": sde.name(t)[0], "en": sde.name(t)[1]} for t in sde.planet_resources.get(kind, [])],
                            "resource_ids": sde.planet_resources.get(kind, []), "users": users})
        return {"id": system_id, "name": system.get("name"), "security": system.get("security_status"),
                "planets": planets}

    def assign_actions(result, home, free, colonies, per_planet):
        """提案ごとに「どのキャラクターが、どの惑星で」を割り当てる。空き枠 → 余っている抽出の切り替え の順。"""
        slots = {cid: dict(v) for cid, v in free.items()}
        leftovers = {}
        for x in result["leftover"]:
            if x["planets"] is None or x["planets"] < 0.5:
                continue
            p0 = x["type_id"] if x["tier"] == 0 else sde.schematics[pi.producer_schematic(sde, x["type_id"])]["inputs"][0][0]
            leftovers[p0] = leftovers.get(p0, 0) + x["planets"]
        used_convert = set()
        for plan in result["plans"]:
            actions = []
            for t, planets in plan["planets"].items():
                if planets < SMALL_PLANET_SHARE:
                    actions.append({"kind": "adjust", "type_id": t, "planets": planets})
                    continue
                for _ in range(math.ceil(planets - 1e-9)):
                    candidates = [p for p in (home or {}).get("planets", []) if any(r["type_id"] == t for r in p["resources"])]
                    choice = None
                    for cid, s in sorted(slots.items(), key=lambda kv: -kv[1]["free"]):
                        if s["free"] <= 0:
                            continue
                        own = {c["planet_id"] for c in colonies if c["character_id"] == cid}
                        planet = next((p for p in candidates if p["planet_id"] not in own), None)
                        if planet or not home:
                            choice = (cid, planet)
                            break
                    if choice:
                        cid, planet = choice
                        slots[cid]["free"] -= 1
                        if planet:
                            planet.setdefault("planned", []).append(slots[cid]["name"])
                        actions.append({"kind": "new", "type_id": t, "character_id": cid, "character_name": slots[cid]["name"],
                                        "planet": planet and {"planet_id": planet["planet_id"], "name": planet["name"], "kind": planet["kind"]},
                                        "no_planet": bool(home) and not planet})
                        continue
                    # 空き枠が無い: 余っている資源を抽出しているコロニーを切り替える
                    conv = None
                    for p0, amount in sorted(leftovers.items(), key=lambda kv: -kv[1]):
                        if amount < 0.5:
                            continue
                        col = next((c for c in colonies if (c["character_id"], c["planet_id"]) not in used_convert
                                    and any(ex["type_id"] == p0 for ex in c["extractors"])), None)
                        if col:
                            conv = (p0, col)
                            break
                    if conv:
                        p0, col = conv
                        leftovers[p0] -= 1
                        used_convert.add((col["character_id"], col["planet_id"]))
                        can = t in sde.planet_resources.get(col["planet_type"], [])
                        actions.append({"kind": "convert", "type_id": t, "from_type_id": p0,
                                        "character_id": col["character_id"], "character_name": col["character_name"],
                                        "planet": {"planet_id": col["planet_id"], "name": col.get("planet_name"), "kind": col["planet_type"]},
                                        "same_planet": can})
                    else:
                        actions.append({"kind": "no_slot", "type_id": t})
            plan["actions"] = actions

    def end_product_values(items, factories, result):
        """最終製品の 1 日の生産額（今と、提案どおりにしたとき）。Jita の買い値・売り値。"""
        consumed = {t for sid in factories for t, _ in sde.schematics[sid]["inputs"]}
        ends = {f["type_id"] for f in factories.values() if f["type_id"] not in consumed}
        gains = {p["type_id"]: p["gain_per_day"] for p in result["plans"]}
        if not ends:
            return []
        prices, _ = safe(jita_prices, ctx, ends)
        prices = prices or {}
        rows = []
        for t in ends:
            now = items[t]["supply"]
            p = prices.get(t, {})
            rows.append({"type_id": t, "ja": sde.name(t)[0], "en": sde.name(t)[1], "per_day": now, "gain": gains.get(t, 0),
                         "sell": p.get("sell"), "buy": p.get("buy")})
        rows.sort(key=lambda r: -((r["sell"] or 0) * r["per_day"]))
        return rows

    def describe_item(t, v):
        ja, en = sde.name(t)
        return {"type_id": t, "ja": ja, "en": en, **v, "surplus": v["supply"] - v["used"], "shortage": v["demand"] - v["used"]}

    def describe_factory(sid, f):
        s = sde.schematics[sid]
        return {"schematic_id": sid, "ja": s["name"][0] or s["name"][1], "en": s["name"][1] or s["name"][0], "tier": sde.pi_tiers.get(f["type_id"], 0), **f}

    def describe_plan(p):
        s = sde.schematics[p["schematic_id"]]
        plan = p["plan"]
        return {
            "schematic_id": p["schematic_id"], "type_id": p["type_id"], "ja": s["name"][0] or s["name"][1], "en": s["name"][1] or s["name"][0],
            "tier": sde.pi_tiers.get(p["type_id"], 0), "utilization": p["utilization"], "count": p["count"],
            "gain_per_day": p["gain_per_day"], "total_planets": p["total_planets"],
            "short": [{"type_id": t, "ja": sde.name(t)[0], "en": sde.name(t)[1], "amount": a} for t, a in p["short"].items() if a > 1e-6],
            "use_surplus": [{"type_id": t, "ja": sde.name(t)[0], "en": sde.name(t)[1], "amount": a} for t, a in plan["use_surplus"].items()],
            "idle": [{"schematic_id": sid, "ja": sde.schematics[sid]["name"][0], "en": sde.schematics[sid]["name"][1] or sde.schematics[sid]["name"][0], "amount": a,
                      "type_id": sde.schematics[sid]["output"][0]} for sid, a in plan["idle"].items()],
            "new_factories": [{"schematic_id": sid, "ja": sde.schematics[sid]["name"][0], "en": sde.schematics[sid]["name"][1] or sde.schematics[sid]["name"][0], "count": n,
                               "tier": sde.pi_tiers.get(sde.schematics[sid]["output"][0], 0)} for sid, n in plan["factories"].items()],
            "extract": [{"type_id": t, "ja": sde.name(t)[0], "en": sde.name(t)[1], "amount": a, "planets": p["planets"][t]}
                        for t, a in plan["extract"].items()],
            "actions": [{**a, "ja": sde.name(a["type_id"])[0], "en": sde.name(a["type_id"])[1],
                         **({"from_ja": sde.name(a["from_type_id"])[0], "from_en": sde.name(a["from_type_id"])[1]} if a.get("from_type_id") else {})}
                        for a in p.get("actions", [])],
        }
