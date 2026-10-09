"""フィットの PG / CPU / キャリブレーションが足りているかの判定（主要な補正のみ）。

計算に入れるもの:
  - 艦の CPU・PG・キャリブレーション（素の値）
  - スキルの補正（SKILL_RULES の表。補正量は ESI のスキルの属性値 × レベル）
  - モジュール・リグ・サブシステムが艦の CPU・PG・キャリブレーションを変える効果（ESI の効果データから自動）
  - リグの副作用で武器の CPU・PG が増える分（効果名から対象を判別。リギング系スキルの軽減も反映）
計算に入れないもの（含まれていれば approximate に理由を入れる）:
  - 艦固有のボーナス（例: 特定モジュールの CPU 軽減）
  - 対象を判別できないリグ・モジュールの効果
全モジュールはオンライン（有効）として計算する。
"""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from itertools import product

from i18n import tr
from paths import DATA_DIR

CACHE_FILE = DATA_DIR / "fitting_cache.json"

ATTR_CPU = 50            # モジュールの CPU 使用量
ATTR_POWER = 30          # モジュールの PG 使用量
ATTR_CAL_COST = 1153     # リグのキャリブレーション
ATTR_CPU_OUTPUT = 48     # 艦の CPU
ATTR_POWER_OUTPUT = 11   # 艦の PG
ATTR_CALIBRATION = 1132  # 艦のキャリブレーション
ATTR_DRAWBACK = 1138     # リグの副作用の大きさ
ATTR_RIG_DRAWBACK_BONUS = 1139  # リギング系スキルの副作用軽減（1 レベルあたり %）

ATTR_CARGO = 38           # カーゴ
ATTR_MINING_HOLD = 1556   # 採掘カーゴ（Ore Hold）
ATTR_DRONE_BAY = 283      # ドローンベイ
HOLD_ATTRS = {
    ATTR_CARGO: "cargo", ATTR_MINING_HOLD: "mining_hold", ATTR_DRONE_BAY: "drone_bay",
    # 専用カーゴ（特殊輸送艦など）
    1653: "pi_hold", 1646: "command_center_hold", 1558: "mineral_hold", 3136: "ice_hold",
    1557: "gas_hold", 1573: "ammo_hold", 908: "ship_maintenance_bay",
}

# 容量の艦ボーナスの属性名 → 1 レベルごとに増やすスキル（表 HULL_HOLD_BONUS_SKILLS に無いもの用）
INDUSTRIAL_BONUS_SKILLS = {"amarrIndustrialBonus": 3343, "caldariIndustrialBonus": 3342,
                           "gallenteIndustrialBonus": 3340, "minmatarIndustrialBonus": 3341, "freighterBonusO": 34327}

FITTING_SHIP_ATTRS = {ATTR_CPU_OUTPUT, ATTR_POWER_OUTPUT, ATTR_CALIBRATION}
SHIP_ATTRS = FITTING_SHIP_ATTRS | set(HOLD_ATTRS)
NEED_ATTRS = {ATTR_CPU, ATTR_POWER, ATTR_CAL_COST}

# 効果のカテゴリ: 0 = 常時（リグ・サブシステム・スキル）、4 = オンライン時。1（起動時）は含めない
PASSIVE_EFFECT_CATEGORIES = {0, 4}

# スキルの補正。ESI の効果データには「どのスキルが必要なモジュールが対象か」が含まれないため、表で持つ。
#   (スキル ID, 補正する属性, 補正量の属性, 対象)
#   対象: "ship" = 艦 / {"skills": {...}} = そのスキルが必要なモジュール / {"groups": {...}} = そのグループのモジュール
SKILL_RULES = [
    (3426, ATTR_CPU_OUTPUT, 424, "ship"),                                 # CPU Management
    (3413, ATTR_POWER_OUTPUT, 313, "ship"),                               # Power Grid Management
    (3318, ATTR_CPU, 310, {"skills": {3300, 3319, 3421}, "groups": {862}}),   # Weapon Upgrades
    (11207, ATTR_POWER, 323, {"skills": {3300, 3319, 3421}, "groups": {862}}),  # Advanced Weapon Upgrades
    (3425, ATTR_POWER, 323, {"skills": {3425}}),                          # Shield Upgrades
    (3424, ATTR_CPU, 310, {"skills": {3424}}),                            # Energy Grid Upgrades
    (3432, ATTR_CPU, 310, {"skills": {3432}}),                            # Electronics Upgrades
]

