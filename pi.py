"""PI（惑星開発）の生産の集計と、余り・不足をなくすための提案。

考え方:
  - 選んだキャラクター全員のコロニーを 1 つの工場群とみなす（キャラクター間で運べる前提）。
  - 抽出機: 1 日あたりの抽出量（ESI の qty_per_cycle ÷ cycle_time）。実際は抽出が進むと少しずつ減る。
  - 工場: 材料が足りていれば 1 日に作れる量（レシピの出力 ÷ サイクル時間）。材料が足りなければ比例して落ちる。
  - 材料は、それを使う工場に必要量の割合で配る（使い切れなかった分は他の工場へ回す）。
  - 不足している材料を増やすのに必要な「抽出する惑星の数」「工場の数」を、余っている材料を先に使う前提で逆算する。
"""

import math
from datetime import datetime, timezone

DAY = 86400
SKILL_INTERPLANETARY_CONSOLIDATION = 2495  # コロニーの数 = 1 + レベル
DEFAULT_P0_PER_PLANET = 100_000            # 抽出惑星 1 つの 1 日の抽出量（自分のデータが無いときの目安）


def parse_time(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def colony_view(sde, planet, detail, now=None):
    """1 惑星分のコロニー: 抽出機・工場の一覧と、1 日の抽出量・生産能力。"""
    now = now or datetime.now(timezone.utc)
    extractors, factories = [], {}
    for pin in detail.get("pins", []):
        ex = pin.get("extractor_details")
        if ex and ex.get("product_type_id"):
            cycle = ex.get("cycle_time") or 0
            expiry = parse_time(pin.get("expiry_time"))
            per_day = ex.get("qty_per_cycle", 0) * DAY / cycle if cycle else 0
            extractors.append({
                "type_id": ex["product_type_id"], "per_day": per_day, "heads": len(ex.get("heads", [])),
                "expiry": pin.get("expiry_time"), "active": bool(expiry and expiry > now),
                "hours_left": (expiry - now).total_seconds() / 3600 if expiry else None,
                # 配置の記録用
                "pin_id": pin.get("pin_id"), "install_time": pin.get("install_time"),
                "ecu": [pin.get("latitude"), pin.get("longitude")], "head_radius": ex.get("head_radius"),
                "head_positions": [[h.get("latitude"), h.get("longitude")] for h in ex.get("heads", [])],
                "cycle_time": cycle, "qty_per_cycle": ex.get("qty_per_cycle", 0),
            })
            continue
        schematic = pin.get("schematic_id") or (pin.get("factory_details") or {}).get("schematic_id")
        if schematic and schematic in sde.schematics:
            factories[schematic] = factories.get(schematic, 0) + 1
    return {"planet_id": planet["planet_id"], "planet_type": planet.get("planet_type"),
            "solar_system_id": planet.get("solar_system_id"), "upgrade_level": planet.get("upgrade_level"),
            "num_pins": planet.get("num_pins"), "last_update": planet.get("last_update"),
            "extractors": extractors, "factories": factories}


def schematic_rates(sde, schematic_id):
    """工場 1 台の 1 日あたり: (出力の type_id, 出力量, {入力の type_id: 消費量})"""
    s = sde.schematics[schematic_id]
    runs = DAY / s["cycle"]
    return s["output"][0], s["output"][1] * runs, {t: q * runs for t, q in s["inputs"]}


def simulate(sde, colonies):
    """全コロニーをまとめたときの、品目ごとの 1 日の生産・消費。

    返り値: {type_id: {"supply", "used", "demand", "tier"}}, {schematic_id: {"count", "utilization", "capacity", "output"}}
    supply: 抽出・生産される量、demand: 工場が満稼働したときの必要量、used: 実際に使われる量。
    """
    extraction = {}
    groups = {}
    for c in colonies:
        for ex in c["extractors"]:
            extraction[ex["type_id"]] = extraction.get(ex["type_id"], 0) + ex["per_day"]
        for sid, n in c["factories"].items():
            groups[sid] = groups.get(sid, 0) + n

    rates = {sid: schematic_rates(sde, sid) for sid in groups}
    demand = {}
    for sid, n in groups.items():
        for t, q in rates[sid][2].items():
            demand[t] = demand.get(t, 0) + q * n

    tier = lambda t: sde.pi_tiers.get(t, 0)  # noqa: E731
    supply = dict(extraction)
    util = {sid: None for sid in groups}  # 稼働率（未定は None）
    # 出力の段階が低い工場から順に決める（材料の生産量が先に決まる）。材料の配分: 同じ材料を使う工場の間で、必要量の割合で配る。使い切れない分は他へ回す（数回繰り返す）
    for _ in range(3):
        supply = dict(extraction)
        for sid in sorted(groups, key=lambda s: tier(rates[s][0])):
            out, cap, inputs = rates[sid]
            n = groups[sid]
            ratio = 1.0
            for t, q in inputs.items():
                share = supply_share(t, sid, supply, groups, rates, util)
                ratio = min(ratio, share / (q * n) if q * n else 1.0)
            util[sid] = max(0.0, min(1.0, ratio))
            supply[out] = supply.get(out, 0) + cap * n * util[sid]

    used = {}
    for sid, n in groups.items():
        for t, q in rates[sid][2].items():
            used[t] = used.get(t, 0) + q * n * util[sid]
    items = {}
    for t in set(supply) | set(demand):
        items[t] = {"supply": supply.get(t, 0), "demand": demand.get(t, 0), "used": min(used.get(t, 0), supply.get(t, 0)),
                    "tier": tier(t)}
    factories = {sid: {"count": n, "utilization": util[sid], "capacity": rates[sid][1] * n,
                       "output": rates[sid][1] * n * util[sid], "type_id": rates[sid][0]} for sid, n in groups.items()}
    return items, factories


def supply_share(type_id, sid, supply, groups, rates, util):
    """材料 type_id のうち、工場 sid（全台）に回せる量。

    他の工場の必要量は、すでに稼働率が決まっていればその分だけ、未定なら満稼働分として割合で配る。
    """
    available = supply.get(type_id, 0)
    mine = rates[sid][2][type_id] * groups[sid]
    others = 0.0
    for other, n in groups.items():
        if other == sid or type_id not in rates[other][2]:
            continue
        u = util.get(other)
        others += rates[other][2][type_id] * n * (1.0 if u is None else u)
    total = mine + others
    return available if total <= 0 else available * mine / total if available < total else mine


def p0_per_planet(colonies):
    """自分のデータから、抽出惑星 1 つの 1 日の抽出量の目安（抽出機のある惑星の平均）。"""
    rates = [sum(ex["per_day"] for ex in c["extractors"]) for c in colonies if c["extractors"]]
    return sum(rates) / len(rates) if rates else DEFAULT_P0_PER_PLANET


def producer_schematic(sde, type_id):
    for sid, s in sde.schematics.items():
        if s["output"][0] == type_id:
            return sid
    return None


def new_plan():
    return {"factories": {}, "idle": {}, "extract": {}, "use_surplus": {}}


def plan_increase(sde, type_id, amount, surplus, spare, plan=None, depth=0):
    """type_id を 1 日 amount 増やすのに必要な、追加の工場・抽出（余っている材料・空いている工場を先に使う）。

    surplus: {type_id: 余っている量}、spare: {schematic_id: 既存の工場の空き（1 日に作れる量）}（どちらも使った分を減らす）
    plan: {"factories": {schematic_id: 新しい工場の台数(小数)}, "idle": {schematic_id: 既存の工場で増やす量},
           "extract": {P0 type_id: 1 日の量}, "use_surplus": {type_id: 量}}
    """
    plan = plan if plan is not None else new_plan()
    if amount <= 0 or depth > 6:
        return plan
    extra = surplus.get(type_id, 0)
    if extra > 0:
        use = min(extra, amount)
        surplus[type_id] = extra - use
        plan["use_surplus"][type_id] = plan["use_surplus"].get(type_id, 0) + use
        amount -= use
    if amount <= 0:
        return plan
    sid = producer_schematic(sde, type_id)
    if sid is None:  # P0: 抽出を増やす
        plan["extract"][type_id] = plan["extract"].get(type_id, 0) + amount
        return plan
    out, cap, inputs = schematic_rates(sde, sid)
    idle = min(spare.get(sid, 0), amount)
    if idle > 0:
        spare[sid] -= idle
        plan["idle"][sid] = plan["idle"].get(sid, 0) + idle
    if amount - idle > 1e-9:
        plan["factories"][sid] = plan["factories"].get(sid, 0) + (amount - idle) / cap
    for t, q in inputs.items():
        plan_increase(sde, t, q * amount / cap, surplus, spare, plan, depth + 1)
    return plan


def suggestions(sde, items, factories, per_planet):
    """最終製品（他の工場で使わないもの）を作る工場を満稼働にするための提案と、提案のあとも余る材料。

    余っている材料を先に使い、足りない分だけ工場・抽出を増やす。段階の高い製品から順に余りを割り当てる。
    """
    consumed = set()
    for sid in factories:
        consumed.update(t for t, _ in sde.schematics[sid]["inputs"])
    surplus = {t: v["supply"] - v["used"] for t, v in items.items() if v["supply"] - v["used"] > 1e-6}
    spare = {sid: f["capacity"] - f["output"] for sid, f in factories.items()}
    plans = []
    ends = [(sid, f) for sid, f in factories.items() if f["type_id"] not in consumed]
    for sid, f in sorted(ends, key=lambda kv: (-sde.pi_tiers.get(kv[1]["type_id"], 0), kv[1]["utilization"])):
        if f["utilization"] >= 0.995:
            continue
        _, _, inputs = schematic_rates(sde, sid)
        short = {t: q * f["count"] * (1 - f["utilization"]) for t, q in inputs.items()}
        plan = new_plan()
        for t, amount in short.items():
            plan_increase(sde, t, amount, surplus, spare, plan, 1)
        planets = {t: amt / per_planet for t, amt in plan["extract"].items()}
        plans.append({
            "schematic_id": sid, "type_id": f["type_id"], "utilization": f["utilization"], "count": f["count"],
            "gain_per_day": f["capacity"] - f["output"], "short": short, "plan": plan, "planets": planets,
            "total_planets": sum(planets.values()),
        })
    # 提案のあとも余る材料。P0・P1 は「抽出惑星何個分か」も出す（切り替えの候補）
    leftover = []
    for t, amount in sorted(surplus.items(), key=lambda kv: sde.pi_tiers.get(kv[0], 0)):
        if amount <= 1e-6 or t not in consumed and sde.pi_tiers.get(t, 0) > 0 and items[t]["demand"] == 0:
            continue  # 最終製品は「余り」ではない
        tier = sde.pi_tiers.get(t, 0)
        p0 = amount if tier == 0 else amount * p0_ratio(sde, t) if tier == 1 else None
        leftover.append({"type_id": t, "amount": amount, "tier": tier,
                         "planets": p0 / per_planet if p0 is not None else None})
    return {"plans": plans, "leftover": leftover}


def p0_ratio(sde, p1_type_id):
    """P1 を 1 個作るのに使う P0 の数（通常 150）。"""
    sid = producer_schematic(sde, p1_type_id)
    s = sde.schematics[sid]
    return s["inputs"][0][1] / s["output"][1]


def free_slots(levels, colony_count):
    """キャラクターの空いているコロニーの枠。"""
    return 1 + levels.get(SKILL_INTERPLANETARY_CONSOLIDATION, 0) - colony_count


def ceil1(x):
    return math.ceil(x - 1e-9)
