"""定番フィットが無い艦のために、役割に合わせたフィットを自動で組む（試作）。

艦のスロット数・ハードポイント・艦ボーナス・大きさから、役割（ドローン・ミサイル・輸送・採掘）に合わせて
モジュールを選び、全スキル V で PG・CPU・キャリブレーションが収まるまで優先度の低いものから外す。
艦固有の使い方（センチネルドローン中心など）までは考えない「とりあえず使える構成」。
"""

import re

import fitting
from i18n import tr

ATTR_HI, ATTR_MED, ATTR_LOW, ATTR_RIG = 14, 13, 12, 1137
ATTR_LAUNCHER_SLOTS, ATTR_TURRET_SLOTS = 101, 102
ATTR_BANDWIDTH, ATTR_DRONE_BAY = 1271, 283
ATTR_MAX_GROUP_FITTED = 1544
CAN_FIT_GROUP_ATTRS = (1298, 1299, 1300, 1301, 1872, 1879, 1880, 1881, 2065, 2396, 2476, 2477, 2478, 2479,
                       2480, 2481, 2482, 2483, 2484, 2485)
CAN_FIT_TYPE_ATTRS = (1302, 1303, 1304, 1305, 1944, 2103, 2463, 2486, 2487, 2488, 2758)

# 艦のリグサイズ（1 = 小型艦、2 = 巡洋艦・巡洋戦艦・輸送艦、3 = 戦艦）→ 推進器・リペア・リグの大きさ
SIZE = {1: "Small", 2: "Medium", 3: "Large"}
PROP = {1: "1MN", 2: "10MN", 3: "100MN"}
SHIELD_EXT = {1: "Small", 2: "Medium", 3: "Large", 4: "Large", 5: "Large"}
RIG_SIZE_NAME = {1: "Small", 2: "Medium", 3: "Large"}

# ランチャー: 艦ボーナスの効果名に含まれる語 → (ランチャー, 弾の大きさ)
LAUNCHER_BY_WORD = [
    ("HeavyAssault", "Heavy Assault Missile Launcher", "Heavy Assault Missile"),
    ("RHML", "Rapid Heavy Missile Launcher", "Heavy Missile"),
    ("RapidLight", "Rapid Light Missile Launcher", "Light Missile"),
    ("Torpedo", "Torpedo Launcher", "Torpedo"),
    ("Cruise", "Cruise Missile Launcher", "Cruise Missile"),
    ("Heavy", "Heavy Missile Launcher", "Heavy Missile"),
    ("Rocket", "Rocket Launcher", "Rocket"),
    ("Light", "Light Missile Launcher", "Light Missile"),
    ("SmallMissile", "Light Missile Launcher", "Light Missile"),
    ("FrigateSizedMissile", "Light Missile Launcher", "Light Missile"),
]
LAUNCHER_BY_CLASS = {1: ("Light Missile Launcher", "Light Missile"), 2: ("Light Missile Launcher", "Light Missile"),
                     3: ("Rapid Light Missile Launcher", "Light Missile"), 4: ("Heavy Missile Launcher", "Heavy Missile"),
                     5: ("Cruise Missile Launcher", "Cruise Missile")}
# ダメージの種類 → 弾の名前（先頭の語）
CHARGE_BY_DAMAGE = {"kinetic": "Scourge", "thermal": "Inferno", "em": "Mjolnir", "explosive": "Nova"}

# タレット: 艦ボーナスの効果名に含まれる語 → 種類。種類 → 大きさごとの (タレット, 弾)、ダメージ強化モジュール
TURRET_KIND_WORDS = [
    ("hybrid", ("Hybrid", "HT", "Blaster", "Railgun")),
    ("projectile", ("Projectile", "PT", "AutoCannon", "Autocannon", "Artillery")),
    ("laser", ("Laser", "Energy", "ET", "Pulse", "Beam")),
]
TURRETS = {
    "hybrid": {1: ("Light Neutron Blaster II", "Antimatter Charge S"), 2: ("Heavy Neutron Blaster II", "Antimatter Charge M"),
               3: ("Neutron Blaster Cannon II", "Antimatter Charge L")},
    "projectile": {1: ("200mm AutoCannon II", "EMP S"), 2: ("425mm AutoCannon II", "EMP M"),
                   3: ("800mm Repeating Cannon II", "EMP L")},
    "laser": {1: ("Small Focused Pulse Laser II", "Multifrequency S"), 2: ("Focused Medium Pulse Laser II", "Multifrequency M"),
              3: ("Mega Pulse Laser II", "Multifrequency L")},
}
TURRET_DAMAGE_MOD = {"hybrid": "Magnetic Field Stabilizer II", "projectile": "Gyrostabilizer II", "laser": "Heat Sink II"}
TORPEDO_BY_DAMAGE = {"kinetic": "Scourge Torpedo", "thermal": "Inferno Torpedo", "em": "Mjolnir Torpedo", "explosive": "Nova Torpedo"}