# モジュール・リグが他のモジュールの CPU・PG を変える効果の対象（ESI にはこの情報が無いため効果名で判別）
# 効果名に含まれる語 → 対象
DRAWBACK_TARGETS = [
    ("Launcher", {"skills": {3319}}),       # リグの副作用: ミサイルランチャー
    ("Hybrid", {"groups": {74}}),           # リグの副作用: ハイブリッドタレット
    ("Laser", {"groups": {53}}),            # リグの副作用: エネルギータレット
    ("EnergyWeapon", {"groups": {53}}),
    ("Projectile", {"groups": {55}}),       # リグの副作用: プロジェクタイルタレット
    ("RepairSystems", {"skills": {3393}}),  # リグの副作用: アーマーリペア（Repair Systems が必要なモジュール）
    ("iceMinerCpu", {"skills": {16281}}),   # Ice Harvester Upgrade: 氷採掘モジュール（Ice Harvesting が必要なモジュール）
    ("minerCpu", {"skills": {3386}}),       # Mining Laser Upgrade: 採掘レーザー（Mining が必要なモジュール）
]

# 艦の「スキル 1 レベルごと」の容量ボーナス。ESI には「どのスキルで増えるか」が無いため表で持つ。
#   ボーナス量の属性 ID（艦の属性） → スキル ID
HULL_HOLD_BONUS_SKILLS = {
    3187: 17940,  # miningBargeBonusGeneralMiningHoldCapacity → Mining Barge（Retriever・Mackinaw の採掘カーゴ）
    3198: 22551,  # exhumersBonusGeneralMiningHoldCapacity → Exhumers（Mackinaw）
    3212: 29637,  # industrialCommandBonusGeneralMiningHoldCapacity → Industrial Command Ships（Orca・Porpoise）
    3211: 29637,  # industrialCommandBonusShipCargoCapacity → Industrial Command Ships
    3241: 3340,   # gallenteIndustrialBonusMiningHoldCapacity → Gallente Hauler（Miasmos）
    494: 3343,    # shipBonusAI → Amarr Hauler
    495: 3342,    # shipBonusCI → Caldari Hauler
    496: 3340,    # shipBonusGI → Gallente Hauler
    493: 3341,    # shipBonusMI → Minmatar Hauler
    887: 20524,   # freighterBonusA2 → Amarr Freighter
    889: 20526,   # freighterBonusC2 → Caldari Freighter
    890: 20527,   # freighterBonusG2 → Gallente Freighter
    893: 20528,   # freighterBonusM2 → Minmatar Freighter
}

# 艦のボーナスのうち、特定のモジュールの CPU・PG を減らすもの（効果名に含まれる語 → 対象）
SHIP_MODULE_TARGETS = [
    ("Cloak", {"groups": {330}}),                   # クローキング装置（Covert Ops・ボマー・ブロッケードランナーなど）
    ("covertOpsCpu", {"groups": {330}}),            # ボマーのクローキング装置の CPU 軽減（効果名に Cloak が無い）
    ("SiegeMissileLauncher", {"groups": {508}}),    # 魚雷ランチャー（ボマー）
    ("Torpedo", {"groups": {508}}),
]

# 計算の順番（EVE の dogma の演算子番号）
OP_PRE_MUL, OP_PRE_DIV, OP_MOD_ADD, OP_MOD_SUB, OP_POST_MUL, OP_POST_DIV, OP_POST_PERCENT, OP_POST_ASSIGN = 0, 1, 2, 3, 4, 5, 6, 7

