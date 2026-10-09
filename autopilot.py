"""オートパイロットで移動したときの時間の見積もり。

1 星系ごとに「整列 → ワープ → ゲートに近づく → ジャンプ」を足す。
  - ワープ: EVE のワープの式（加速は ワープ速度 k AU/s、減速は j = min(k/3, 2)）。
    加速中の速度 e^(k·t) m/s、減速中の速度 v_max·e^(-j·t)、亜光速の半分（最大 100 m/s）まで落ちたらワープが終わる。
  - オートパイロットはゲートの 15 km 手前にワープするので、ジャンプできる 2.5 km まで近づく分も足す。
  - ゲートを通るとき（ジャンプ・読み込み）は 1 回 JUMP_SECONDS 秒とみなす。
星系の中の位置はゲート・ステーションの座標（ESI）。出発地にステーションを指定しないときは恒星（原点）から出発する。
"""

import math

from align import align_times

AU = 149_597_870_700  # m
JUMP_SECONDS = 10      # ゲートを通る（ジャンプの演出・読み込み）
DOCK_SECONDS = 5       # ステーションに入る
GATE_LANDING = 15_000  # オートパイロットはゲートの 15 km 手前に出る
JUMP_RANGE = 2_500     # ゲートを使える距離
MIN_WARP = 150_000     # これより近いとワープできない
ATTR_MAX_VELOCITY = 37
ATTR_WARP_SPEED = 600       # warpSpeedMultiplier
ATTR_BASE_WARP_SPEED = 1281
SKILL_NAVIGATION = 3449     # 最高速度 +5% / レベル


def ship_stats(data, ship_id, levels):
    """艦の {warp: AU/s, velocity: m/s, align: 秒}（装備なし・スキル込み。艦のボーナスは含まない）。"""
    data.ensure([ship_id])
    warp = data.attr(ship_id, ATTR_WARP_SPEED, 1) * data.attr(ship_id, ATTR_BASE_WARP_SPEED, 1)
    velocity = data.attr(ship_id, ATTR_MAX_VELOCITY, 0) * (1 + 0.05 * levels.get(SKILL_NAVIGATION, 0))
    return {"warp": warp, "velocity": velocity, "align": align_times(data, ship_id, [], levels)["normal"]}


def warp_seconds(distance, warp_au, velocity):
    """distance m をワープする時間（秒）。"""
    if distance < MIN_WARP:
        return 0.0
    k = warp_au
    j = min(k / 3, 2)
    v_max = k * AU
    v_exit = min(velocity / 2, 100) or 1
    if distance >= v_max / k + v_max / j:  # 最高速度まで出る
        cruise = (distance - v_max / k - v_max / j) / v_max
        return math.log(v_max) / k + cruise + math.log(v_max / v_exit) / j
    peak = distance * k * j / (k + j)  # 短いワープは最高速度に届かない
    return math.log(peak) / k + max(math.log(peak / v_exit), 0) / j


def approach_seconds(distance, velocity, align):
    """止まった状態から distance m 進む時間（加速の分は時定数 τ = 整列時間 / ln4 を足して近似）。"""
    if distance <= 0 or not velocity:
        return 0.0
    return distance / velocity + align / math.log(4)


def distance(a, b):
    return math.dist((a["x"], a["y"], a["z"]), (b["x"], b["y"], b["z"]))


ORIGIN = {"x": 0.0, "y": 0.0, "z": 0.0}


def estimate(route, gates, ship, start=None, end=None):
    """route: 星系 ID の並び、gates: {星系 ID: {行き先の星系 ID: ゲートの座標}}、ship: ship_stats() の結果。
    start / end: 出発・到着のステーションの座標（無ければ出発は恒星、到着はゲートを出たところで終わり）。

    戻り値: {"seconds", "align", "warp", "approach", "jump", "dock", "missing_gates"}
    """
    parts = {"align": 0.0, "warp": 0.0, "approach": 0.0, "jump": 0.0, "dock": 0.0}
    missing = 0
    for i, sid in enumerate(route):
        here = gates.get(sid, {})
        pos = (start or ORIGIN) if i == 0 else here.get(route[i - 1])
        if i < len(route) - 1:
            target = here.get(route[i + 1])
            if pos is None or target is None:
                missing += 1
                continue
            parts["align"] += ship["align"]
            parts["warp"] += warp_seconds(distance(pos, target) - GATE_LANDING, ship["warp"], ship["velocity"])
            parts["approach"] += approach_seconds(GATE_LANDING - JUMP_RANGE, ship["velocity"], ship["align"])
            parts["jump"] += JUMP_SECONDS
        elif end and pos is not None:
            parts["align"] += ship["align"]
            parts["warp"] += warp_seconds(distance(pos, end), ship["warp"], ship["velocity"])
            parts["dock"] += DOCK_SECONDS
    return {"seconds": sum(parts.values()), **parts, "missing_gates": missing}
