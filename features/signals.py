"""シグネチャ・星系の様子:
  1. 自分たちのスキャン結果の記録（星系ごとのシグネチャの数・種類・増減）
  2. Thera・Turnur の繋がり（EVE-Scout の公開データ）と、出発地からのジャンプ数
  3. 星系の活動（ESI: 直近 1 時間の NPC・艦・ポッドの撃墜数とジャンプ数）、インカージョン
"""

import json
import threading
from datetime import datetime, timedelta, timezone

import requests
from flask import jsonify, request

import accounts
import wormhole
from accounts import ThreadPoolExecutor
from i18n import tr
from live import safe

from .common import error, int_arg

MAX_SNAPSHOTS = 5000
EVE_SCOUT_URL = "https://api.eve-scout.com/v2/public/signatures"
KINDS = ["wormhole", "data", "relic", "gas", "ore", "combat", "anomaly", "unknown"]
SHIP_SIZE = {"small": "フリゲート・駆逐艦まで", "medium": "巡洋艦・巡洋戦艦まで", "large": "戦艦まで",
             "xlarge": "フレイター・キャピタル（一部）まで", "capital": "キャピタルまで"}
INCURSION_STATE = {"established": "開始", "mobilizing": "動員中", "withdrawing": "撤退中"}
_lock = threading.Lock()
_scout_cache = {"at": None, "data": None}


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log_file():
    return accounts.user_file("sig_log.json")


def load_log():
    try:
        return json.loads(log_file().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"snapshots": []}