FITTED_FLAGS = ("LoSlot", "MedSlot", "HiSlot", "RigSlot", "SubSystemSlot")


class FittingData:
    """型の dogma 属性・効果を ESI から取得してキャッシュする。"""

    def __init__(self, esi_get, path=CACHE_FILE):
        self.esi_get = esi_get
        self.path = path
        self._lock = threading.RLock()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            raw = {}
        self.types = {int(k): v for k, v in raw.get("types", {}).items()}
        self.effects = {int(k): v for k, v in raw.get("effects", {}).items()}
        self.attr_names = {int(k): v for k, v in raw.get("attr_names", {}).items()}
        self.dirty = False

    def attr_name(self, attr_id):
        """dogma 属性の名前（艦ボーナスの種類の判別に使う）。"""
        if attr_id not in self.attr_names:
            self.attr_names[attr_id] = self.esi_get(f"/dogma/attributes/{attr_id}/").get("name", "")
            self.dirty = True
        return self.attr_names[attr_id]

    def save(self):
        with self._lock:
            if self.dirty:
                data = {"types": self.types, "effects": self.effects, "attr_names": self.attr_names}
                self.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                self.dirty = False

    def _fetch_type(self, type_id):
        data = self.esi_get(f"/universe/types/{type_id}/")
        return type_id, {
            "group_id": data.get("group_id"),
            "attrs": {str(a["attribute_id"]): a["value"] for a in data.get("dogma_attributes", [])},
            "effects": [e["effect_id"] for e in data.get("dogma_effects", [])],
        }

    def _fetch_effect(self, effect_id):
        data = self.esi_get(f"/dogma/effects/{effect_id}/")
        return effect_id, {
            "name": data.get("name", ""),
            "category": data.get("effect_category"),
            "modifiers": [
                {"func": m.get("func"), "domain": m.get("domain"), "attr": m.get("modified_attribute_id"),
                 "by": m.get("modifying_attribute_id"), "op": m.get("operator")}
                for m in data.get("modifiers", [])
            ],
        }

    def ensure(self, type_ids):
        """型と、その型の効果をまとめて取得する（並列）。"""
        missing = [t for t in set(type_ids) if t not in self.types]
        if missing:
            with ThreadPoolExecutor(max_workers=10) as pool:
                fetched = list(pool.map(self._fetch_type, missing))
            with self._lock:
                self.types.update(fetched)
                self.dirty = True
        effect_ids = {e for t in type_ids for e in self.types[t]["effects"]}
        missing_effects = [e for e in effect_ids if e not in self.effects]
        if missing_effects:
            with ThreadPoolExecutor(max_workers=10) as pool:
                fetched = list(pool.map(self._fetch_effect, missing_effects))
            with self._lock:
                self.effects.update(fetched)
                self.dirty = True

    def attr(self, type_id, attr_id, default=0.0):
        return self.types[type_id]["attrs"].get(str(attr_id), default)

    def type_effects(self, type_id):
        return [self.effects[e] for e in self.types[type_id]["effects"] if e in self.effects]


def _apply(base, mods):
    """EVE の dogma の順番で補正を適用する。mods: [(演算子, 値)]"""
    value = base
    for op in (OP_PRE_MUL, OP_PRE_DIV, OP_MOD_ADD, OP_MOD_SUB, OP_POST_MUL, OP_POST_DIV, OP_POST_PERCENT, OP_POST_ASSIGN):
        for o, v in mods:
            if o != op:
                continue
            if op in (OP_PRE_MUL, OP_POST_MUL):
                value *= v
            elif op in (OP_PRE_DIV, OP_POST_DIV):
                value = value / v if v else value
            elif op == OP_MOD_ADD:
                value += v
            elif op == OP_MOD_SUB:
                value -= v
            elif op == OP_POST_PERCENT:
                value *= 1 + v / 100
            elif op == OP_POST_ASSIGN:
                value = v
    return value


