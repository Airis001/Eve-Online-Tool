"""便利な道具: 査定・D-Scan・ローカルの危険度・星系の最近の撃墜・サーバーの状態・属性の割り振り・ステーション内トレードの候補。"""

import contextvars
import itertools
import re
import threading
import time
from datetime import datetime, timedelta, timezone

import requests
from flask import jsonify, request

import accounts
import skill_check
from accounts import ThreadPoolExecutor
from i18n import tr
from live import EsiForbidden, ScopeMissing, safe

from .common import (JITA_REGION_ID, JITA_STATION_ID, average_prices, error, int_arg, jita_prices, resolve_names,
                     skill_levels, type_name, undercut)
from .money import standing_reductions

ZKILL = "https://zkillboard.com/api"
ZKILL_HEADERS = {"User-Agent": "EVE skill checker (personal desktop tool)", "Accept-Encoding": "gzip"}
ATTRS = ["perception", "memory", "willpower", "intelligence", "charisma"]
ATTR_JA = {"perception": "知覚", "memory": "記憶", "willpower": "意志", "intelligence": "知性", "charisma": "魅力"}
IMPLANT_ATTRS = {178: "perception", 177: "memory", 179: "willpower", 176: "intelligence", 175: "charisma"}
BASE_ATTR, MAX_ATTR, REMAP_POINTS = 17, 27, 14
SKILL_ACCOUNTING, SKILL_BROKER_RELATIONS = 16622, 3446
MAX_TRADE_MARGIN = 100  # ステーション内トレードの候補にする利益率の上限（%）
MIN_TRADE_VOLUME = 5    # 1 日の取引量（7 日平均）の下限

# 艦のグループ → 大きさの区分（D-Scan の集計用）
SHIP_CLASS = {
    "フリゲート": ["Frigate", "Assault Frigate", "Interceptor", "Covert Ops", "Stealth Bomber", "Electronic Attack Ship",
               "Expedition Frigate", "Logistics Frigate", "Prototype Exploration Ship"],
    "駆逐艦": ["Destroyer", "Interdictor", "Tactical Destroyer", "Command Destroyer"],
    "巡洋艦": ["Cruiser", "Heavy Assault Cruiser", "Logistics", "Recon Ship", "Combat Recon Ship", "Force Recon Ship",
            "Heavy Interdiction Cruiser", "Strategic Cruiser", "Flag Cruiser"],
    "巡洋戦艦": ["Combat Battlecruiser", "Attack Battlecruiser", "Command Ship"],
    "戦艦": ["Battleship", "Black Ops", "Marauder"],
    "キャピタル": ["Carrier", "Dreadnought", "Force Auxiliary", "Supercarrier", "Titan", "Lancer Dreadnought"],
    "輸送・生産": ["Hauler", "Deep Space Transport", "Blockade Runner", "Freighter", "Jump Freighter", "Industrial Command Ship",
              "Capital Industrial Ship", "Mining Barge", "Exhumer"],
}
GROUP_TO_CLASS = {g: c for c, groups in SHIP_CLASS.items() for g in groups}

_zkill_cache = {}
_zkill_lock = threading.Lock()
_trade_jobs = {}  # アカウント → ステーション内トレードの候補を調べるジョブ
_trade_lock = threading.Lock()


def trade_job():
    """いまのアカウントのジョブ。"""
    return _trade_jobs.setdefault(accounts.current_uid(),
                                  {"state": "idle", "progress": 0, "at": None, "result": None, "error": None})


def zkill_get(path, ttl=3600):
    """zKillboard の API（キャッシュ付き。短時間に叩きすぎないよう少し待つ）。"""
    with _zkill_lock:
        hit = _zkill_cache.get(path)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
    res = requests.get(f"{ZKILL}{path}", headers=ZKILL_HEADERS, timeout=20)
    res.raise_for_status()
    data = res.json()
    with _zkill_lock:
        _zkill_cache[path] = (time.time(), data)
    return data


def parse_qty(text):
    # 桁区切り: カンマ・空白・ノーブレークスペースなど（クライアントの言語設定で変わる）
    text = re.sub(r"[,\s  　']", "", text or "")
    if re.fullmatch(r"\d+(\.\d+)?", text):
        return int(float(text))
    return None


