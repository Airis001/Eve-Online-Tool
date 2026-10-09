"""PvP 向けの性能: 速さ（推進モジュール込み）・ワープ妨害 / ウェブの射程・遠隔回復の量。

いずれも目安。艦ボーナス（インターセプターの速度・ロジ艦の回復量など）とオーバーヒートは含めない。
"""

from dps import stacking

ATTR_MAX_VELOCITY = 37
ATTR_MASS = 4
ATTR_MASS_ADDITION = 796
ATTR_SPEED_FACTOR = 20
ATTR_THRUST = 567
ATTR_MAX_RANGE = 54
ATTR_DURATION = 73
ATTR_WARP_SCRAMBLE_STRENGTH = 105
ATTR_ARMOR_REPAIR = 84
ATTR_SHIELD_BONUS = 68
ATTR_SIG_BONUS = 554  # MWD だけにある
PROPULSION_GROUP = 46
WARP_SCRAMBLER_GROUP = 52
WEBIFIER_GROUP = 65
SKILL_NAVIGATION = 3449
SKILL_ACCELERATION_CONTROL = 3452
VELOCITY_BONUS_ATTR_NAME = "implantBonusVelocity"  # オーバードライブ・ナノファイバー・ポリカーボン


def _attr_by_name(data, type_id, name):
    for key, value in data.types[type_id]["attrs"].items():
        if data.attr_name(int(key)) == name:
            return value
    return 0.0


def speed(data, ship, fitted, levels):
    """{"base": 素の最高速度, "prop": 推進モジュール起動中, "prop_kind": "MWD" / "AB" / None}（m/s）"""
    base = data.attr(ship, ATTR_MAX_VELOCITY, 0) * (1 + 0.05 * levels.get(SKILL_NAVIGATION, 0))
    bonuses = [1 + v / 100 for m in fitted if (v := _attr_by_name(data, m, VELOCITY_BONUS_ATTR_NAME))]
    base *= stacking(bonuses) if bonuses else 1.0
    mass = data.attr(ship, ATTR_MASS, 0) + sum(data.attr(m, ATTR_MASS_ADDITION, 0) for m in fitted)
    prop = next((m for m in fitted if data.types[m]["group_id"] == PROPULSION_GROUP), None)
    if not prop or not mass:
        return {"base": base, "prop": None, "prop_kind": None}
    factor = data.attr(prop, ATTR_SPEED_FACTOR, 0) * (1 + 0.05 * levels.get(SKILL_ACCELERATION_CONTROL, 0))
    boosted = base * (1 + factor / 100 * data.attr(prop, ATTR_THRUST, 0) / mass)
    return {"base": base, "prop": boosted, "prop_kind": "MWD" if data.attr(prop, ATTR_SIG_BONUS, 0) else "AB"}


def tackle(data, fitted):
    """ワープ妨害・ウェブ: [{"kind": "scram" / "point" / "web", "range": m, "strength": 点}]（同じものはまとめる）"""
    found = {}
    for m in fitted:
        group = data.types[m]["group_id"]
        if group == WARP_SCRAMBLER_GROUP:
            strength = data.attr(m, ATTR_WARP_SCRAMBLE_STRENGTH, 1)
            kind = "scram" if strength >= 2 else "point"
        elif group == WEBIFIER_GROUP:
            kind, strength = "web", 0
        else:
            continue
        rng = data.attr(m, ATTR_MAX_RANGE, 0)
        key = (kind, rng)
        entry = found.setdefault(key, {"kind": kind, "range": rng, "strength": strength, "count": 0})
        entry["count"] += 1
    return sorted(found.values(), key=lambda e: ("point", "scram", "web").index(e["kind"]))


def reps(data, fitted):
    """遠隔回復: {"armor": HP/秒, "shield": HP/秒, "range": 最短の射程 m}"""
    armor = shield = 0.0
    ranges = []
    for m in fitted:
        names = {e["name"] for e in data.type_effects(m)}
        duration = data.attr(m, ATTR_DURATION, 0) / 1000
        if not duration:
            continue
        if "shipModuleRemoteArmorRepairer" in names:
            armor += data.attr(m, ATTR_ARMOR_REPAIR, 0) / duration
        elif "shipModuleRemoteShieldBooster" in names:
            shield += data.attr(m, ATTR_SHIELD_BONUS, 0) / duration
        else:
            continue
        ranges.append(data.attr(m, ATTR_MAX_RANGE, 0))
    return {"armor": armor, "shield": shield, "range": min(ranges) if ranges else 0}


def compute(data, ship, fitted, levels):
    return {"speed": speed(data, ship, fitted, levels), "tackle": tackle(data, fitted), "reps": reps(data, fitted)}