def fitted_type_ids(items):
    """ESI のフィットの items から、スロットに装着するモジュールの type_id（数量分）を取り出す。"""
    result = []
    for item in items:
        if item["flag"].startswith(FITTED_FLAGS):
            result += [item["type_id"]] * max(item.get("quantity", 1), 1)
    return result


def hold_bonus_skill(data, type_cache, ship_type_id, bonus_attr):
    """容量の艦ボーナス → (1 レベルごとに増やすスキル, 固定ボーナスか)。"""
    if bonus_attr in HULL_HOLD_BONUS_SKILLS:
        return HULL_HOLD_BONUS_SKILLS[bonus_attr], False
    from dps import HULL_RE, HULL_SKILLS, ROLE_RE  # dps は fitting を読み込まないので循環しない
    name = data.attr_name(bonus_attr)
    if ROLE_RE.match(name):
        return None, True
    if m := HULL_RE.match(name):
        return HULL_SKILLS.get((m.group(1), m.group(2))), False
    for prefix, skill_id in INDUSTRIAL_BONUS_SKILLS.items():
        if name.startswith(prefix):
            return skill_id, False
    reqs = type_cache.get(ship_type_id)["requirements"]  # 判別できなければ艦種スキル
    return (reqs[0][0] if reqs else None), False


def _prepare(data, type_cache, ship_type_id, fitted_ids, levels):
    """スキルレベルに依存しない部分（モジュールの属性・モジュール同士の効果）をまとめる。"""
    rule_skills = [r[0] for r in SKILL_RULES]
    data.ensure([ship_type_id, *fitted_ids, *rule_skills])
    rig_skill_ids = {req for t in set(fitted_ids) for req, _ in type_cache.get(t)["requirements"]}
    data.ensure(rig_skill_ids)

    approximate = []

    def matches(type_id, target):
        reqs = {req for req, _ in type_cache.get(type_id)["requirements"]}
        return bool(reqs & target.get("skills", set())) or data.types[type_id]["group_id"] in target.get("groups", set())

    # モジュール（個体ごと）の属性: リグの副作用はリギング系スキルで軽減される
    modules = []
    for type_id in fitted_ids:
        attrs = {int(k): v for k, v in data.types[type_id]["attrs"].items()}
        if ATTR_DRAWBACK in attrs:
            for skill_id in {req for req, _ in type_cache.get(type_id)["requirements"]}:
                bonus = data.attr(skill_id, ATTR_RIG_DRAWBACK_BONUS, 0)
                if bonus and levels.get(skill_id):
                    attrs[ATTR_DRAWBACK] *= 1 + bonus * levels[skill_id] / 100
        modules.append({"type_id": type_id, "attrs": attrs, "mods": []})

    ship_mods = {a: [] for a in SHIP_ATTRS}

    # モジュール・リグ・サブシステムの効果（スキルレベルに依存しない）
    for m in modules:
        for effect in data.type_effects(m["type_id"]):
            if effect["category"] not in PASSIVE_EFFECT_CATEGORIES:
                continue
            for mod in effect["modifiers"]:
                attr_id = mod["attr"]
                value = m["attrs"].get(mod["by"])
                if value is None or mod["domain"] != "shipID":
                    continue
                if attr_id in SHIP_ATTRS and mod["func"] == "ItemModifier":
                    ship_mods[attr_id].append((mod["op"], value))
                elif attr_id in NEED_ATTRS and mod["func"] in ("LocationRequiredSkillModifier", "LocationGroupModifier"):
                    target = next((t for word, t in DRAWBACK_TARGETS if word in effect["name"]), None)
                    if target is None:
                        approximate.append(tr("{0} の効果の一部", type_cache.get(m['type_id'])['name']))
                        continue
                    for other in modules:
                        if matches(other["type_id"], target):
                            other["mods"].append((attr_id, mod["op"], value))

    # 艦固有のボーナス: 容量と、特定のモジュール（クローキング装置など）の CPU・PG は反映する。それ以外の CPU・PG 関係は反映しない
    hull_rules = []
    for effect in data.type_effects(ship_type_id):
        if effect["category"] not in PASSIVE_EFFECT_CATEGORIES:
            continue
        for mod in effect["modifiers"]:
            target = next((t for word, t in SHIP_MODULE_TARGETS if word in effect["name"]), None)
            if mod["attr"] in NEED_ATTRS and target and mod["func"] in ("LocationRequiredSkillModifier", "LocationGroupModifier"):
                indexes = [i for i, m in enumerate(modules) if matches(m["type_id"], target)]
                if indexes:
                    skill_id, fixed = hold_bonus_skill(data, type_cache, ship_type_id, mod["by"])
                    fixed = fixed or mod["op"] != OP_POST_PERCENT  # 倍率で掛けるボーナス（×0.5 など）はレベルで変わらない
                    hull_rules.append({"skill_id": skill_id, "attr": mod["attr"], "op": mod["op"], "fixed": fixed,
                                       "per_level": data.attr(ship_type_id, mod["by"]), "modules": indexes})
            elif mod["attr"] in NEED_ATTRS | FITTING_SHIP_ATTRS:
                approximate.append("艦固有のボーナス")
            elif mod["attr"] in HOLD_ATTRS and mod["func"] == "ItemModifier" and mod["domain"] == "shipID":
                skill_id, fixed = hold_bonus_skill(data, type_cache, ship_type_id, mod["by"])
                hull_rules.append({"skill_id": skill_id, "attr": mod["attr"], "op": mod["op"], "fixed": fixed,
                                   "per_level": data.attr(ship_type_id, mod["by"]), "modules": None})

    # スキルの補正の対象（レベルは評価時に与える）
    rules = []
    for skill_id, attr_id, bonus_attr, target in SKILL_RULES:
        indexes = None if target == "ship" else [i for i, m in enumerate(modules) if matches(m["type_id"], target)]
        if indexes == []:
            continue  # このフィットには効かない
        rules.append({"skill_id": skill_id, "attr": attr_id, "per_level": data.attr(skill_id, bonus_attr), "modules": indexes})
    rules += hull_rules

    return {"ship_type_id": ship_type_id, "data": data, "modules": modules, "ship_mods": ship_mods,
            "rules": rules, "approximate": list(dict.fromkeys(approximate))}


