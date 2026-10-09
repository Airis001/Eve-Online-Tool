"""移動: ルートと危険度、ゲームの目的地の設定、ジャンプクローン、ジャンプ疲労。"""

from datetime import datetime, timedelta, timezone

import requests
from flask import jsonify, request

import autopilot
import routes
from accounts import ThreadPoolExecutor
from i18n import tr
from live import EsiForbidden, ScopeMissing, safe

from . import routing
from .common import error, int_arg, location_names, per_character, selected_characters, skill_levels, type_name
from .money import ui_post

ROUTE_FLAGS = {"shortest": "最短", "secure": "安全優先（ハイセク）", "insecure": "危険な星系を優先",
               "highsec": "ローセクを通らない最短"}
SKILL_INFOMORPH_SYNCHRONIZING = 33399  # クローンジャンプの待ち時間 -1 時間 / レベル
CLONE_JUMP_HOURS = 24


def register(app, ctx):
    core, live = ctx.core, ctx.live

    def resolve_system(value):
        value = (value or "").strip()
        if not value:
            return None
        if value.isdigit():
            return int(value)
        found = core.esi_post("/universe/ids/", [value]).get("systems", [])
        return found[0]["id"] if found else None

    def route_ship(char_id, ship_name):
        """見積もりに使う艦 (type_id, エラー)。名前の指定が無ければ、キャラクターが今乗っている艦。"""
        if ship_name:
            t = ctx.catalog.find_by_name(ship_name)
            return (t, None) if t else (None, tr("艦「{0}」が見つかりません", ship_name))
        if not char_id:
            return None, "艦を指定してください"
        try:
            ship = live.get(char_id, f"/characters/{char_id}/ship/", core.SCOPE_SHIP, ttl=30)
        except ScopeMissing:
            return None, "今乗っている艦を調べるには再ログインが必要です。艦の名前を入力してください"
        except (EsiForbidden, RuntimeError, requests.RequestException):
            return None, "今乗っている艦を取得できませんでした。艦の名前を入力してください"
        return ship["ship_type_id"], None

    def autopilot_time(route, char_id, ship_name, start_station, end_station):
        """オートパイロットで移動したときの時間の見積もり（失敗したら {"error"}）。"""
        ship_id, err = route_ship(char_id, ship_name)
        if err:
            return {"error": err}
        levels = skill_levels(ctx, char_id) if char_id else {}
        stats = autopilot.ship_stats(ctx.fitting_data, ship_id, levels)
        if not stats["velocity"]:
            return {"error": "艦ではないため計算できません"}
        try:
            if ctx.sde.gates:  # 静的データにゲートの位置があれば、それを使う（ESI に聞かなくてよい）
                gates = {sid: ctx.sde.gates.get(sid, {}) for sid in route}
            else:
                with ThreadPoolExecutor(max_workers=8) as pool:
                    gates = dict(zip(route, pool.map(ctx.universe.gates, route)))
            start = ctx.universe.station(start_station)["position"] if start_station else None
            end = ctx.universe.station(end_station)["position"] if end_station else None
        except (RuntimeError, requests.RequestException, KeyError) as e:
            return {"error": tr("ゲートの位置を取得できませんでした: {0}", str(e).splitlines()[0])}
        ja, en = type_name(ctx, ship_id)
        return {**autopilot.estimate(route, gates, stats, start, end), "ship": {"type_id": ship_id, "ja": ja, "en": en, **stats},
                "from_station": bool(start), "to_station": bool(end)}

    @app.get("/api/travel/route")
    def api_travel_route():
        from_station = int_arg("from_station")
        to_station = int_arg("to_station")
        try:
            origin = resolve_system(request.args.get("from"))
            dest = resolve_system(request.args.get("to"))
            # ステーションだけ指定したときは、その星系から・まで
            if not origin and from_station:
                origin = ctx.universe.station(from_station)["system_id"]
            if not dest and to_station:
                dest = ctx.universe.station(to_station)["system_id"]
        except (RuntimeError, requests.RequestException, KeyError) as e:
            return error(tr("星系を調べられませんでした: {0}", str(e).splitlines()[0]), 502)
        if not origin or not dest:
            return error("出発地と目的地の星系名を正しく入力してください（例: Jita、Amarr）")
        flag = request.args.get("flag", "secure")
        flag = flag if flag in ROUTE_FLAGS else "secure"
        avoid = []
        for name in filter(None, (s.strip() for s in request.args.get("avoid", "").split(","))):
            try:
                sid = resolve_system(name)
            except (RuntimeError, requests.RequestException):
                sid = None
            if sid:
                avoid.append(sid)
        min_sec = None
        max_low = 0
        if flag == "highsec":
            min_sec, max_low = routing.route_options(request.args)
            try:
                route = routing.safe_route(ctx, origin, dest, min_sec, avoid, max_low)
            except routing.NotReady as e:
                return error(tr("ルートの計算に使う静的データ（SDE）を準備しています（{0}%）。数分後にもう一度調べてください。", e), 503)
            except (RuntimeError, requests.RequestException) as e:
                return error(tr("ゲートが通れるかを確かめられませんでした: {0}", str(e).splitlines()[0]), 502)
            if not route:
                extra = tr("（セキュリティの足りない星系を {0} か所まで通っても）", max_low) if max_low else "（ローセクなどを通らないと着かない場所です）"
                return error(tr("セキュリティ {0:.1f} 以上の星系だけでは行けません{1}。", min_sec, extra), 404)
        else:
            params = {"flag": flag}
            if avoid:
                params["avoid"] = ",".join(map(str, avoid))
            try:
                route = live.public(f"/route/{origin}/{dest}/", ttl=600, params=params)
            except (RuntimeError, requests.RequestException):
                return error("ルートが見つかりません（ワームホール経由のみの場合や、避ける星系が多すぎる場合など）。", 404)
        kills, _ = safe(live.public, "/universe/system_kills/", 600)
        jumps, _ = safe(live.public, "/universe/system_jumps/", 600)
        kills = {k["system_id"]: k for k in kills or []}
        jumps = {j["system_id"]: j["ship_jumps"] for j in jumps or []}
        with ThreadPoolExecutor(max_workers=8) as pool:
            infos = list(pool.map(lambda s: safe(ctx.universe.system, s)[0], route))
        systems = []
        for sid, info in zip(route, infos):
            k = kills.get(sid, {})
            systems.append({"id": sid, "name": (info or {}).get("name", str(sid)),
                            "security": (info or {}).get("security_display"), "kind": (info or {}).get("kind"),
                            "label": (info or {}).get("label"), "region": (info or {}).get("region"),
                            "ship_kills": k.get("ship_kills", 0), "pod_kills": k.get("pod_kills", 0),
                            "npc_kills": k.get("npc_kills", 0), "jumps": jumps.get(sid, 0)})
        kinds = [s["kind"] for s in systems]
        if flag == "highsec":
            label = (tr("セキュリティ {0:.1f} 以上の最短", min_sec) + (tr("（足りない星系は {0} か所まで）", max_low) if max_low else "")
                     if min_sec > 0.5 else tr("ローセクを {0} か所まで通る最短", max_low) if max_low else ROUTE_FLAGS[flag])
        else:
            label = ROUTE_FLAGS[flag]
        result = {"flag": flag, "flag_label": label, "min_sec": min_sec, "max_low": max_low, "systems": systems, "jumps": len(systems) - 1,
                  "lowsec": kinds.count("lowsec"), "nullsec": kinds.count("nullsec") + kinds.count("pochven"),
                  "ship_kills": sum(s["ship_kills"] for s in systems), "avoided": len(avoid)}
        if flag == "highsec":  # くらべる: ゲームの「安全優先」のジャンプ数
            secure, _ = safe(live.public, f"/route/{origin}/{dest}/", 600, {"flag": "secure"})
            result["secure_jumps"] = len(secure) - 1 if secure else None
        if request.args.get("autopilot") == "1":
            start = from_station if from_station and ctx.universe.station(from_station)["system_id"] == origin else None
            end = to_station if to_station and ctx.universe.station(to_station)["system_id"] == dest else None
            result["autopilot"] = autopilot_time(route, int_arg("character_id"), request.args.get("ship", "").strip(), start, end)
        return jsonify(result)

    @app.post("/api/ui/waypoint")
    def api_ui_waypoint():
        body = request.get_json(silent=True) or {}
        try:
            dest = int(body.get("destination_id"))
        except (TypeError, ValueError):
            return error("destination_id が必要です")
        return ui_post(ctx, body.get("character_id"), core.SCOPE_WAYPOINT, "/ui/autopilot/waypoint/", {
            "destination_id": dest, "clear_other_waypoints": str(bool(body.get("clear", True))).lower(),
            "add_to_beginning": str(bool(body.get("beginning", False))).lower(),
        })

    @app.post("/api/ui/route")
    def api_ui_route():
        """ルート（星系の並び）どおりにゲームのオートパイロットが進むよう、必要なところだけ経由地を入れる。

        ゲームのルートの設定は「安全優先」とみなし、ESI の安全優先のルートと分かれるところを経由地にする。
        """
        body = request.get_json(silent=True) or {}
        route = body.get("systems") or []
        if not (isinstance(route, list) and 2 <= len(route) <= 300 and all(isinstance(s, int) for s in route)):
            return error("systems が不正です")

        def game_route(a, b):
            return live.public(f"/route/{a}/{b}/", ttl=600, params={"flag": "secure"})
        try:
            points = routes.waypoints_for(route, game_route)
        except (RuntimeError, requests.RequestException) as e:
            return error(tr("ルートを調べられませんでした: {0}", str(e).splitlines()[0]), 502)
        for i, sid in enumerate(points):
            res = ui_post(ctx, body.get("character_id"), core.SCOPE_WAYPOINT, "/ui/autopilot/waypoint/", {
                "destination_id": sid, "clear_other_waypoints": str(i == 0).lower(), "add_to_beginning": "false"})
            if isinstance(res, tuple):  # エラー（応答, ステータス）
                return res
        names = [(safe(ctx.universe.system, sid)[0] or {}).get("name", str(sid)) for sid in points]
        return jsonify({"ok": True, "waypoints": names})

    @app.get("/api/travel/clones")
    def api_travel_clones():
        def load(cid, name):
            clones = live.get(cid, f"/characters/{cid}/clones/", core.SCOPE_CLONES, ttl=120)
            fatigue, ferr = safe(live.get, cid, f"/characters/{cid}/fatigue/", core.SCOPE_FATIGUE, ttl=300)
            return {"clones": clones, "fatigue": fatigue, "fatigue_error": ferr}

        rows = per_character(selected_characters(ctx), load)
        now = datetime.now(timezone.utc)
        for r in rows:
            data = r.get("data")
            if not data:
                continue
            clones = data["clones"]
            ids = {j["location_id"] for j in clones.get("jump_clones", [])}
            home = clones.get("home_location") or {}
            if home.get("location_id"):
                ids.add(home["location_id"])
            names = location_names(ctx, ids, r["character_id"])
            levels = skill_levels(ctx, r["character_id"])
            cooldown = CLONE_JUMP_HOURS - levels.get(SKILL_INFOMORPH_SYNCHRONIZING, 0)
            last = clones.get("last_clone_jump_date")
            ready_at = None
            if last:
                ready = datetime.fromisoformat(last.replace("Z", "+00:00")) + timedelta(hours=cooldown)
                ready_at = ready.isoformat() if ready > now else None
            r["home"] = {"location_id": home.get("location_id"), "name": names.get(home.get("location_id"))}
            r["jump_clones"] = [{"id": j["jump_clone_id"], "name": j.get("name"), "location_id": j["location_id"],
                                 "location": names.get(j["location_id"]),
                                 "implants": [type_name(ctx, t)[0] for t in j.get("implants", [])]}
                                for j in clones.get("jump_clones", [])]
            r["last_clone_jump"] = last
            r["clone_ready_at"] = ready_at
            r["cooldown_hours"] = cooldown
            f = data.get("fatigue") or {}
            expire = f.get("jump_fatigue_expire_date")
            r["fatigue_expire"] = expire if expire and datetime.fromisoformat(expire.replace("Z", "+00:00")) > now else None
            r["last_jump"] = f.get("last_jump_date")
            r["fatigue_needs_scope"] = (data.get("fatigue_error") or {}).get("needs_scope")
            del r["data"]
        return jsonify({"characters": rows})