# 外す優先度（先に外すもの）
REMOVE_ORDER = ["Power Diagnostic System", "Omnidirectional Tracking Link", "Cap Recharger", "Sensor Booster",
                "Target Painter", "Drone Navigation Computer", "Inertial Stabilizers", "Multispectrum Shield Hardener",
                "Multispectrum Energized Membrane", "Shield Extender", "Armor Repairer", "Mining Laser Upgrade",
                "Ice Harvester Upgrade",
                "Ballistic Control System", "Drone Damage Amplifier", "Magnetic Field Stabilizer", "Gyrostabilizer",
                "Heat Sink", "Expanded Cargohold", "Damage Control"]


class AutoFitter:
    def __init__(self, data, type_cache, catalog, calc, all_v_character):
        self.data = data
        self.type_cache = type_cache
        self.catalog = catalog
        self.calc = calc            # dps.DpsCalculator
        self.all_v = all_v_character

    def _exists(self, name):
        return self.catalog.find_by_name(name) is not None

    def _pick(self, *names):
        """最初に実在する名前。"""
        return next((n for n in names if n and self._exists(n)), None)

    def _can_fit(self, module_name, ship_id):
        type_id = self.catalog.find_by_name(module_name)
        if not type_id:
            return False
        self.data.ensure([type_id])
        groups = {int(self.data.attr(type_id, a, 0)) for a in CAN_FIT_GROUP_ATTRS} - {0}
        types = {int(self.data.attr(type_id, a, 0)) for a in CAN_FIT_TYPE_ATTRS} - {0}
        return not (groups or types) or self.data.types[ship_id]["group_id"] in groups or ship_id in types

    def _max_fitted(self, module_name, wanted):
        type_id = self.catalog.find_by_name(module_name)
        limit = int(self.data.attr(type_id, ATTR_MAX_GROUP_FITTED, 0)) if type_id else 0
        return min(wanted, limit) if limit else wanted

    def _tank(self, ship_id, meds, lows):
        names = " ".join(e["name"] for e in self.data.type_effects(ship_id))
        shield, armor = len(re.findall("Shield", names)), len(re.findall("Armor", names))
        if shield != armor:
            return "shield" if shield > armor else "armor"
        return "shield" if meds >= lows else "armor"

    def _launcher(self, ship_id, size_class):
        hull, _ = self.calc._hull_bonuses(ship_id, {})
        names = " ".join(e["name"] for e in self.data.type_effects(ship_id))
        launcher, charge_size = LAUNCHER_BY_CLASS.get(size_class, LAUNCHER_BY_CLASS[3])
        for word, name, size in LAUNCHER_BY_WORD:
            if word in names:
                launcher, charge_size = name, size
                break
        damage = [k.split(":")[1] for k, v in hull if k.startswith("missile_damage:") and v > 1]
        prefix = CHARGE_BY_DAMAGE.get(damage[0], "Scourge") if damage else "Scourge"
        charge = self._pick(f"{prefix} {charge_size}", f"Scourge {charge_size}")
        return self._pick(f"{launcher} II", f"{launcher} I"), charge

    def _turret_kind(self, ship_id):
        names = " ".join(e["name"] for e in self.data.type_effects(ship_id))
        for kind, words in TURRET_KIND_WORDS:
            if any(w in names for w in words):
                return kind
        return "hybrid"

    def _cloak(self, ship_id):
        return "Covert Ops Cloaking Device II" if self._can_fit("Covert Ops Cloaking Device II", ship_id) \
            else "Prototype Cloaking Device I"

    def _drones(self, ship_id):
        bandwidth = self.data.attr(ship_id, ATTR_BANDWIDTH, 0)
        bay = self.data.attr(ship_id, ATTR_DRONE_BAY, 0)
        # 帯域に合わせて一番大きいドローン 5 機、残りのドローンベイに小さいドローン（体積 = 帯域の戦闘用ドローン）
        plan = []
        for name, size in (("Ogre II", 25), ("Hammerhead II", 10), ("Hobgoblin II", 5)):
            if size * 5 <= bandwidth and bay >= size * 5:
                plan.append((name, 5))
                bay -= size * 5
                break
        else:
            for name, size in (("Hammerhead II", 10), ("Hobgoblin II", 5)):
                count = int(min(bandwidth, bay) // size)
                if count:
                    plan.append((name, min(count, 5)))
                    bay -= size * min(count, 5)
                    break
        for name, size in (("Hobgoblin II", 5),):
            if bay >= size * 5 and all(n != name for n, _ in plan):
                plan.append((name, 5))
                bay -= size * 5
        return plan

    # ---------- 組み立て ----------

    def build(self, ship_id, role, size_class, ship_group):
        """役割に合わせたモジュールを選ぶ。戻り値: {"high": [(名前, 弾)], "med": [...], "low": [...], "rig": [...], "bay": [(名前, 数)]}"""
        self.data.ensure([ship_id])
        hi, med, low, rig = (int(self.data.attr(ship_id, a, 0)) for a in (ATTR_HI, ATTR_MED, ATTR_LOW, ATTR_RIG))
        launchers = int(self.data.attr(ship_id, ATTR_LAUNCHER_SLOTS, 0))
        turrets = int(self.data.attr(ship_id, ATTR_TURRET_SLOTS, 0))
        rig_size = int(self.data.attr(ship_id, 1547, 0)) or 2
        rig_prefix = RIG_SIZE_NAME.get(rig_size, "Medium")
        tank = self._tank(ship_id, med, low)
        fit = {"high": [], "med": [], "low": [], "rig": [], "bay": []}
        prop = f"{PROP.get(rig_size, '10MN')} Afterburner II"

        def fill(slot, names, count):
            for name in names:
                if name and len(fit[slot]) < count:
                    fit[slot].append((name, None))

        if role == "turret":
            kind = self._turret_kind(ship_id)
            turret, ammo = TURRETS[kind].get(rig_size, TURRETS[kind][2])
            fit["high"] = [(turret, ammo)] * min(turrets, hi)
            fit["bay"].append((ammo, 1000))
            if self.data.attr(ship_id, ATTR_BANDWIDTH, 0) >= 25:
                fit["bay"] = self._drones(ship_id) + fit["bay"]
            damage_mod = TURRET_DAMAGE_MOD[kind]
            if tank == "shield":
                fill("med", [prop, f"{SHIELD_EXT[size_class]} Shield Extender II", *["Multispectrum Shield Hardener II"] * med], med)
                fill("low", [*[damage_mod] * min(3, max(low - 1, 1)), "Damage Control II", *["Power Diagnostic System II"] * low], low)
                fill("rig", [f"{rig_prefix} Core Defense Field Extender I"] * rig, rig)
            else:
                fill("med", [prop, *["Cap Recharger II"] * med], med)
                fill("low", ["Damage Control II", f"{SIZE.get(rig_size, 'Medium')} Armor Repairer II",
                             *[damage_mod] * min(3, max(low - 3, 1)), *["Multispectrum Energized Membrane II"] * low], low)
                fill("rig", [f"{rig_prefix} Auxiliary Nano Pump I"] * rig, rig)
        elif role == "bomber":
            hull, _ = self.calc._hull_bonuses(ship_id, {})
            damage = [k.split(":")[1] for k, v in hull if k.startswith("missile_damage:") and v > 1]
            torpedo = TORPEDO_BY_DAMAGE.get(damage[0], "Scourge Torpedo") if damage else "Scourge Torpedo"
            fit["high"] = [("Torpedo Launcher II", torpedo)] * min(launchers, hi - 1) + [(self._cloak(ship_id), None)]
            fit["bay"].append((torpedo, 300))
            fill("med", [f"{PROP.get(rig_size, '1MN').replace('1MN', '5MN').replace('10MN', '50MN')} Microwarpdrive II",
                         "Target Painter II", "Sensor Booster II", *["Cap Recharger II"] * med], med)
            fill("low", ["Ballistic Control System II"] * low, low)
        elif role == "exploration":
            fit["high"] = [("Core Probe Launcher II", None), (self._cloak(ship_id), None)][:hi]
            fill("med", [prop, "Data Analyzer II", "Relic Analyzer II", *["Cap Recharger II"] * med], med)
            fill("low", ["Inertial Stabilizers II", *["Damage Control II"] * low], low)
            fill("rig", [f"{rig_prefix} Memetic Algorithm Bank I", f"{rig_prefix} Emission Scope Sharpener I",
                         f"{rig_prefix} Gravity Capacitor Upgrade I"][:rig], rig)
            if self.data.attr(ship_id, ATTR_BANDWIDTH, 0) >= 25:
                fit["bay"] = self._drones(ship_id)
        elif role == "salvage":
            salvagers = (hi + 1) // 2
            fit["high"] = [("Salvager II", None)] * salvagers + [("Small Tractor Beam I", None)] * (hi - salvagers)
            fill("med", [prop, *["Cap Recharger II"] * med], med)
            fill("low", ["Expanded Cargohold II"] * low, low)
            fill("rig", [f"{rig_prefix} Salvage Tackle I"] * rig, rig)
        elif role == "drone_mining":
            bandwidth = self.data.attr(ship_id, ATTR_BANDWIDTH, 0)
            count = int(min(5, bandwidth // 5))
            fit["bay"] = [("Mining Drone II", count)] if count else []
            fit["bay"] += [(n, q) for n, q in self._drones(ship_id) if n == "Hobgoblin II"][:1]
            fill("med", [prop, "Drone Navigation Computer II", *["Cap Recharger II"] * med], med)
            fill("low", ["Damage Control II", f"{SIZE.get(rig_size, 'Medium')} Armor Repairer II",
                         *["Multispectrum Energized Membrane II"] * low], low)
            fill("rig", [f"{rig_prefix} Drone Mining Augmentor I"] * rig, rig)
        elif role == "special_hauler":
            fill("med", [prop, f"{SHIELD_EXT.get(size_class, 'Medium')} Shield Extender II",
                         *["Multispectrum Shield Hardener II"] * med], med)
            fill("low", ["Inertial Stabilizers II", "Damage Control II", *["Inertial Stabilizers II"] * low], low)
        elif role in ("drone", "missile"):
            if role == "missile" and launchers:
                launcher, charge = self._launcher(ship_id, size_class)
                if launcher:
                    fit["high"] = [(launcher, charge)] * min(launchers, hi)
                    if charge:
                        fit["bay"].append((charge, 1000))
            if role == "drone" or self.data.attr(ship_id, ATTR_BANDWIDTH, 0) >= 25:
                fit["bay"] = self._drones(ship_id) + fit["bay"]
            damage_mod = "Drone Damage Amplifier II" if role == "drone" else "Ballistic Control System II"
            tracking = ["Omnidirectional Tracking Link II"] if role == "drone" else []
            if tank == "shield":
                fill("med", [prop, f"{SHIELD_EXT[size_class]} Shield Extender II", *tracking,
                             *["Multispectrum Shield Hardener II"] * med], med)
                # 同じモジュールは重ねるほど効きが落ちるので、ダメージ強化は 3 個まで。余りは PG を増やすモジュール
                fill("low", [*[damage_mod] * min(3, max(low - 1, 1)), "Damage Control II",
                             *["Power Diagnostic System II"] * low], low)
                fill("rig", [f"{rig_prefix} Core Defense Field Extender I"] * rig, rig)
            else:
                fill("med", [prop, *tracking, *["Cap Recharger II"] * med], med)
                fill("low", ["Damage Control II", f"{SIZE.get(rig_size, 'Medium')} Armor Repairer II",
                             *[damage_mod] * min(3, max(low - 3, 1)), *["Multispectrum Energized Membrane II"] * low], low)
                fill("rig", [f"{rig_prefix} Auxiliary Nano Pump I"] * rig, rig)
        elif role == "hauler":
            fill("med", [prop, f"{SHIELD_EXT.get(size_class, 'Medium')} Shield Extender II",
                         *["Multispectrum Shield Hardener II"] * med], med)
            fill("low", ["Expanded Cargohold II"] * low, low)
            fill("rig", [f"{rig_prefix} Cargohold Optimization I"] * rig, rig)
        elif role in ("mining_ore", "mining_gas", "mining_ice"):
            barge = ship_group in ("Mining Barge", "Exhumer")
            if role == "mining_ice":
                # 採掘船・採掘専用艦はアイス・ハーベスター、それ以外は氷用の採掘レーザー
                tool = "Ice Harvester II" if barge else "Ice Mining Laser II"
                charge = None
                count = turrets or 1
            elif role == "mining_ore":
                if ship_group == "Exhumer":
                    tool, charge = "Modulated Strip Miner II", "Simple Asteroid Mining Crystal Type A II"
                elif barge:
                    tool, charge = "Strip Miner I", None
                else:
                    tool, charge = "Miner II", None
                count = turrets or min(hi, 2)
            else:
                tool = next((t for t in ("Gas Cloud Harvester II", "Gas Cloud Harvester I", "Gas Cloud Scoop II")
                             if self._can_fit(t, ship_id)), "Gas Cloud Scoop II")
                charge = None
                count = min(hi, 2)
            if self._can_fit(tool, ship_id):
                count = self._max_fitted(tool, count)
                fit["high"] = [(tool, charge)] * count
            fill("med", [prop, f"{SHIELD_EXT.get(size_class, 'Medium')} Shield Extender II",
                         *["Multispectrum Shield Hardener II"] * med], med)
            upgrades = {"mining_ore": ["Mining Laser Upgrade II"] * min(2, low),
                        "mining_ice": ["Ice Harvester Upgrade II"] * min(2, low)}.get(role, [])
            fill("low", [*upgrades, "Damage Control II", *["Inertial Stabilizers II"] * low], low)
        return fit

    def to_eft(self, ship_name, fit_name, fit):
        lines = [f"[{ship_name}, {fit_name}]"]
        for slot in ("low", "med", "high", "rig"):
            for name, charge in fit[slot]:
                lines.append(f"{name}, {charge}" if charge else name)
            lines.append("")
        lines.append("")
        lines += [f"{n} x{q}" for n, q in fit["bay"]]
        return "\n".join(lines).strip() + "\n"

    def _fits(self, ship_id, fit):
        """全スキル V で PG・CPU・キャリブレーションが収まるか。"""
        names = [n for s in ("low", "med", "high", "rig") for n, _ in fit[s]]
        ids = [self.catalog.find_by_name(n) for n in names]
        if not all(ids):
            return None
        return fitting.check_resources(self.data, self.type_cache, ship_id, ids, self.all_v())

    def shrink(self, ship_id, fit):
        """収まるまで、優先度の低いモジュール（リグは後ろから）を外す。"""
        # 実在しない名前は先に外す（T2 が無いなど）
        for slot in ("low", "med", "high", "rig"):
            fit[slot] = [(n, c) for n, c in fit[slot] if self._exists(n)]
        for _ in range(40):
            r = self._fits(ship_id, fit)
            if r is None or r["ok"]:
                return fit
            if not r["calibration"]["ok"] and fit["rig"]:
                fit["rig"].pop()
                continue
            removed = False
            for word in REMOVE_ORDER:
                for slot in ("med", "low"):
                    idx = next((i for i in range(len(fit[slot]) - 1, -1, -1) if word in fit[slot][i][0]), None)
                    if idx is not None and len(fit[slot]) > 1:
                        fit[slot].pop(idx)
                        removed = True
                        break
                if removed:
                    break
            if not removed:
                if len(fit["high"]) > 1:
                    fit["high"].pop()
                else:
                    return fit
        return fit

    def make(self, ship_id, ship_name, role, size_class, ship_group, role_label):
        fit = self.shrink(ship_id, self.build(ship_id, role, size_class, ship_group))
        if (role.startswith("mining") or role in ("turret", "bomber", "salvage")) and not fit["high"]:
            return None  # 採掘モジュールを装着できない艦
        return self.to_eft(ship_name, tr("自動 {0} {1}", ship_name, role_label), fit)
