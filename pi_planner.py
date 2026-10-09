"""PI をゼロから配置し直したときの、一番稼げる配置の計算。

前提:
  - 選んだキャラクターの今のコロニーをすべて破棄し、コロニーの枠（1 + Interplanetary Consolidation）をすべて使う。
  - 惑星は 2 種類:
      抽出惑星 … エクストラクターコントロールユニット（ECU）で P0 を掘り、同じ惑星の基本工場で P1 にする。
      工場惑星 … 抽出惑星から運んだ材料で P2〜P4 を作る（高度工場・ハイテク工場）。
  - 惑星に置ける設備の数は、司令基地（Command Center Upgrades のレベル）の CPU・パワーグリッドで決まる。
    リンク（設備間の接続）の分として 10% を残す。
  - 抽出量は「ヘッド 1 本の 1 日の抽出量」×ヘッドの数。実際は惑星の資源の濃さ・抽出の期間で変わる。
  - 製品の価値は Jita の価格。輸送・税（税関の輸出税）は含めない。
"""

import math

import pi

SKILL_COMMAND_CENTER_UPGRADES = 2505
# 司令基地のレベル → (パワーグリッド, CPU)。SDE にはレベル 0 の値しか無いので、ゲーム内の値を使う
COMMAND_CENTER = {0: (6000, 1675), 1: (9000, 7057), 2: (12000, 12136), 3: (15000, 17215), 4: (17000, 21315), 5: (19000, 25415)}
LINK_MARGIN = 0.9  # リンクの分として CPU・パワーグリッドの 10% を残す
# 設備の (CPU, パワーグリッド)。SDE の値
ECU = (400, 2600)
HEAD = (110, 550)
BASIC = (200, 800)
ADVANCED = (500, 700)
HIGH_TECH = (1100, 400)
LAUNCHPAD = (3600, 700)
MAX_HEADS_PER_ECU = 10
BASIC_P0_PER_DAY = 3000 * 48  # 基本工場 1 台が 1 日に加工する P0
HIGH_TECH_PLANETS = {"barren", "temperate"}  # ハイテク工場（P4）を建てられる惑星
DEFAULT_PER_HEAD = 12_000


def capacity(level):
    pg, cpu = COMMAND_CENTER[max(0, min(5, level))]
    return cpu * LINK_MARGIN, pg * LINK_MARGIN


def extraction_design(level, per_head):
    """抽出惑星の設備: ヘッドの数が最大になる (ECU 数, ヘッド数, 基本工場数, 1 日の P0)。

    発射台を置けないとき（司令基地のレベルが低い）は、司令基地から直接打ち上げる設計にする。
    """
    for launchpad in (True, False):
        design = _extraction_design(level, per_head, launchpad)
        if design["heads"]:
            return design
    return design