def register(app, ctx):
    live, sde = ctx.live, ctx.sde
    by_name = {}

    def system_id_of(value):
        """星系名（英語・日本語、大文字小文字は問わない）または ID → 星系 ID。"""
        value = str(value or "").strip()
        if value.isdigit():
            return int(value)
        if sde.ready and not by_name:
            for sid, v in sde.systems.items():
                by_name[(v[0] or "").lower()] = sid
                if v[1]:
                    by_name[v[1]] = sid
        return by_name.get(value.lower()) or by_name.get(value)

    def system_view(sid):
        """星系の名前・種類（クラス / セキュリティ）・地域（静的データから。無ければ ESI）。"""
        v = sde.systems.get(sid) if sde.ready else None
        if not v:
            info, _ = safe(ctx.universe.system, sid)
            return info or {"id": sid, "name": str(sid)}
        name, name_ja, sec, region_id, _ = v
        region = sde.regions.get(region_id, [str(region_id), None, None])
        cls = wormhole.system_class(sid, name, region_id, region[0], sec)
        return {"id": sid, "name": name, "name_ja": name_ja, "security": sec,
                "security_display": wormhole.display_security(sec), "region_id": region_id, "region": region[0],
                "region_ja": region[1], **cls}

    # ---------- 1. スキャンの記録 ----------

    @app.post("/api/sigs/record")
    def api_sigs_record():
        body = request.get_json(silent=True) or {}
        sid = system_id_of(body.get("system"))
        if not sid:
            return error(tr("「{0}」という星系が見つかりません。星系名を入力してください。", body.get('system') or ''))
        sigs = [{"id": str(s.get("id", ""))[:7], "kind": s.get("kind") if s.get("kind") in KINDS else "unknown",
                 "name": str(s.get("name") or "")[:100], "signal": str(s.get("signal") or "")[:10]}
                for s in body.get("sigs", []) if s.get("id")]
        if not sigs:
            return error("シグネチャがありません")
        counts = {k: 0 for k in KINDS}
        for s in sigs:
            counts[s["kind"]] += 1
        snap = {"system_id": sid, "at": now_iso(), "by": str(body.get("character_name") or "")[:50],
                "counts": counts, "total": len(sigs), "sigs": sigs}
        with _lock:
            log = load_log()
            prev = next((x for x in reversed(log["snapshots"]) if x["system_id"] == sid), None)
            log["snapshots"].append(snap)
            log["snapshots"] = log["snapshots"][-MAX_SNAPSHOTS:]
            log_file().write_text(json.dumps(log, ensure_ascii=False), encoding="utf-8")
        return jsonify({"system": system_view(sid), "snapshot": snap, "previous": prev})

    @app.get("/api/sigs/systems")
    def api_sigs_systems():
        """記録した星系ごとの最新のシグネチャの数（前回からの増減付き）。"""
        days = int_arg("days", 30, 1, 365)
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        latest, previous, counts = {}, {}, {}
        for snap in load_log()["snapshots"]:
            sid = snap["system_id"]
            counts[sid] = counts.get(sid, 0) + 1
            if sid in latest:
                previous[sid] = latest[sid]
            latest[sid] = snap
        rows = []
        for sid, snap in latest.items():
            if snap["at"] < since:
                continue
            prev = previous.get(sid)
            rows.append({"system": system_view(sid), "at": snap["at"], "by": snap["by"], "counts": snap["counts"],
                         "total": snap["total"], "scans": counts[sid],
                         "diff": snap["total"] - prev["total"] if prev else None,
                         "sigs": snap["sigs"]})
        rows.sort(key=lambda r: r["at"], reverse=True)
        return jsonify({"systems": rows, "kinds": KINDS})

    @app.get("/api/sigs/history")
    def api_sigs_history():
        sid = int_arg("system_id")
        snaps = [s for s in load_log()["snapshots"] if s["system_id"] == sid][-50:]
        return jsonify({"system": system_view(sid) if sid else None,
                        "history": [{k: s[k] for k in ("at", "by", "counts", "total")} for s in reversed(snaps)]})

    @app.delete("/api/sigs/system/<int:sid>")
    def api_sigs_delete(sid):
        with _lock:
            log = load_log()
            log["snapshots"] = [s for s in log["snapshots"] if s["system_id"] != sid]
            log_file().write_text(json.dumps(log, ensure_ascii=False), encoding="utf-8")
        return jsonify({"ok": True})

    # ---------- 2. Thera・Turnur（EVE-Scout） ----------

    def scout_data():
        now = datetime.now(timezone.utc)
        if _scout_cache["data"] is not None and now - _scout_cache["at"] < timedelta(minutes=5):
            return _scout_cache["data"]
        res = requests.get(EVE_SCOUT_URL, timeout=20)
        res.raise_for_status()
        _scout_cache.update(at=now, data=res.json())
        return _scout_cache["data"]

    @app.get("/api/sigs/scout")
    def api_sigs_scout():
        try:
            data = scout_data()
        except (requests.RequestException, ValueError) as e:
            return error(tr("EVE-Scout のデータを取得できませんでした: {0}", e), 502)
        origin = system_id_of(request.args.get("from", ""))
        rows = []
        for d in data:
            if d.get("signature_type") != "wormhole" or not d.get("in_system_id"):
                continue
            dest = system_view(d["in_system_id"])
            rows.append({"hub": d.get("out_system_name"), "hub_signature": d.get("out_signature"),
                         "signature": d.get("in_signature"), "destination": dest, "wh_type": d.get("wh_type"),
                         "size": d.get("max_ship_size"), "size_label": SHIP_SIZE.get(d.get("max_ship_size"), d.get("max_ship_size")),
                         "expires_at": d.get("expires_at"), "remaining_hours": d.get("remaining_hours"),
                         "updated_at": d.get("updated_at"), "jumps": None})

        # 出発地から出口の星系（K 空間）までのジャンプ数
        if origin:
            def jumps(dest_id):
                if dest_id >= wormhole.WORMHOLE_SYSTEM_MIN:
                    return dest_id, None
                route, _ = safe(live.public, f"/route/{origin}/{dest_id}/", 1800, {"flag": "shortest"})
                return dest_id, (len(route) - 1) if route else None
            with ThreadPoolExecutor(max_workers=8) as pool:
                found = dict(pool.map(jumps, {r["destination"]["id"] for r in rows}))
            for r in rows:
                r["jumps"] = found.get(r["destination"]["id"])
        rows.sort(key=lambda r: (r["jumps"] is None, r["jumps"] or 0, r["hub"] or ""))
        return jsonify({"connections": rows, "origin": system_view(origin) if origin else None,
                        "source": "EVE-Scout（https://www.eve-scout.com/）"})

    # ---------- 3. 星系の活動・インカージョン ----------

    @app.get("/api/sigs/activity")
    def api_sigs_activity():
        if not sde.ready:
            sde.build_async()
            return error("静的データ（SDE）を準備しています。しばらくしてから開き直してください。", 503)
        kills, _ = safe(live.public, "/universe/system_kills/", 600)
        jumps, _ = safe(live.public, "/universe/system_jumps/", 600)
        kills = {k["system_id"]: k for k in kills or []}
        jumps = {j["system_id"]: j["ship_jumps"] for j in jumps or []}
        region = int_arg("region")
        sec = request.args.get("sec", "all")
        sort = request.args.get("sort", "npc")
        limit = int_arg("limit", 50, 10, 300)
        rows = []
        for sid, v in sde.systems.items():
            if sid >= 32_000_000 or (region and v[3] != region):
                continue
            view = system_view(sid)
            kind = view.get("kind")
            if sec != "all" and not (sec == kind or (sec == "null" and kind in ("nullsec", "pochven"))
                                     or (sec == "high" and kind == "highsec") or (sec == "low" and kind == "lowsec")
                                     or (sec == "wh" and kind == "wormhole")):
                continue
            k = kills.get(sid, {})
            rows.append({"system": view, "npc_kills": k.get("npc_kills", 0), "ship_kills": k.get("ship_kills", 0),
                         # ESI は 0 の星系を返さないので、K 空間は 0 とみなす（J 空間はジャンプ数そのものが無い）
                         "pod_kills": k.get("pod_kills", 0),
                         "jumps": jumps.get(sid, 0) if sid < wormhole.WORMHOLE_SYSTEM_MIN else None})
        keys = {
            "npc": lambda r: -r["npc_kills"],
            "ship": lambda r: -r["ship_kills"],
            "jumps_desc": lambda r: -(r["jumps"] or 0),
            "quiet": lambda r: (r["ship_kills"] + r["pod_kills"], r["jumps"] if r["jumps"] is not None else 10**9, -r["npc_kills"]),
        }
        rows.sort(key=keys.get(sort, keys["npc"]))
        regions = sorted(({"id": rid, "name": v[0], "name_ja": v[1]} for rid, v in sde.regions.items()
                          if rid < 11_000_000 or 11_000_000 <= rid < 11_000_034), key=lambda r: r["name"])
        return jsonify({"systems": rows[:limit], "total": len(rows), "regions": regions,
                        "note": "撃墜数・ジャンプ数は ESI の直近 1 時間の集計（約 1 時間ごとに更新）"})

    @app.get("/api/sigs/incursions")
    def api_sigs_incursions():
        data, err = safe(live.public, "/incursions/", 600)
        if data is None:
            return error("インカージョンの情報を取得できませんでした", 502)
        rows = []
        for inc in data:
            constellation, _ = safe(live.public, f"/universe/constellations/{inc['constellation_id']}/", 86400)
            staging = system_view(inc["staging_solar_system_id"])
            rows.append({"constellation": (constellation or {}).get("name"), "staging": staging,
                         "systems": [system_view(s) for s in inc.get("infested_solar_systems", [])],
                         "state": INCURSION_STATE.get(inc.get("state"), inc.get("state")), "influence": inc.get("influence"),
                         "has_boss": inc.get("has_boss")})
        return jsonify({"incursions": rows})