def clean_name(name):
    """ゲームからコピーした名前の整形。日本語クライアントは名前の末尾に「*」を付けることがある。"""
    return (name or "").replace("　", " ").strip().rstrip("*").strip()


def register(app, ctx):
    core, live, catalog = ctx.core, ctx.live, ctx.catalog

    def find_type(name):
        name = clean_name(name)
        if not name:
            return None
        return catalog.find_by_name(name)

    # ---------- 3. 査定 ----------

    @app.post("/api/tools/appraise")
    def api_appraise():
        text = (request.get_json(silent=True) or {}).get("text", "")
        items, unknown = {}, []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("["):
                continue
            cols = [c.strip() for c in line.split("\t")]
            name, qty = cols[0], 1
            if len(cols) > 1 and parse_qty(cols[1]) is not None:  # インベントリ・契約のコピー（名前\t数量\t…）
                qty = parse_qty(cols[1])
            else:
                m = re.match(r"^(.*?)\s+x\s?([\d,]+)$", line) or re.match(r"^([\d,]+)\s*x?\s+(.*)$", line)
                if m:
                    a, b = m.groups()
                    name, qty = (a, parse_qty(b)) if parse_qty(b) is not None else (b, parse_qty(a))
                name = name.split(",")[0].strip()  # 「モジュール, 弾」
            name = clean_name(name)
            t = find_type(name)
            if not t:
                unknown.append((name, max(qty or 1, 1)))
                continue
            items[t] = items.get(t, 0) + max(qty or 1, 1)
        if unknown:  # 名前一覧に無いもの（英語の正式名）は ESI で探す
            found = ctx.type_cache.resolve_names(list(dict.fromkeys(n for n, _ in unknown))[:200])
            still = []
            for n, q in unknown:
                if n in found:
                    items[found[n][0]] = items.get(found[n][0], 0) + q
                elif n not in still:
                    still.append(n)
            unknown = still
        if not items:
            return error("アイテムが見つかりません。ゲームのインベントリや契約の中身をコピーして貼り付けてください。")
        if len(items) > 300:
            return error("品目が多すぎます（300 種類まで）")
        try:
            prices = jita_prices(ctx, items)
        except (RuntimeError, requests.RequestException) as e:
            return error(tr("価格を取得できませんでした: {0}", str(e).splitlines()[0]), 502)
        rows = []
        for t, q in items.items():
            ja, en = type_name(ctx, t)
            item = catalog.get(t) or {}
            p = prices.get(t, {})
            rows.append({"type_id": t, "ja": ja, "en": en, "qty": q, "sell": p.get("sell"), "buy": p.get("buy"),
                         "sell_total": (p.get("sell") or 0) * q, "buy_total": (p.get("buy") or 0) * q,
                         "volume": (item.get("volume") or 0) * q})
        rows.sort(key=lambda r: -r["sell_total"])
        return jsonify({"items": rows, "unknown": unknown,
                        "sell_total": sum(r["sell_total"] for r in rows), "buy_total": sum(r["buy_total"] for r in rows),
                        "volume": sum(r["volume"] for r in rows)})

    # ---------- 8. D-Scan ----------

    @app.post("/api/tools/dscan")
    def api_dscan():
        text = (request.get_json(silent=True) or {}).get("text", "")
        entries = []
        for line in text.splitlines():
            cols = [c.strip() for c in line.split("\t")]
            if len(cols) < 2:
                continue
            if cols[0].isdigit() and len(cols) >= 3:
                type_id, name, type_label = int(cols[0]), cols[1], cols[2]
                dist = cols[3] if len(cols) > 3 else ""
            else:
                name, type_label = cols[0], cols[1]
                dist = cols[2] if len(cols) > 2 else ""
                type_id = find_type(type_label)
            km = None
            m = re.match(r"^([\d,.]+)\s*(km|m|AU)$", dist.replace(" ", " "))
            if m:
                v = float(m.group(1).replace(",", ""))
                km = v if m.group(2) == "km" else v / 1000 if m.group(2) == "m" else v * 149_597_871
            entries.append({"type_id": type_id, "name": name, "type": type_label, "km": km})
        if not entries:
            return error("D-Scan の結果が見つかりません。指向性スキャナーの一覧をコピーして貼り付けてください。")
        types, classes, others = {}, {}, {}
        on_grid = 0
        for e in entries:
            item = catalog.get(e["type_id"]) if e["type_id"] else None
            ja = item["ja"] if item else e["type"]
            if e["km"] is not None and e["km"] <= 7500:
                on_grid += 1
            if item and item.get("category") == "艦船":
                cls = GROUP_TO_CLASS.get(item.get("group"), "その他の艦")
                key = (e["type_id"], ja, item.get("group"), cls)
                types[key] = types.get(key, 0) + 1
                classes[cls] = classes.get(cls, 0) + 1
            else:
                others[ja] = others.get(ja, 0) + 1
        ships = [{"type_id": k[0], "ja": k[1], "group": k[2], "class": k[3], "count": n}
                 for k, n in sorted(types.items(), key=lambda kv: -kv[1])]
        return jsonify({"total": len(entries), "ship_count": sum(classes.values()), "on_grid": on_grid,
                        "classes": [{"class": c, "count": n} for c, n in sorted(classes.items(), key=lambda kv: -kv[1])],
                        "ships": ships, "others": [{"ja": k, "count": n} for k, n in sorted(others.items(), key=lambda kv: -kv[1])[:40]]})

    # ---------- 7. ローカルの危険度 ----------

    @app.post("/api/tools/local")
    def api_local():
        text = (request.get_json(silent=True) or {}).get("text", "")
        names = list(dict.fromkeys(n.strip() for n in text.splitlines() if n.strip()))[:300]
        if not names:
            return error("ローカルチャットのメンバーの名前を貼り付けてください（1 行に 1 人）")
        found = {}
        for i in range(0, len(names), 500):
            res, _ = safe(core.esi_post, "/universe/ids/", names[i:i + 500])
            for c in (res or {}).get("characters", []):
                found[c["id"]] = c["name"]
        if not found:
            return error("パイロットが見つかりません")
        aff, _ = safe(core.esi_post, "/characters/affiliation/", list(found))
        aff = {a["character_id"]: a for a in aff or []}
        org_names = resolve_names(ctx, {v for a in aff.values() for v in (a.get("corporation_id"), a.get("alliance_id")) if v})

        def stats(cid):
            data, _ = safe(zkill_get, f"/stats/characterID/{cid}/", 3600)
            return cid, data or {}
        with ThreadPoolExecutor(max_workers=3) as pool:
            zk = dict(pool.map(stats, list(found)[:100]))
        pilots = []
        for cid, name in found.items():
            a = aff.get(cid, {})
            z = zk.get(cid, {})
            kills = z.get("shipsDestroyed") or 0
            recent = ((z.get("activepvp") or {}).get("kills") or {}).get("count", 0)
            danger = z.get("dangerRatio")
            # recent は最近の撃墜への関与（損失も含む）なので、撃墜の実績と合わせて判定する
            if ((danger or 0) >= 70 and kills >= 50) or (recent >= 10 and kills >= 20):
                level = "high"
            elif kills >= 20 or (recent >= 3 and kills > 0):
                level = "mid"
            else:
                level = "low"
            pilots.append({"id": cid, "name": name, "corporation": org_names.get(a.get("corporation_id")),
                           "alliance": org_names.get(a.get("alliance_id")), "alliance_id": a.get("alliance_id"),
                           "kills": kills, "losses": z.get("shipsLost") or 0, "danger": danger, "gang": z.get("gangRatio"),
                           "solo": z.get("soloKills") or 0, "recent_kills": recent, "level": level,
                           "zkill": f"https://zkillboard.com/character/{cid}/", "checked": cid in zk})
        pilots.sort(key=lambda p: ({"high": 0, "mid": 1, "low": 2}[p["level"]], -p["recent_kills"], -p["kills"]))
        groups = {}
        for p in pilots:
            key = p["alliance"] or p["corporation"] or "不明"
            groups[key] = groups.get(key, 0) + 1
        return jsonify({"pilots": pilots, "not_found": [n for n in names if n not in found.values()],
                        "groups": [{"name": k, "count": v} for k, v in sorted(groups.items(), key=lambda kv: -kv[1])]})

    # ---------- 9. 星系の最近の撃墜 ----------

    @app.get("/api/tools/system-kills")
    def api_system_kills():
        value = request.args.get("system", "").strip()
        sid = int(value) if value.isdigit() else None
        if not sid and value:
            res, _ = safe(core.esi_post, "/universe/ids/", [value])
            sid = ((res or {}).get("systems") or [{}])[0].get("id")
        if not sid:
            return error("星系名を入力してください（例: Uedama）")
        try:
            kills = zkill_get(f"/kills/solarSystemID/{sid}/", 300)
        except (requests.RequestException, ValueError) as e:
            return error(tr("zKillboard から取得できませんでした: {0}", e), 502)
        kills = sorted(kills, key=lambda k: k.get("killmail_time", ""), reverse=True)[:50]
        now = datetime.now(timezone.utc)
        ids = set()
        for k in kills:
            v = k.get("victim", {})
            ids.update(x for x in (v.get("character_id"), v.get("corporation_id"), v.get("alliance_id")) if x)
            for a in k.get("attackers", [])[:5]:
                ids.update(x for x in (a.get("character_id"), a.get("corporation_id"), a.get("alliance_id")) if x)
        names = resolve_names(ctx, ids)
        rows, attackers_1h = [], {}
        for k in kills:
            when = datetime.fromisoformat(k["killmail_time"].replace("Z", "+00:00"))
            v = k.get("victim", {})
            atk = k.get("attackers", [])
            final = next((a for a in atk if a.get("final_blow")), atk[0] if atk else {})
            if now - when <= timedelta(hours=1):
                for a in atk:
                    key = a.get("alliance_id") or a.get("corporation_id")
                    if key:
                        attackers_1h[key] = attackers_1h.get(key, 0) + 1
            rows.append({
                "id": k["killmail_id"], "time": k["killmail_time"], "minutes_ago": (now - when).total_seconds() / 60,
                "victim": names.get(v.get("character_id")) or "（NPC・建造物）", "victim_ship": type_name(ctx, v["ship_type_id"])[0] if v.get("ship_type_id") else "",
                "victim_group": names.get(v.get("alliance_id")) or names.get(v.get("corporation_id")),
                "attackers": len(atk), "final_blow": names.get(final.get("character_id")) or "NPC",
                "final_ship": type_name(ctx, final["ship_type_id"])[0] if final.get("ship_type_id") else "",
                "attacker_group": names.get(final.get("alliance_id")) or names.get(final.get("corporation_id")),
                "value": (k.get("zkb") or {}).get("totalValue"), "url": f"https://zkillboard.com/kill/{k['killmail_id']}/",
            })
        last_hour = [r for r in rows if r["minutes_ago"] <= 60]
        camp = len(last_hour) >= 3 and any(n >= 3 for n in attackers_1h.values())
        return jsonify({"system_id": sid, "system": names.get(sid) or resolve_names(ctx, {sid}).get(sid), "kills": rows,
                        "last_hour": len(last_hour), "last_day": sum(r["minutes_ago"] <= 1440 for r in rows), "camp": camp})

    # ---------- 10. サーバーの状態 ----------

    @app.get("/api/tools/status")
    def api_status():
        data, err = safe(live.public, "/status/", 60)
        if data is None:
            return jsonify({"online": False, "error": (err or {}).get("error")})
        return jsonify({"online": True, **data})

    # ---------- 4. 属性の割り振り ----------

    @app.post("/api/tools/remap")
    def api_remap():
        body = request.get_json(silent=True) or {}
        char_id = body.get("character_id")
        character = next((c for c in ctx.ready_characters() if c["character_id"] == char_id), None)
        if not character or not character.get("attributes"):
            return error("キャラクターの属性が取得できていません（スキルチェッカーで更新してください）")
        tc = ctx.type_cache
        steps = []  # [(skill_id, 必要 SP)]
        if body.get("mode") == "text":
            targets = {}
            for line in (body.get("text") or "").splitlines():
                m = re.match(r"^(.*?)\s+([1-5IV]+)$", line.strip())
                if not m:
                    continue
                text_lv = m.group(2)
                lv = int(text_lv) if text_lv.isdigit() else {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5}.get(text_lv)
                sid = find_type(m.group(1))
                if sid and lv:
                    targets[sid] = max(targets.get(sid, 0), lv)
            if not targets:
                return error("スキルプランが読み取れません（1 行に「スキル名 レベル」）")
            plan = skill_check.build_plan(tc, [], character, targets)
            for s in plan["steps"]:  # キュー済みでも、まだ訓練が要るので含める
                if s["minutes"] is None:
                    continue
                info = tc.get(s["skill_id"])
                rate = skill_check.sp_per_minute(info, character["attributes"])
                steps.append((s["skill_id"], s["minutes"] * rate))
        else:  # スキルキューの残り
            for q in character.get("skill_queue") or []:
                # そのレベルで訓練する SP（訓練中のものは、途中までの分も含む目安）
                sp = (q.get("level_end_sp") or 0) - max(q.get("training_start_sp") or 0, q.get("level_start_sp") or 0)
                if sp > 0:
                    steps.append((q["skill_id"], sp))
        if not steps:
            return error("訓練するスキルがありません")
        tc.ensure([s for s, _ in steps])
        # 主属性・副属性ごとの必要 SP
        need = {}
        for sid, sp in steps:
            info = tc.get(sid)
            if info.get("primary"):
                key = (info["primary"], info["secondary"])
                need[key] = need.get(key, 0) + sp

        def minutes(attrs):
            return sum(sp / (attrs[p] + attrs[s] / 2) for (p, s), sp in need.items())

        total = dict(character["attributes"])
        bonus = {a: 0 for a in ATTRS}
        implants = character.get("implants") or []
        safe(ctx.fitting_data.ensure, implants)
        for t in implants:
            if t in ctx.fitting_data.types:
                for attr_id, name in IMPLANT_ATTRS.items():
                    bonus[name] += ctx.fitting_data.attr(t, attr_id, 0)
        base_sum = sum(total.get(a, 0) for a in ATTRS)
        includes = base_sum - sum(bonus.values()) == BASE_ATTR * 5 + REMAP_POINTS
        base = {a: total.get(a, 0) - (bonus[a] if includes else 0) for a in ATTRS}
        current = {a: base[a] + bonus[a] for a in ATTRS}

        best = None
        for combo in itertools.product(range(0, 11), repeat=4):
            last = REMAP_POINTS - sum(combo)
            if not 0 <= last <= 10:
                continue
            attrs = {a: BASE_ATTR + p for a, p in zip(ATTRS, (*combo, last))}
            m = minutes({a: attrs[a] + bonus[a] for a in ATTRS})
            if best is None or m < best[0]:
                best = (m, attrs)
        best_min, best_base = best
        with_plus5 = minutes({a: best_base[a] + 5 for a in ATTRS})
        now_min = minutes(current)
        return jsonify({
            "character_name": character["character_name"], "skills": len(steps), "sp": sum(sp for _, sp in steps),
            "current": {"attrs": current, "minutes": now_min}, "base": base, "implant_bonus": bonus,
            "best": {"attrs": best_base, "with_implants": {a: best_base[a] + bonus[a] for a in ATTRS}, "minutes": best_min},
            "best_plus5": {"minutes": with_plus5},
            "current_plus5": {"minutes": minutes({a: base[a] + 5 for a in ATTRS})},
            "bonus_remaps": character["attributes"].get("bonus_remaps"),
            "remap_available": character["attributes"].get("accrued_remap_cooldown_date"),
            "attr_ja": ATTR_JA,
        })

    # ---------- 6. ステーション内トレードの候補 ----------

    def trader_fees(char_id, station_id=JITA_STATION_ID):
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
        chars = ctx.ready_characters()
        if not chars:
            return None
        def key(c):
            lv = {s["skill_id"]: s["trained_level"] for s in c.get("skills", [])}
            return (lv.get(SKILL_BROKER_RELATIONS, 0), lv.get(SKILL_ACCOUNTING, 0))
        return max(chars, key=key)

    # ---------- 今の艦のカーゴを売る ----------

    CARGO_FLAGS = ("Cargo", "FleetHangar")  # と、Specialized…Hold（採掘・ガス・PI などの専用カーゴ）

    @app.get("/api/tools/cargo-sale")
    def api_cargo_sale():
        """キャラクターが今乗っている艦のカーゴの中身を、トレードスキルが一番高いキャラクターが売ったときの金額。"""
        char_id = int_arg("character_id")
        location = int_arg("location", JITA_STATION_ID)
        force = request.args.get("force") == "1"
        try:
            ship = live.get(char_id, f"/characters/{char_id}/ship/", core.SCOPE_SHIP, ttl=30, force=force)
            assets = live.get(char_id, f"/characters/{char_id}/assets/", core.SCOPE_ASSETS, ttl=300, pages=True, force=force)
        except ScopeMissing as e:
            return error(tr("このキャラクターは再ログインが必要です（{0}）", e.scope), 403)
        except (EsiForbidden, RuntimeError, requests.RequestException) as e:
            return error(tr("艦・資産を取得できませんでした: {0}", str(e).splitlines()[0]), 502)
        cargo = {}
        for a in assets:
            flag = a.get("location_flag", "")
            if a["location_id"] == ship["ship_item_id"] and (flag in CARGO_FLAGS or flag.startswith("Specialized")):
                cargo[a["type_id"]] = cargo.get(a["type_id"], 0) + a.get("quantity", 1)
        trader = best_trader()
        tax, broker = trader_fees(trader["character_id"], location) if trader else (7.5, 3.0)
        ship_ja, ship_en = type_name(ctx, ship["ship_type_id"])
        base = {"ship": {"type_id": ship["ship_type_id"], "ja": ship_ja, "en": ship_en, "name": ship.get("ship_name")},
                "trader": trader and {"character_id": trader["character_id"], "name": trader["character_name"]},
                "tax": tax, "broker": broker, "location": location}
        if not cargo:
            return jsonify({**base, "items": [], "list_total": 0, "instant_total": 0})
        try:
            prices = ctx.markets.prices(location, list(cargo))
        except Exception as e:  # noqa: BLE001 - 建造物の権限なしなど
            return error(tr("マーケットの価格を取得できませんでした: {0}", str(e).splitlines()[0]), 502)
        region = ctx.markets.station_region(location) if location < 1_000_000_000_000 else JITA_REGION_ID

        def volume(t):
            rows, _ = safe(live.public, f"/markets/{region}/history/", 3600, {"type_id": t})
            rows = (rows or [])[-7:]
            return t, sum(r["volume"] for r in rows) / 7 if rows else None
        with ThreadPoolExecutor(max_workers=8) as pool:
            volumes = dict(pool.map(volume, cargo))
        items = []
        for t, qty in cargo.items():
            p = prices.get(t) or {}
            sell = (p.get("sell") or {}).get("price")
            buy = (p.get("buy") or {}).get("price")
            # 出品価格: 最安の売り注文のすぐ下（価格は有効数字 4 桁まで）
            list_price = undercut(sell) if sell else None
            list_net = list_price * (1 - (tax + broker) / 100) * qty if list_price else None
            instant_net = buy * (1 - tax / 100) * qty if buy else None
            daily = volumes.get(t)
            ja, en = type_name(ctx, t)
            items.append({"type_id": t, "ja": ja, "en": en, "qty": qty, "sell": sell, "buy": buy, "list_price": list_price,
                          "list_net": list_net, "instant_net": instant_net, "daily_volume": daily,
                          "days_to_sell": qty / daily if daily else None,
                          "better": "list" if (list_net or 0) > (instant_net or 0) else "instant" if instant_net else None,
                          "sell_orders": (p.get("sell") or {}).get("orders", 0)})
        items.sort(key=lambda i: -max(i["list_net"] or 0, i["instant_net"] or 0))
        return jsonify({**base, "items": items, "list_total": sum(i["list_net"] or 0 for i in items),
                        "instant_total": sum(i["instant_net"] or 0 for i in items),
                        "best_total": sum(max(i["list_net"] or 0, i["instant_net"] or 0) for i in items)})

    def build_trade(char_id, min_price, min_margin):
        job = trade_job()
        try:
            first, headers = core._esi_request("GET", f"/markets/{JITA_REGION_ID}/orders/", params={"order_type": "all", "page": 1},
                                               with_headers=True)
            pages = int(headers.get("X-Pages", 1))
            orders = list(first)
            done = [1]

            def page(n):
                data = core._esi_request("GET", f"/markets/{JITA_REGION_ID}/orders/", params={"order_type": "all", "page": n})
                done[0] += 1
                job["progress"] = int(done[0] / pages * 80)
                return data
            with ThreadPoolExecutor(max_workers=12) as pool:
                for data in pool.map(page, range(2, pages + 1)):
                    orders += data
            best = {}
            for o in orders:
                if o["location_id"] != JITA_STATION_ID:
                    continue
                b = best.setdefault(o["type_id"], {"sell": None, "buy": None, "sell_orders": 0, "buy_orders": 0})
                if o["is_buy_order"]:
                    b["buy_orders"] += 1
                    b["buy"] = max(b["buy"] or 0, o["price"])
                else:
                    b["sell_orders"] += 1
                    b["sell"] = o["price"] if b["sell"] is None else min(b["sell"], o["price"])
            tax, broker = trader_fees(char_id)
            cands = []
            for t, b in best.items():
                if not b["sell"] or not b["buy"] or b["buy"] < min_price:
                    continue
                cost = b["buy"] * (1 + broker / 100)
                profit = b["sell"] * (1 - (tax + broker) / 100) - cost
                margin = profit / cost * 100
                if min_margin <= margin <= MAX_TRADE_MARGIN:  # 極端な差は、ありえない価格の注文（釣り）がほとんど
                    cands.append({"type_id": t, **b, "profit": profit, "margin": margin})
            # 取引量を調べる前の絞り込み: 注文の件数（売り・買いの少ない方）が多いほど売買が活発とみなす
            cands.sort(key=lambda c: -c["profit"] * min(c["buy_orders"], c["sell_orders"]))
            cands = cands[:400]
            total = len(cands)
            done = [0]

            def history(c):
                rows, _ = safe(live.public, f"/markets/{JITA_REGION_ID}/history/", 3600, {"type_id": c["type_id"]})
                rows = (rows or [])[-7:]
                done[0] += 1
                job["progress"] = 80 + int(done[0] / max(total, 1) * 19)
                c["volume"] = sum(r["volume"] for r in rows) / 7 if rows else 0
                c["average"] = sum(r["average"] * r["volume"] for r in rows) / max(sum(r["volume"] for r in rows), 1) if rows else None
                return c
            with ThreadPoolExecutor(max_workers=10) as pool:
                cands = list(pool.map(history, cands))
            for c in cands:
                c["ja"], c["en"] = type_name(ctx, c["type_id"])
                c["potential"] = c["profit"] * c["volume"] * 0.1  # 1 日の取引量の 1 割を取れた場合
            # 実際に取引されている価格（7 日の平均）が買値〜売値の近くにあり、ある程度売れているものだけ
            cands = [c for c in cands if c["volume"] >= MIN_TRADE_VOLUME and c["average"]
                     and c["buy"] * 0.7 <= c["average"] <= c["sell"] * 1.3]
            cands.sort(key=lambda c: -c["potential"])
            job.update(state="ready", progress=100, at=datetime.now(timezone.utc).isoformat(), error=None,
                              result={"items": cands[:150], "tax": tax, "broker": broker, "orders": len(orders),
                                      "types": len(best), "character_id": char_id})
        except Exception as e:  # noqa: BLE001 - 失敗は画面に出す
            job.update(state="error", error=str(e).splitlines()[0] if str(e) else repr(e))

    @app.post("/api/tools/station-trade")
    def api_station_trade_start():
        body = request.get_json(silent=True) or {}
        char_id = int(body.get("character_id") or 0)
        job = trade_job()
        with _trade_lock:
            if job["state"] == "running":
                return jsonify(job)
            fresh = job["state"] == "ready" and job["at"] and \
                datetime.now(timezone.utc) - datetime.fromisoformat(job["at"]) < timedelta(minutes=15)
            if fresh and job["result"]["character_id"] == char_id and job.get("params") == body:
                return jsonify(job)
            job.update(state="running", progress=0, error=None, params=body)
        # スレッドの中でも、どのアカウントのジョブかが分かるようにする
        threading.Thread(target=contextvars.copy_context().run,
                         args=(build_trade, char_id, float(body.get("min_price") or 1000),
                               float(body.get("min_margin") or 5)), daemon=True).start()
        return jsonify(job)

    @app.get("/api/tools/station-trade")
    def api_station_trade():
        return jsonify(trade_job())