def _extraction_design(level, per_head, launchpad):
    cpu, pg = capacity(level)
    if launchpad:
        cpu -= LAUNCHPAD[0]
        pg -= LAUNCHPAD[1]
    best = None
    for ecus in (1, 2):
        for heads in range(ecus * MAX_HEADS_PER_ECU, 0, -1):
            p0 = heads * per_head
            basic = math.ceil(p0 / BASIC_P0_PER_DAY)
            need_cpu = ecus * ECU[0] + heads * HEAD[0] + basic * BASIC[0]
            need_pg = ecus * ECU[1] + heads * HEAD[1] + basic * BASIC[1]
            if need_cpu <= cpu and need_pg <= pg:
                if not best or heads > best["heads"]:
                    split = [heads // ecus + (1 if i < heads % ecus else 0) for i in range(ecus)]
                    best = {"ecus": ecus, "heads": heads, "heads_per_ecu": split, "basic": basic, "p0_per_day": p0,
                            "launchpad": launchpad}
                break
    return best or {"ecus": 0, "heads": 0, "heads_per_ecu": [], "basic": 0, "p0_per_day": 0, "launchpad": launchpad}


def factory_capacity(level):
    """工場惑星で使える (CPU, パワーグリッド)（発射台の分を引いた後）。"""
    cpu, pg = capacity(level)
    return max(0.0, cpu - LAUNCHPAD[0]), max(0.0, pg - LAUNCHPAD[1])


def chain(sde, product):
    """製品 1 個/日 を作るのに必要な P0（/日）と、工場惑星の設備（台数・CPU・パワーグリッド）。P1 の基本工場は抽出惑星に置く。"""
    p0, factories, kinds = {}, {}, {}
    load = [0.0, 0.0]
    high_tech = False

    def need(t, qty):
        nonlocal high_tech
        sid = pi.producer_schematic(sde, t)
        if sid is None:
            p0[t] = p0.get(t, 0) + qty
            return
        out, cap, inputs = pi.schematic_rates(sde, sid)
        count = qty / cap
        tier = sde.pi_tiers.get(t, 0)
        if tier >= 2:
            kind = HIGH_TECH if tier == 4 else ADVANCED
            high_tech |= tier == 4
            factories[sid] = factories.get(sid, 0) + count
            kinds[sid] = kind
            load[0] += count * kind[0]
            load[1] += count * kind[1]
        for i, q in inputs.items():
            need(i, q * count)

    need(product, 1.0)
    return {"p0": p0, "factories": factories, "kinds": kinds, "cpu": load[0], "pg": load[1], "high_tech": high_tech}


def factory_counts(ch, rate):
    """rate 個/日 作るのに必要な工場の台数（整数に切り上げ）。"""
    return {sid: math.ceil(per_unit * rate - 1e-6) for sid, per_unit in ch["factories"].items()}


def assign(slots, home, ch, rate, per_head, used_planets):
    """製品を rate 個/日 作れるように、枠（slots）を抽出惑星・工場惑星に割り当てる。できなければ None。

    slots: [{"character_id", "name", "level"}]、used_planets: {character_id: 使用済みの惑星 ID の集合}（変更しない）
    """
    if rate <= 0:
        return []
    counts = factory_counts(ch, rate)
    need_cpu = sum(n * ch["kinds"][sid][0] for sid, n in counts.items())
    need_pg = sum(n * ch["kinds"][sid][1] for sid, n in counts.items())
    deficits = {r: a * rate for r, a in ch["p0"].items()}
    planets = home["planets"]
    by_resource = {r: [p for p in planets if r in p["resource_ids"]] for r in deficits}
    factory_ok = [p for p in planets if p["kind"] and (not ch["high_tech"] or p["kind"] in HIGH_TECH_PLANETS)]
    order = sorted(range(len(slots)), key=lambda i: -slots[i]["level"])
    # 工場惑星の数: 司令基地のレベルが高い順に足して、必要な CPU・パワーグリッドに届く最小の数
    n_factory, cpu, pg = 0, 0.0, 0.0
    while (cpu + 1e-6 < need_cpu or pg + 1e-6 < need_pg) and n_factory < len(order):
        c, g = factory_capacity(slots[order[n_factory]]["level"])
        cpu, pg, n_factory = cpu + c, pg + g, n_factory + 1
    for n_factory in (n_factory,):
        used = {k: set(v) for k, v in used_planets.items()}
        count = {}  # 惑星 ID → この計画で置いたコロニーの数（同じ惑星に集中させない）
        result = []
        cpu = pg = 0.0
        ok = True
        for i in order[:n_factory]:  # 工場惑星は司令基地のレベルが高いキャラクターから
            s = slots[i]
            free = [p for p in factory_ok if p["planet_id"] not in used.setdefault(s["character_id"], set())]
            if not free:
                ok = False
                break
            planet = min(free, key=lambda p: count.get(p["planet_id"], 0))
            used[s["character_id"]].add(planet["planet_id"])
            count[planet["planet_id"]] = count.get(planet["planet_id"], 0) + 1
            c, g = factory_capacity(s["level"])
            cpu += c
            pg += g
            result.append({**s, "role": "factory", "planet": planet, "cpu": c, "pg": g})
        if not ok or cpu + 1e-6 < need_cpu or pg + 1e-6 < need_pg:
            continue
        left = dict(deficits)
        for i in sorted(order[n_factory:], key=lambda i: -extraction_design(slots[i]["level"], per_head)["p0_per_day"]):
            if all(v <= 1e-6 for v in left.values()):
                break
            s = slots[i]
            design = extraction_design(s["level"], per_head)
            mine = used.setdefault(s["character_id"], set())
            options = [(r, p) for r, v in left.items() if v > 1e-6 for p in by_resource[r] if p["planet_id"] not in mine]
            if not options:
                continue
            # 足りない量が一番多い資源を、コロニーの少ない惑星で掘る
            r, planet = max(options, key=lambda rp: (left[rp[0]], -count.get(rp[1]["planet_id"], 0)))
            mine.add(planet["planet_id"])
            count[planet["planet_id"]] = count.get(planet["planet_id"], 0) + 1
            left[r] -= design["p0_per_day"]
            result.append({**s, "role": "extract", "planet": planet, "resource": r, **design})
        if all(v <= 1e-6 for v in left.values()):
            return result
    return None


def max_rate(sde, slots, home, ch, per_head, used_planets):
    """その枠で作れる最大の量（/日）と割り当て。二分探索。"""
    top = sum(extraction_design(s["level"], per_head)["p0_per_day"] for s in slots)
    total_p0 = sum(ch["p0"].values())
    if not total_p0 or not top:
        return 0.0, []
    lo, hi, best = 0.0, top / total_p0, []
    for _ in range(30):
        mid = (lo + hi) / 2
        a = assign(slots, home, ch, mid, per_head, used_planets)
        if a is not None:
            lo, best = mid, a
        else:
            hi = mid
    return lo, best


def redesign(sde, slots, home, prices, per_head, target=None, candidates_limit=12):
    """全コロニーを作り直すときの、一番稼げる配置。

    prices: {type_id: 1 個の価格}。target: 最初に作る製品（指定なしは ISK が最大のもの）。
    返り値: {"ranking": [...], "products": [...], "layout": [...], "unused": [...]}
    """
    products = [t for t, tier in sde.pi_tiers.items() if tier >= 1 and prices.get(t)]
    chains = {t: chain(sde, t) for t in products}
    ranking = []
    for t in products:
        rate, a = max_rate(sde, slots, home, chains[t], per_head, {})
        if rate > 0:
            ranking.append({"type_id": t, "tier": sde.pi_tiers[t], "per_day": rate, "isk_per_day": rate * prices[t],
                            "extract_planets": sum(x["role"] == "extract" for x in a),
                            "factory_planets": sum(x["role"] == "factory" for x in a)})
    ranking.sort(key=lambda r: -r["isk_per_day"])

    # 1 番目の製品で枠を使い、余った枠で次の製品…を繰り返す
    remaining = list(slots)
    used = {}
    chosen, layout = [], []
    first = target if target in chains else (ranking[0]["type_id"] if ranking else None)
    queue = [first] + [r["type_id"] for r in ranking if r["type_id"] != first] if first else []
    for t in queue:
        if not remaining:
            break
        rate, a = max_rate(sde, remaining, home, chains[t], per_head, used)
        if rate <= 0 or not a:
            continue
        chosen.append({"type_id": t, "tier": sde.pi_tiers[t], "per_day": rate, "isk_per_day": rate * prices[t],
                       "chain": chains[t]})
        taken = {(x["character_id"], x["slot"]) for x in a}
        for x in a:
            used.setdefault(x["character_id"], set()).add(x["planet"]["planet_id"])
            layout.append({**x, "product": t})
        remaining = [s for s in remaining if (s["character_id"], s["slot"]) not in taken]
        if len(chosen) >= 4:
            break
    distribute_factories(sde, chosen, layout)
    return {"ranking": ranking[:candidates_limit], "products": chosen, "layout": layout, "unused": remaining}


def distribute_factories(sde, chosen, layout):
    """工場惑星ごとに、置く工場（レシピと台数）を CPU・パワーグリッドの空きの順に割り振る。"""
    for c in chosen:
        planets = [x for x in layout if x["role"] == "factory" and x["product"] == c["type_id"]]
        for x in planets:
            x.setdefault("factories", {})
            x["cpu_left"], x["pg_left"] = x["cpu"], x["pg"]
        counts = factory_counts(c["chain"], c["per_day"])
        c["factory_counts"] = counts
        for sid, n in sorted(counts.items(), key=lambda kv: -sde.pi_tiers.get(sde.schematics[kv[0]]["output"][0], 0)):
            kind = c["chain"]["kinds"][sid]
            for _ in range(n):
                x = next((x for x in planets if x["cpu_left"] >= kind[0] and x["pg_left"] >= kind[1]), None)
                if x is None:  # 合計では足りているが 1 台ずつ詰めると入らない（リンクの余裕で調整）
                    x = max(planets, key=lambda x: min(x["cpu_left"] / kind[0], x["pg_left"] / kind[1]))
                x["factories"][sid] = x["factories"].get(sid, 0) + 1
                x["cpu_left"] -= kind[0]
                x["pg_left"] -= kind[1]
