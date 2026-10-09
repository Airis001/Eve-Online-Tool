"""フィットのルール: スロット・ハードポイント・装着できる艦・同グループの上限・リグのサイズ・ドローンベイ・ワープコアの強度。

定番フィットの検証（validate_templates.py）と、フィットの作成ページで共通に使う。
"""

from i18n import tr

SLOT_EFFECTS = {11: "low", 12: "high", 13: "med", 2663: "rig", 3772: "subsystem"}
SHIP_SLOT_ATTRS = {"high": 14, "med": 13, "low": 12, "rig": 1137, "subsystem": 1367}
ATTR_LAUNCHER_SLOTS, ATTR_TURRET_SLOTS = 101, 102
EFFECT_LAUNCHER, EFFECT_TURRET = 40, 42
ATTR_RIG_SIZE = 1547
ATTR_MAX_GROUP_FITTED = 1544
ATTR_DRONE_BAY = 283
ATTR_DRONE_BANDWIDTH = 1271
ATTR_DRONE_BANDWIDTH_USED = 1272
ATTR_CHARGE_SIZE = 128
CHARGE_GROUP_ATTRS = (604, 605, 606, 609, 610)
ATTR_WARP_SCRAMBLE_STATUS = 104    # 艦のワープコアの強度（マイナスが強度）
ATTR_WARP_SCRAMBLE_STRENGTH = 105  # ワープコアスタビライザー（起動中）: マイナスが強度の加算
WCS_EFFECT = "warpCoreStabilizerActive"
CAN_FIT_GROUP_ATTRS = (1298, 1299, 1300, 1301, 1872, 1879, 1880, 1881, 2065, 2396, 2476, 2477, 2478, 2479,
                       2480, 2481, 2482, 2483, 2484, 2485)
CAN_FIT_TYPE_ATTRS = (1302, 1303, 1304, 1305, 1944, 2103, 2463, 2486, 2487, 2488, 2758)


def slot_of(data, type_id):
    """モジュールのスロット（high / med / low / rig / subsystem）。モジュールでなければ None。"""
    effects = set(data.types[type_id]["effects"])
    return next((s for e, s in SLOT_EFFECTS.items() if e in effects), None)


def slot_usage(data, ship, fitted):
    used = {k: 0 for k in SHIP_SLOT_ATTRS}
    launchers = turrets = 0
    for m in fitted:
        slot = slot_of(data, m)
        if slot:
            used[slot] += 1
        effects = set(data.types[m]["effects"])
        launchers += EFFECT_LAUNCHER in effects
        turrets += EFFECT_TURRET in effects
    total = {k: int(data.attr(ship, a, 0)) for k, a in SHIP_SLOT_ATTRS.items()}
    return {"used": used, "total": total, "launchers": launchers, "turrets": turrets,
            "launcher_total": int(data.attr(ship, ATTR_LAUNCHER_SLOTS, 0)),
            "turret_total": int(data.attr(ship, ATTR_TURRET_SLOTS, 0))}


def fit_errors(data, name_of, ship, fitted, drones, volume_of):
    """フィットの問題の一覧（日本語）。name_of(type_id) → 名前、volume_of(type_id) → 体積。drones: [(type_id, 個数)]"""
    errors = []
    usage = slot_usage(data, ship, fitted)
    labels = {"high": "ハイ", "med": "ミッド", "low": "ロー", "rig": "リグ", "subsystem": "サブシステム"}
    for slot, n in usage["used"].items():
        if n > usage["total"][slot]:
            errors.append(tr("{0}スロットが足りません（{1} / {2}）", labels[slot], n, usage['total'][slot]))
    if usage["launchers"] > usage["launcher_total"]:
        errors.append(tr("ランチャーのハードポイントが足りません（{0} / {1}）", usage['launchers'], usage['launcher_total']))
    if usage["turrets"] > usage["turret_total"]:
        errors.append(tr("タレットのハードポイントが足りません（{0} / {1}）", usage['turrets'], usage['turret_total']))
    ship_group = data.types[ship]["group_id"]
    for m in set(fitted):
        groups = {int(data.attr(m, a, 0)) for a in CAN_FIT_GROUP_ATTRS} - {0}
        types = {int(data.attr(m, a, 0)) for a in CAN_FIT_TYPE_ATTRS} - {0}
        if (groups or types) and ship_group not in groups and ship not in types:
            errors.append(tr("{0} はこの艦に装着できません", name_of(m)))
        if str(ATTR_RIG_SIZE) in data.types[m]["attrs"] and slot_of(data, m) == "rig" and \
                data.attr(m, ATTR_RIG_SIZE) != data.attr(ship, ATTR_RIG_SIZE):
            errors.append(tr("{0} はリグのサイズが合いません", name_of(m)))
    counts = {}
    for m in fitted:
        g = data.types[m]["group_id"]
        counts[g] = counts.get(g, 0) + 1
        limit = data.attr(m, ATTR_MAX_GROUP_FITTED, 0)
        if limit and counts[g] == limit + 1:
            errors.append(tr("{0} の仲間は {1} 個までしか装着できません", name_of(m), int(limit)))
    volume = sum(volume_of(d) * q for d, q in drones)
    if volume > data.attr(ship, ATTR_DRONE_BAY, 0) + 1e-6:
        errors.append(tr("ドローンがドローンベイに入りません（{0:g} / {1:g} m³）", volume, (data.attr(ship, ATTR_DRONE_BAY, 0))))
    return errors


def can_load(data, module, charge):
    """モジュールにその弾（チャージ）を装填できるか。"""
    groups = {int(data.attr(module, a, 0)) for a in CHARGE_GROUP_ATTRS} - {0}
    if not groups or data.types[charge]["group_id"] not in groups:
        return False
    size = data.attr(module, ATTR_CHARGE_SIZE, 0)
    return not size or data.attr(charge, ATTR_CHARGE_SIZE, 0) == size


def warp_strength(data, ship, fitted):
    """ワープコアの強度: {"base": 艦の強度, "wcs": スタビライザー起動中の加算}。"""
    base = -data.attr(ship, ATTR_WARP_SCRAMBLE_STATUS, 0)
    wcs = 0.0
    for m in fitted:
        if any(e["name"] == WCS_EFFECT for e in data.type_effects(m)):
            wcs = max(wcs, -data.attr(m, ATTR_WARP_SCRAMBLE_STRENGTH, 0))
    return {"base": base, "wcs": wcs}
