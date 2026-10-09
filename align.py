"""ワープに入るまでの時間（整列時間）と、マイクロワープドライブ（MWD）の小技の効果。

整列時間: 最高速度の 75% に達するまでの時間 = -ln(0.25) × 慣性係数 × 質量 / 1,000,000（秒）
MWD の小技: 目的地に向けて MWD を起動し、サイクルの終わりにワープする。MWD の加速で速度が上がり、
  MWD が切れた瞬間に「素の最高速度の 75%」を超えているので、ほぼサイクルの長さ（約 10 秒）でワープに入れる。
  → 素の整列時間がサイクルより十分長い艦（戦艦・輸送艦など）だけ速くなる。短い艦はかえって遅い。
"""

import math

ATTR_MASS = 4
ATTR_AGILITY = 70
ATTR_DURATION = 73
ATTR_SPEED_FACTOR = 20
ATTR_THRUST = 567
ATTR_MASS_ADDITION = 796
ATTR_SIG_BONUS = 554          # MWD だけにある（シグネチャの増加）
PROPULSION_GROUP_ID = 46
SKILL_EVASIVE_MANEUVERING = 3453  # 慣性係数 -5% / レベル
SKILL_SPACESHIP_COMMAND = 3327    # 慣性係数 -2% / レベル
SKILL_ACCELERATION_CONTROL = 3452  # AB・MWD の速度 +5% / レベル
EFFECTIVE_RATIO = 0.8  # 小技の整列時間が素の 80% 以下なら「効果あり」

MWD_TO_AB = {"5MN": "1MN", "50MN": "10MN", "500MN": "100MN"}


def is_mwd(data, type_id):
    return data.types[type_id]["group_id"] == PROPULSION_GROUP_ID and data.attr(type_id, ATTR_SIG_BONUS, 0) > 0


def align_times(data, ship_id, fitted, levels):
    """{"normal": 素の整列時間（秒）, "trick": MWD の小技での時間 or None, "effective": 小技の効果があるか, "mwd": MWD の type_id}"""
    data.ensure([ship_id, *fitted])
    mass = data.attr(ship_id, ATTR_MASS, 0)
    mwd = None
    for t in fitted:
        if data.types[t]["group_id"] == PROPULSION_GROUP_ID:
            if is_mwd(data, t):
                mwd = t
        else:
            mass += data.attr(t, ATTR_MASS_ADDITION, 0)  # アーマープレートなど
    agility = data.attr(ship_id, ATTR_AGILITY, 0) * (1 - 0.05 * levels.get(SKILL_EVASIVE_MANEUVERING, 0)) \
        * (1 - 0.02 * levels.get(SKILL_SPACESHIP_COMMAND, 0))
    normal = -math.log(0.25) * agility * mass / 1e6
    result = {"normal": normal, "trick": None, "effective": False, "mwd": mwd}
    if not mwd or not mass:
        return result
    boosted_mass = mass + data.attr(mwd, ATTR_MASS_ADDITION, 0)
    speed_factor = data.attr(mwd, ATTR_SPEED_FACTOR, 0) * (1 + 0.05 * levels.get(SKILL_ACCELERATION_CONTROL, 0))
    ratio = 1 + speed_factor / 100 * data.attr(mwd, ATTR_THRUST, 0) / boosted_mass  # MWD 中の最高速度 / 素の最高速度
    cycle = data.attr(mwd, ATTR_DURATION, 10000) / 1000
    reach = -agility * boosted_mass / 1e6 * math.log(1 - 0.75 / ratio) if ratio > 0.75 else math.inf
    trick = max(cycle, reach)
    result.update(trick=trick, effective=trick <= normal * EFFECTIVE_RATIO)
    return result


def ab_name_for(mwd_name):
    """MWD の名前 → 同じ大きさのアフターバーナーの名前（候補を順に）。"""
    size = mwd_name.split(" ", 1)[0]
    ab_size = MWD_TO_AB.get(size, "1MN")
    names = []
    if "Compact" in mwd_name:
        names.append(f"{ab_size} Y-S8 Compact Afterburner")
    if mwd_name.endswith(" II"):
        names.append(f"{ab_size} Afterburner II")
    names += [f"{ab_size} Afterburner I", f"{ab_size} Afterburner II"]
    return names
