"""フィットの作成: 艦とモジュール・ドローン・カーゴを選ぶと、スロット・PG / CPU・DPS・容量・整列時間・
ワープコアの強度・必要なスキル・購入費を計算し、EFT 形式（ゲームにインポートできる）で出す。"""

import requests
from flask import jsonify, request

import align
import fit_rules
import fitting
import skill_check
from i18n import tr
from recommend import t1_name

from .common import error, skill_levels

SLOT_ORDER = ["low", "med", "high", "rig", "subsystem"]
SLOT_LABELS = {"high": "ハイスロット", "med": "ミッドスロット", "low": "ロースロット", "rig": "リグ", "subsystem": "サブシステム"}
DRONE_CATEGORY = 18
# メタグループ → 表示名（仲間の装備の選択肢に出すもの。士官・アビサルなどは出さない）
META_GROUPS = {1: "T1", 2: "T2", 3: "ストーリーライン", 4: "勢力", 6: "デッドスペース", 14: "T3"}
META_ORDER = [1, 2, 3, 4, 6, 14]
CHARGE_CATEGORY = 8


def register(app, ctx):
    data, type_cache, catalog = ctx.fitting_data, ctx.type_cache, ctx.catalog

    def names(t):
        item = catalog.get(t)
        if item:
            return item["ja"], item["en"]
        name = type_cache.get(t)["name"]
        return name, name

    def can_use(t, levels):
        """そのキャラクターのスキルで使えるか（直接の必要スキルを満たしているか）。"""
        return all(levels.get(s, 0) >= lv for s, lv in type_cache.get(t)["requirements"])

    def variants_of(t, levels):
        """同じ装備の仲間（T1・メタ 1〜4・T2・勢力など）と、それぞれ使えるか。"""
        sde = ctx.sde
        if not sde.ready:
            return []
        parent = sde.variant_parent.get(t)
        rows = [r for r in sde.variants.get(parent, []) if r[1] in META_GROUPS] if parent else []
        if len(rows) < 2:
            return []
        type_cache.ensure([r[0] for r in rows])
        out = []
        for tid, group, level in rows:
            label = META_GROUPS[group] if group != 1 or not level else tr("メタ {0}", level)
            out.append({"type_id": tid, "ja": names(tid)[0], "en": names(tid)[1], "label": label, "group": group, "level": level,
                        "usable": can_use(tid, levels), "current": tid == t})
        out.sort(key=lambda v: (META_ORDER.index(v["group"]), v["level"], v["ja"]))
        return out

    def t1_of(t):
        """T1 版の type_id（T2 の装備・ドローン・リグ・弾だけ。無ければ None）。"""
        en = names(t)[1]
        name = t1_name(catalog, en)
        return catalog.find_by_name(name) if name != en else None

    _volumes = {}

    def volume_of(t):
        if t not in _volumes:
            item = catalog.get(t)
            _volumes[t] = item.get("volume") if item and item.get("volume") is not None else \
                ctx.core.esi_get(f"/universe/types/{t}/").get("volume", 0)
        return _volumes[t] or 0

    def category_of(t):
        group = data.types[t]["group_id"]
        try:
            return ctx.live.public(f"/universe/groups/{group}/", ttl=86400 * 7).get("category_id")
        except (RuntimeError, requests.RequestException):
            return None

    def item_info(t):
        data.ensure([t])
        ja, en = names(t)
        slot = fit_rules.slot_of(data, t)
        cat = category_of(t)
        kind = "module" if slot else "drone" if cat == DRONE_CATEGORY else "charge" if cat == CHARGE_CATEGORY else "other"
        effects = set(data.types[t]["effects"])
        return {"type_id": t, "ja": ja, "en": en, "kind": kind, "slot": slot,
                "turret": fit_rules.EFFECT_TURRET in effects, "launcher": fit_rules.EFFECT_LAUNCHER in effects,
                "cpu": data.attr(t, 50, 0), "pg": data.attr(t, 30, 0), "volume": volume_of(t)}

    @app.get("/api/fitbuilder/item")
    def api_fitbuilder_item():
        try:
            return jsonify(item_info(int(request.args.get("type_id", ""))))
        except (ValueError, KeyError, RuntimeError, requests.RequestException) as e:
            return error(tr("アイテムの情報を取得できませんでした: {0}", e))

    @app.post("/api/fitbuilder/import")
    def api_fitbuilder_import():
        """EFT 形式のテキスト → 艦・モジュール・ドローン・カーゴ（作成ページに読み込む）。"""
        text = (request.get_json(silent=True) or {}).get("eft", "")
        try:
            parsed = skill_check.parse_eft(text)
        except ValueError as e:
            return error(str(e))
        want = [parsed["ship"], *parsed["items"]]
        ids = {n: catalog.find_by_name(n) for n in want}
        rest = [n for n, t in ids.items() if not t]
        if rest:
            for n, (t, _) in type_cache.resolve_names(rest).items():
                ids[n] = t
        ship = ids.get(parsed["ship"])
        if not ship:
            return error(tr("艦「{0}」が見つかりません", parsed['ship']))
        modules = [ids[n] for n in parsed["fitted"] if ids.get(n)]
        drones, cargo = [], []
        for n, q in parsed["bay"]:
            t = ids.get(n)
            if not t:
                continue
            (drones if item_info(t)["kind"] == "drone" else cargo).append([t, q])
        # 装填していた弾はカーゴに無ければ 1 セット分入れておく（自動で装填するため）
        for c in {ids[c] for c in parsed["loaded"] if c and ids.get(c)}:
            if not any(t == c for t, _ in cargo):
                cargo.append([c, 1])
        return jsonify({"ship_type_id": ship, "name": parsed["name"], "modules": modules, "drones": drones,
                        "cargo": cargo, "unresolved": [n for n in want if not ids.get(n)]})

    @app.post("/api/fitbuilder/evaluate")
    def api_fitbuilder_evaluate():
        body = request.get_json(silent=True) or {}
        try:
            ship = int(body.get("ship_type_id"))
            modules = [int(t) for t in body.get("modules", [])]
            drones = [(int(t), max(1, int(q))) for t, q in body.get("drones", [])]
            cargo = [(int(t), max(1, int(q))) for t, q in body.get("cargo", [])]
        except (TypeError, ValueError):
            return error("フィットの内容が不正です")
        name = str(body.get("name") or "").strip()[:100]
        char_id = body.get("character_id")
        data.ensure([ship, *modules, *[t for t, _ in drones + cargo]])

        rec = ctx.recommender()
        character = next((c for c in ctx.ready_characters() if c["character_id"] == char_id), None)
        if not character:  # キャラクターがいないときは全スキル V
            character = {**rec.all_v_character(), "character_name": "全スキル V",
                         "attributes": {"perception": 20, "memory": 20, "willpower": 20, "intelligence": 20, "charisma": 19}}
        levels = {s["skill_id"]: s["trained_level"] for s in character["skills"]}

        # 弾の自動装填: カーゴの弾のうち、そのモジュールに入る最初のもの
        loaded = []
        for m in modules:
            charge = next((t for t, _ in cargo if fit_rules.can_load(data, m, t)), None)
            loaded.append(charge)
        bay = drones + cargo
        cost = lambda targets: skill_check.build_plan(type_cache, [], character, targets)["total_minutes"]  # noqa: E731
        res = fitting.check_resources(data, type_cache, ship, modules, character, cost)
        dps = rec.calc.compute(ship, modules, loaded, bay, levels)
        name_of = lambda t: names(t)[0]  # noqa: E731
        errors = fit_rules.fit_errors(data, name_of, ship, modules, drones, volume_of)
        labels = {"power": "パワーグリッド", "cpu": "CPU", "calibration": "キャリブレーション"}
        for k, label in labels.items():
            if not res[k]["ok"]:
                errors.append(tr("{0}が足りません（{1:.1f} / {2:.1f}）", label, res[k]['used'], res[k]['total']))
        cargo_volume = sum(volume_of(t) * q for t, q in cargo)
        cargo_cap = (res["holds"].get("cargo") or {}).get("total", 0)
        if cargo_volume > cargo_cap + 1e-6:
            errors.append(tr("カーゴに入りません（{0:,.1f} / {1:,.1f} m³）", cargo_volume, cargo_cap))

        type_ids = sorted({ship, *modules, *[t for t, _ in bay]})
        plan = skill_check.build_plan(type_cache, type_ids, character,
                                      {s["skill_id"]: s["to"] for s in (res.get("suggestion") or {}).get("skills", [])})
        usage = fit_rules.slot_usage(data, ship, modules)
        slots = {s: [] for s in SLOT_ORDER}
        for i, (m, c) in enumerate(zip(modules, loaded)):
            ja, en = names(m)
            has_charge = bool({int(data.attr(m, a, 0)) for a in fit_rules.CHARGE_GROUP_ATTRS} - {0})
            slots.setdefault(fit_rules.slot_of(data, m) or "other", []).append({
                "index": i, "type_id": m, "ja": ja, "en": en, "charge": c and names(c)[0], "charge_en": c and names(c)[1],
                "needs_charge": has_charge, "t1": t1_of(m), "usable": can_use(m, levels),
                "variants": variants_of(m, levels)})
        ship_ja, ship_en = names(ship)

        # EFT（ゲームのインポート用。英語名）
        lines = [f"[{ship_en}, {name or ship_en}]"]
        for s in SLOT_ORDER:
            if slots.get(s):
                lines += [x["en"] + (f", {x['charge_en']}" if x["charge_en"] else "") for x in slots[s]] + [""]
        if drones:
            lines += [f"{names(t)[1]} x{q}" for t, q in drones] + [""]
        if cargo:
            lines += [f"{names(t)[1]} x{q}" for t, q in cargo]
        eft = "\n".join(lines).strip() + "\n"

        ws = fit_rules.warp_strength(data, ship, modules)
        al = align.align_times(data, ship, modules, levels)
        return jsonify({
            "ship": {"type_id": ship, "ja": ship_ja, "en": ship_en}, "name": name or ship_en,
            "character_name": character.get("character_name", "全スキル V"),
            "slots": slots, "usage": usage, "slot_labels": SLOT_LABELS,
            "drones": [{"type_id": t, "qty": q, "ja": names(t)[0], "en": names(t)[1], "volume": volume_of(t), "t1": t1_of(t),
                        "usable": can_use(t, levels), "variants": variants_of(t, levels),
                        "bandwidth": data.attr(t, fit_rules.ATTR_DRONE_BANDWIDTH_USED, 0)} for t, q in drones],
            "cargo": [{"type_id": t, "qty": q, "ja": names(t)[0], "en": names(t)[1], "volume": volume_of(t), "t1": t1_of(t),
                       "usable": can_use(t, levels), "variants": variants_of(t, levels)} for t, q in cargo],
            "drone_bay": {"used": sum(volume_of(t) * q for t, q in drones), "total": data.attr(ship, fit_rules.ATTR_DRONE_BAY, 0),
                          "bandwidth": data.attr(ship, fit_rules.ATTR_DRONE_BANDWIDTH, 0)},
            "cargo_volume": {"used": cargo_volume, "total": cargo_cap},
            "resources": {k: res[k] for k in ("power", "cpu", "calibration")}, "approximate": res["approximate"],
            "suggestion": res.get("suggestion"), "holds": res["holds"], "dps": dps,
            "align": {"normal": al["normal"], "trick": al["trick"], "effective": al["effective"]},
            "warp_strength": ws, "errors": errors,
            "skills": {"minutes": plan["total_minutes"], "steps": len(plan["steps"]),
                       "usable": not plan["steps"] and res["ok"]},
            "type_ids": type_ids, "plan_skills": [[s["skill_id"], s["to"]] for s in (res.get("suggestion") or {}).get("skills", [])],
            "bom": [[ship, 1, "ship"], *[[t, 1, "module"] for t in modules], *[[t, q, "bay"] for t, q in bay]],
            "eft": eft,
        })