def _evaluate(ctx, levels):
    """スキルレベル levels で CPU・PG・キャリブレーションを計算する。"""
    data = ctx["data"]
    ship_mods = {a: list(v) for a, v in ctx["ship_mods"].items()}
    module_mods = [list(m["mods"]) for m in ctx["modules"]]
    for rule in ctx["rules"]:
        level = 1 if rule.get("fixed") else levels.get(rule["skill_id"], 0)
        if not level:
            continue
        value = rule["per_level"] * level
        if rule["modules"] is None:
            ship_mods[rule["attr"]].append((rule.get("op", OP_POST_PERCENT), value))
        else:
            for i in rule["modules"]:
                module_mods[i].append((rule["attr"], rule.get("op", OP_POST_PERCENT), value))

    def total(attr_id):
        return _apply(data.attr(ctx["ship_type_id"], attr_id), ship_mods[attr_id])

    def used(attr_id):
        return sum(
            _apply(m["attrs"].get(attr_id, 0), [(o, v) for a, o, v in mods if a == attr_id])
            for m, mods in zip(ctx["modules"], module_mods)
        )

    result = {
        "cpu": {"used": used(ATTR_CPU), "total": total(ATTR_CPU_OUTPUT)},
        "power": {"used": used(ATTR_POWER), "total": total(ATTR_POWER_OUTPUT)},
        "calibration": {"used": used(ATTR_CAL_COST), "total": total(ATTR_CALIBRATION)},
    }
    for key in ("cpu", "power", "calibration"):
        r = result[key]
        r["used"], r["total"] = round(r["used"], 2), round(r["total"], 2)
        r["ok"] = r["used"] <= r["total"] + 1e-6

    # 容量（艦にその区画があるものだけ）
    result["holds"] = {}
    for attr_id, key in HOLD_ATTRS.items():
        base = data.attr(ctx["ship_type_id"], attr_id)
        if base:
            result["holds"][key] = {"base": base, "total": round(total(attr_id), 1)}
    return result


