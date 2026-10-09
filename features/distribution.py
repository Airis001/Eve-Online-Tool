"""流通ミッション: 近くの流通エージェントを探し、受注と配達の回り方（一筆書き）を求める。

1. 基準の星系から N ジャンプ以内にいる流通（Distribution）部門のエージェント（SDE）
2. エージェントの星系をすべて回る順番（確認用）
3. 受注すると決めたエージェントだけを回る順番
4. 最後に受注した星系から、受取場所と配達先をすべて回る順番（どの荷物も受取場所 → 配達先の順。routes.pdp_tour）
   ミッションは「受注場所（エージェント）」「受取場所」「配達先」を別々に持つ。受取場所 = 受注場所なら、受注のときに積み込み済み。
回る順番は routes.open_tour（最近傍法 + 2-opt）、ジャンプ数は SDE のゲートのつながり（routing と同じ通り方の決まり）。
"""

import requests
from flask import jsonify, request

import routes
from accounts import ThreadPoolExecutor
from i18n import tr
from live import safe
from wormhole import display_security

from . import routing
from .common import error

DISTRIBUTION = 22  # SDE の部門: 流通
MAX_JUMPS = 6
MAX_STOPS = 60     # 一度に回る星系の数の上限


def register(app, ctx):
    sde = ctx.sde

    def ready():
        """エージェントとゲートのデータが無ければ作り始めて、エラーの応答を返す。"""
        if sde.agents and sde.gates:
            return None
        if sde.status["state"] != "building":
            sde.build_async()
        return error(tr("エージェントとルートのデータ（SDE）を準備しています（{0}%）。数分後にもう一度試してください。", (sde.status.get('progress', 0))), 503)

    def find_system(value):
        """星系名（英語・日本語、大文字小文字は区別しない）か ID → 星系 ID。"""
        value = (value or "").strip()
        if value.isdigit():
            return int(value) if int(value) in sde.systems else None
        low = value.lower()
        for sid, (en, ja, *_rest) in sde.systems.items():
            if (en or "").lower() == low or ja == value:
                return sid
        return None

    def system_info(sid):
        en, ja, sec = sde.systems.get(sid, [str(sid), None, 0])[:3]
        shown = display_security(sec)
        kind = "highsec" if shown >= 0.5 else "lowsec" if shown > 0 else "nullsec"
        return {"id": sid, "name": en, "ja": ja, "security": shown, "kind": kind}

    def corp_name(cid):
        en, ja = sde.corp_names.get(cid, [str(cid), None])
        return ja or en

    @app.get("/api/dist/systems")
    def api_dist_systems():
        """星系名の候補（配達先の入力用）: [[ID, 英語名, 日本語名, セキュリティ]]。ワームホールなどは除く。"""
        if (problem := ready()):
            return problem
        rows = [[sid, v[0], v[1], display_security(v[2])] for sid, v in sde.systems.items()
                if sid < 31000000 and sid in sde.gates]
        return jsonify({"systems": rows})

    @app.get("/api/dist/agents")
    def api_dist_agents():
        if (problem := ready()):
            return problem
        base = find_system(request.args.get("system"))
        if not base:
            return error("基準の星系が見つかりません（例: Jita）")
        try:
            jumps = max(0, min(int(request.args.get("jumps", 2)), MAX_JUMPS))
        except ValueError:
            jumps = 2
        levels = {int(x) for x in request.args.get("levels", "1,2,3,4").split(",") if x.strip().isdigit()}
        min_sec, max_low = routing.route_options(request.args)
        near = routes.distances(sde.gates, sde.systems, base, min_sec, routing.known_blocked(), max_low, limit=jumps)
        stations = {}
        for aid, (en, ja, division, level, station, corp, locator) in sde.agents.items():
            system = sde.stations.get(station)
            if division != DISTRIBUTION or system not in near or level not in levels:
                continue
            st = stations.setdefault(station, {"station_id": station, "system": system_info(system), "jumps": near[system],
                                               "agents": []})
            st["agents"].append({"id": aid, "name": ja or en, "en": en, "level": level, "corp": corp_name(corp),
                                 "locator": locator})

        def name(st):
            info, _ = safe(ctx.universe.station, st["station_id"])
            st["name"] = (info or {}).get("name") or f"#{st['station_id']}"
            return st
        with ThreadPoolExecutor(max_workers=8) as pool:
            result = list(pool.map(name, stations.values()))
        for st in result:
            st["agents"].sort(key=lambda a: (-a["level"], a["name"]))
        result.sort(key=lambda st: (st["jumps"], st["system"]["name"], st["name"]))
        return jsonify({"base": system_info(base), "jumps": jumps, "stations": result,
                        "agents": sum(len(st["agents"]) for st in result)})

    @app.post("/api/dist/tour")
    def api_dist_tour():
        """start から systems をすべて回る順番と、つなげたルート（ゲームに設定できる星系の並び）。"""
        if (problem := ready()):
            return problem
        body = request.get_json(silent=True) or {}
        start = body.get("start")
        points = body.get("systems") or []
        if not isinstance(start, int) or start not in sde.systems:
            return error("出発の星系が不正です")
        if not (isinstance(points, list) and len(points) <= MAX_STOPS and all(isinstance(p, int) for p in points)):
            return error(tr("回る星系は {0} か所までです", MAX_STOPS))
        min_sec, max_low = routing.route_options(body)
        blocked = routing.known_blocked()
        cache = {}

        def dist(a, b):
            if a not in cache:
                cache[a] = routes.distances(sde.gates, sde.systems, a, min_sec, blocked, max_low)
            return cache[a].get(b)
        order, _, unreachable = routes.open_tour(start, points, dist)
        # 区間ごとに実際のルートを求める（通れないゲートは避け直すので、見積もりより長くなることがある）
        legs, full = [], [start]
        here = start
        try:
            for stop in order:
                path = routing.safe_route(ctx, here, stop, min_sec, (), max_low)
                if not path:
                    unreachable.append(stop)
                    continue
                legs.append({**system_info(stop), "jumps": len(path) - 1})
                full += path[1:]
                here = stop
        except (RuntimeError, requests.RequestException) as e:
            return error(tr("ゲートが通れるかを確かめられませんでした: {0}", str(e).splitlines()[0]), 502)
        systems = [system_info(s) for s in full]
        kinds = [s["kind"] for s in systems]
        return jsonify({"start": system_info(start), "stops": legs, "jumps": len(full) - 1, "systems": systems,
                        "unreachable": [system_info(s) for s in unreachable], "flag": "highsec",
                        "lowsec": kinds.count("lowsec"), "nullsec": kinds.count("nullsec"), "end": full[-1]})

    def action_of(missions, volumes, kind, i, at):
        """地点で行う受取・配達。at = 出発から何ジャンプ目か。"""
        return {"type": "pickup" if kind == "P" else "dropoff", "index": i, "at": at,
                "label": str(missions[i].get("label") or f"#{i + 1}"), "volume": volumes[i],
                "urgent": bool(missions[i].get("urgent"))}

    @app.post("/api/dist/deliver")
    def api_dist_deliver():
        """受取と配達の一筆書き。missions: [{label, pickup: 受取の星系 ID or null（積み込み済み）, dropoff: 配達先の星系 ID,
        volume: 荷物の体積 m³, urgent: 緊急か}]、capacity: カーゴの容量 m³（0 = 考えない）。
        start は「最後に受注した星系」でも「今いる星系」（途中で割り込みを入れて計算し直すとき）でもよい。

        どの荷物も受取場所を通ってから、その配達先を通る（Pickup and Delivery）。どの時点でも積んでいる合計が容量を
        超えない（一度に積めなければ、途中で配達して空けてから次を受け取りに行く）。緊急の荷物は、合計ジャンプ数が少し増えても
        早く受け取り・届ける順番にする。同じ星系での受取・配達は 1 か所にまとめる。
        各地点の actions の index は missions の番号（画面で「済んだ」を付けるのに使う）。
        """
        if (problem := ready()):
            return problem
        body = request.get_json(silent=True) or {}
        start = body.get("start")
        missions = body.get("missions") or []
        if not isinstance(start, int) or start not in sde.systems:
            return error("出発の星系が不正です")
        ok = isinstance(missions, list) and 0 < len(missions) <= MAX_STOPS and all(
            isinstance(m, dict) and isinstance(m.get("dropoff"), int) and m["dropoff"] in sde.systems
            and (m.get("pickup") is None or (isinstance(m["pickup"], int) and m["pickup"] in sde.systems)) for m in missions)
        if not ok:
            return error(tr("ミッションの受取場所・配達先が不正です（{0} 件まで）", MAX_STOPS))
        min_sec, max_low = routing.route_options(body)
        try:
            capacity = max(float(body.get("capacity") or 0), 0)
            volumes = [max(float(m.get("volume") or 0), 0) for m in missions]
        except (TypeError, ValueError):
            return error("カーゴの容量・荷物の体積は数字で入れてください")
        blocked = routing.known_blocked()
        cache = {}

        def dist(a, b):
            if a == b:
                return 0
            if a not in cache:
                cache[a] = routes.distances(sde.gates, sde.systems, a, min_sec, blocked, max_low)
            return cache[a].get(b)
        try:
            seq, _, unreachable = routes.pdp_tour(start, [(m.get("pickup"), m["dropoff"]) for m in missions], dist,
                                                  volumes, capacity or None, [bool(m.get("urgent")) for m in missions])
        except routes.OverCapacity as e:
            return error(tr("積み込み済みの荷物（{0:,.0f} m³）だけで、カーゴの容量（{1:,.0f} m³）を超えています。", float(str(e)), capacity))
        too_big = [i for i in unreachable if capacity and volumes[i] > capacity]
        load = sum(volumes[i] for i, m in enumerate(missions) if m.get("pickup") is None and i not in unreachable)
        initial_load = load
        # 同じ星系が続くところは 1 か所にまとめ、区間ごとに実際のルートを求める
        stops, full, here = [], [start], start
        try:
            for kind, i, system in seq:
                if stops and stops[-1]["id"] == system:
                    load += volumes[i] if kind == "P" else -volumes[i]
                    stops[-1]["actions"].append(action_of(missions, volumes, kind, i, len(full) - 1))
                    stops[-1]["load"] = load
                    continue
                path = [here] if system == here else routing.safe_route(ctx, here, system, min_sec, (), max_low)
                if not path:
                    unreachable.append(i)
                    continue
                load += volumes[i] if kind == "P" else -volumes[i]
                stops.append({**system_info(system), "jumps": len(path) - 1, "load": load,
                              "actions": [action_of(missions, volumes, kind, i, len(full) - 1 + len(path) - 1)]})
                full += path[1:]
                here = system
        except (RuntimeError, requests.RequestException) as e:
            return error(tr("ゲートが通れるかを確かめられませんでした: {0}", str(e).splitlines()[0]), 502)
        systems = [system_info(s) for s in full]
        kinds = [s["kind"] for s in systems]
        urgent_done = [a["at"] for st in stops for a in st["actions"] if a["urgent"] and a["type"] == "dropoff"]
        return jsonify({"start": system_info(start), "stops": stops, "jumps": len(full) - 1, "systems": systems,
                        "urgent_done_at": max(urgent_done) if urgent_done else None,
                        "unreachable": [str(missions[i].get("label") or f"#{i + 1}") for i in dict.fromkeys(unreachable) if i not in too_big],
                        "too_big": [str(missions[i].get("label") or f"#{i + 1}") for i in too_big],
                        "capacity": capacity, "initial_load": initial_load,
                        "max_load": max([initial_load] + [st["load"] for st in stops]),
                        "flag": "highsec", "lowsec": kinds.count("lowsec"), "nullsec": kinds.count("nullsec"), "end": full[-1]})