# CPU・PG のどちらに効くスキルか
CPU_ATTRS = {ATTR_CPU, ATTR_CPU_OUTPUT}
POWER_ATTRS = {ATTR_POWER, ATTR_POWER_OUTPUT}


def suggest_skills(ctx, levels, type_cache, cost_fn):
    """CPU・PG が足りないとき、どのスキルをどのレベルまで上げれば足りるか。

    候補のスキル（足りない項目に効き、このフィットに関係するもの）の組み合わせを全部試し、
    足りる組み合わせのうち訓練時間（cost_fn({skill_id: level}) → 分、前提スキル込み）が最短のものを返す。
    戻り値: {"skills": [{"skill_id", "name", "from", "to"}], "minutes"} / {"impossible": True} / None（不足なし）
    """
    current = _evaluate(ctx, levels)
    short_attrs = (CPU_ATTRS if not current["cpu"]["ok"] else set()) | (POWER_ATTRS if not current["power"]["ok"] else set())
    if not short_attrs:
        return None
    candidates = sorted({r["skill_id"] for r in ctx["rules"]
                         if r["attr"] in short_attrs and r["skill_id"] and not r.get("fixed") and levels.get(r["skill_id"], 0) < 5})

    def feasible(lv):
        r = _evaluate(ctx, lv)
        return r["cpu"]["ok"] and r["power"]["ok"]

    options = []
    for combo in product(*[range(levels.get(sk, 0), 6) for sk in candidates]):
        trial = {**levels, **dict(zip(candidates, combo))}
        if feasible(trial):
            options.append(combo)
    if not options:
        return {"impossible": True}

    # ほかの組み合わせより全スキルで低い（か同じ）ものだけを残してから、訓練時間で比べる
    minimal = [o for o in options if not any(p != o and all(a <= b for a, b in zip(p, o)) for p in options)]
    best = None
    for combo in minimal:
        targets = {sk: lv for sk, lv in zip(candidates, combo) if lv > levels.get(sk, 0)}
        minutes = cost_fn(targets)
        if best is None or (minutes or 0) < (best[1] or 0):
            best = (targets, minutes)
    targets, minutes = best
    return {
        "skills": [{"skill_id": sk, "name": type_cache.get(sk)["name"], "from": levels.get(sk, 0), "to": lv}
                   for sk, lv in targets.items()],
        "minutes": minutes,
    }


def check_resources(data, type_cache, ship_type_id, fitted_ids, character, cost_fn=None):
    """フィットの CPU・PG・キャリブレーションの使用量と上限を計算する。

    fitted_ids: スロットに装着するモジュールの type_id（同じモジュールは個数分）
    cost_fn: {skill_id: level} → 訓練時間（分）。渡すと、不足時に必要なスキルレベルを suggestion に入れる
    戻り値: {"cpu": {"used", "total", "ok"}, "power": {...}, "calibration": {...}, "ok", "approximate", "suggestion"}
    """
    levels = {s["skill_id"]: s["trained_level"] for s in character["skills"]}
    ctx = _prepare(data, type_cache, ship_type_id, fitted_ids, levels)
    result = _evaluate(ctx, levels)
    result["approximate"] = ctx["approximate"]
    result["ok"] = all(result[k]["ok"] for k in ("cpu", "power", "calibration"))
    result["suggestion"] = suggest_skills(ctx, levels, type_cache, cost_fn) if cost_fn else None
    return result
