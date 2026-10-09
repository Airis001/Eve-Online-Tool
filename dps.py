"""フィットの DPS の目安（ドローン・ミサイルのみ）。

計算に入れるもの:
  ミサイル: 弾薬のダメージ × スキル（Warhead Upgrades・各ミサイルのスキル）× BCS × 艦ボーナス
            ÷ 発射間隔（ランチャー × Missile Launcher Operation・Rapid Launch・専門スキル × BCS・リグ × 艦ボーナス）
  ドローン: ドローンのダメージ × ダメージ倍率 × スキル（Drone Interfacing・各サイズ・専門スキル）× DDA × 艦ボーナス
            ÷ 発射間隔。帯域と出せる数（Drones スキル）の範囲で、DPS が最大になるドローンを選ぶ
  タレット: 弾のダメージ × タレットのダメージ倍率 × スキル（Surgical Strike・各サイズ・専門スキル）× ダメージ強化モジュール × 艦ボーナス
            ÷ 発射間隔（タレット × Gunnery・Rapid Firing × ダメージ強化モジュール × 艦ボーナス）
あわせて、ドローン採掘の採掘量・探査（ハッキングの強さ・プローブの強さ）・サルベージの指標も出す。
計算に入れないもの: 弾薬の装填時間、命中（爆発半径・追尾・射程）、相手の耐性、オーバーヒート
スキルの効果量は ESI のスキルの属性値（1 レベルあたり）を使う。
"""

import math
import re

ATTR_SPEED = 51                 # 発射間隔（ミリ秒）
ATTR_DAMAGE_MULTIPLIER = 64     # ドローンのダメージ倍率
DAMAGE_ATTRS = {114: "em", 118: "thermal", 117: "kinetic", 116: "explosive"}
ATTR_DAMAGE_BONUS = 292         # スキル: damageMultiplierBonus（1 レベルあたり %）
ATTR_ROF_BONUS = 293            # スキル: rofBonus（1 レベルあたり %）
ATTR_MISSILE_DAMAGE_MULT = 213  # BCS: missileDamageMultiplierBonus
ATTR_SPEED_MULTIPLIER = 204     # BCS・リグ: speedMultiplier（発射間隔）
ATTR_DRONE_DAMAGE_BONUS = 1255  # DDA: droneDamageBonus（%）
ATTR_BANDWIDTH = 1271           # 艦のドローン帯域
ATTR_BANDWIDTH_USED = 1272      # ドローンが使う帯域
CHARGE_GROUP_ATTRS = (604, 605, 606, 609, 610)

SKILL_MISSILE_LAUNCHER_OPERATION = 3319
SKILL_RAPID_LAUNCH = 21071
SKILL_WARHEAD_UPGRADES = 20315
SKILL_DRONES = 3436
SKILL_DRONE_INTERFACING = 3442
SKILL_GUNNERY = 3300
SKILL_RAPID_FIRING = 3310
SKILL_SURGICAL_STRIKE = 3315
SKILL_MINING_DRONE_OPERATION = 3438
SKILL_SALVAGING = 25863

ATTR_TURRET_SPEED_BONUS = 441   # Gunnery: turretSpeeBonus（1 レベルあたり %）
ATTR_CHARGE_SIZE = 128
ATTR_MINING_AMOUNT = 77         # 採掘ドローンの 1 回の採掘量（m³）
ATTR_DURATION = 73              # 作業時間（ミリ秒）
ATTR_MINING_AMOUNT_BONUS = 434  # スキル: miningAmountBonus（1 レベルあたり %）
ATTR_ICE_CYCLE_BONUS = 780      # iceHarvestCycleBonus（Ice Harvesting・アップグレード・リグ）
GAS_HARVESTER_GROUPS = {737, 4138}  # ガスクラウドスクープ・ガスクラウドハーベスター
SKILL_MINING, SKILL_ASTROGEOLOGY, SKILL_ICE_HARVESTING = 3386, 3410, 16281
# 採掘艦のボーナス属性名の頭 → 1 レベルごとに増やすスキル
MINING_HULL_SKILLS = {"miningBarge": 17940, "exhumers": 22551, "miningFrigate": 32918, "expeditionFrigate": 33856,
                      "industrialCommand": 29637, "capitalIndustrial": 28374}
ATTR_VIRUS_STRENGTH = 1910      # アナライザーのハッキングの強さ
ATTR_VIRUS_STRENGTH_BONUS = 1918  # 艦のハッキングの強さボーナス（加算）
ATTR_SCAN_STRENGTH_BONUS = 846  # プローブランチャーのプローブ強度ボーナス（%）
ATTR_ACCESS_DIFFICULTY_BONUS = 902  # サルベージャーの成功率ボーナス

# タレットのグループ → 種類、ダメージ強化モジュールのグループ → 対象のタレットのグループ
TURRET_GROUPS = {53: "レーザー", 55: "プロジェクタイル", 74: "ハイブリッド"}
TURRET_DAMAGE_MOD_GROUPS = {302: 74, 59: 55, 205: 53}  # Magnetic Field Stabilizer / Gyrostabilizer / Heat Sink
TURRET_WORDS = re.compile(r"Hybrid|Projectile|Laser|Energy|Turret|Blaster|Railgun|AutoCannon|Autocannon|Artillery|Pulse|Beam|HT|PT|ET")

# ミサイルランチャーのグループ（爆弾は除く）
MISSILE_LAUNCHER_GROUPS = {506, 507, 508, 509, 510, 511, 524, 771, 1245, 1673, 1674}
BCS_GROUP = 367
MISSILE_RIG_ROF_GROUPS = {779}  # Rig Launcher（Bay Loading Accelerator など）

# 艦ボーナスの属性名 → 艦種スキル。shipBonus<勢力><艦種><番号>、eliteBonus<T2 艦種><番号>
HULL_SKILLS = {
    ("A", "F"): 3331, ("A", "D"): 33091, ("A", "C"): 3335, ("A", "BC"): 33095, ("A", "B"): 3339, ("A", "I"): 3343,
    ("C", "F"): 3330, ("C", "D"): 33092, ("C", "C"): 3334, ("C", "BC"): 33096, ("C", "B"): 3338, ("C", "I"): 3342,
    ("G", "F"): 3328, ("G", "D"): 33093, ("G", "C"): 3332, ("G", "BC"): 33097, ("G", "B"): 3336, ("G", "I"): 3340,
    ("M", "F"): 3329, ("M", "D"): 33094, ("M", "C"): 3333, ("M", "BC"): 33098, ("M", "B"): 3337, ("M", "I"): 3341,
}
ELITE_SKILLS = {"HeavyGunship": 16591, "Gunship": 12095, "CommandShip": 23950, "Violator": 28667, "BlackOps": 28656,
                "CovertOps": 12093, "CoverOps": 12093}
HULL_RE = re.compile(r"^shipBonus2?([ACGM])(BC|F|D|C|B|I)\d*$")
ELITE_RE = re.compile(r"^eliteBonus(HeavyGunship|Gunship|CommandShip|Violator|BlackOps|CovertOps|CoverOps)s?\d*$")
ROLE_RE = re.compile(r"^(shipBonusRole|roleBonus|shipRoleBonus|industrialBonus)")  # レベルで変わらない固定ボーナス
MISSILE_WORDS = re.compile(r"(?i)missile|launcher|rocket|torpedo|cruise|rhml|siege")
DRONE_SIZE_WORDS = {"Light": "Light Drone Operation", "Medium": "Medium Drone Operation",
                    "Heavy": "Heavy Drone Operation", "Sentry": "Sentry Drone Interfacing"}


def stacking(values):
    """スタックペナルティ付きで倍率を掛け合わせる。values: 倍率（1.1 = +10%）"""
    result = 1.0
    stronger_first = sorted(values, key=lambda v: -abs(v - 1))
    for i, v in enumerate(stronger_first):
        result *= 1 + (v - 1) * math.exp(-((i / 2.67) ** 2))
    return result


ATTR_DRONE_BANDWIDTH_PERCENT = 3124


class DpsCalculator:
    def __init__(self, data, type_cache):
        self.data = data            # fitting.FittingData
        self.type_cache = type_cache

    # ---------- 共通 ----------

    def _requirement_names(self, type_id):
        return {self.type_cache.get(s)["name"]: s for s, _ in self.type_cache.get(type_id)["requirements"]}

    def _skill_bonus(self, skill_id, attr_id, levels):
        """スキル 1 つ分の倍率（1 + 値% × レベル）。"""
        return 1 + self.data.attr(skill_id, attr_id, 0) * levels.get(skill_id, 0) / 100

    def _bonus_skill(self, ship_type_id, name):
        """艦ボーナスの属性名 → 1 レベルごとに増やすスキル。固定ボーナスなら None。

        名前から判別できないときは、艦の最初の必要スキル（艦種スキル）とみなす。
        """
        if ROLE_RE.match(name):
            return None
        if m := HULL_RE.match(name):
            return HULL_SKILLS.get((m.group(1), m.group(2)))
        if m := ELITE_RE.match(name):
            return ELITE_SKILLS.get(m.group(1))
        reqs = self.type_cache.get(ship_type_id)["requirements"]
        return reqs[0][0] if reqs else None

    def _hull_bonuses(self, ship_type_id, levels):
        """艦ボーナスのうち、DPS・採掘・探査・サルベージの指標に効くもの。

        戻り値: [(種類, 倍率)]。種類: "missile_damage:<型>" / "missile_rof" / "drone_damage:<サイズ or *>" /
        "turret_damage" / "turret_rof" / "drone_mining" / "probe_strength" / "salvage_cycle"
        """
        bonuses = []
        unknown = []
        seen = set()  # 同じボーナス属性が、弾の種類ごとの別の効果として複数登録されている（重ねて掛けない）
        for effect in self.data.type_effects(ship_type_id):
            if effect["category"] not in (0, 4):
                continue
            for mod in effect["modifiers"]:
                attr, by = mod["attr"], mod["by"]
                if by is None:
                    continue
                kind = None
                if attr in DAMAGE_ATTRS and MISSILE_WORDS.search(effect["name"]):
                    kind = f"missile_damage:{DAMAGE_ATTRS[attr]}"
                elif attr == ATTR_SPEED and MISSILE_WORDS.search(effect["name"]):
                    kind = "missile_rof"
                elif attr == ATTR_DAMAGE_MULTIPLIER and "Drone" in effect["name"] and mod["func"] == "OwnerRequiredSkillModifier":
                    size = next((w for w in DRONE_SIZE_WORDS if w in effect["name"]), "*")
                    kind = f"drone_damage:{size}"
                elif attr in (ATTR_DAMAGE_MULTIPLIER, ATTR_SPEED) and TURRET_WORDS.search(effect["name"]) \
                        and "Drone" not in effect["name"] and not MISSILE_WORDS.search(effect["name"]) \
                        and mod["func"] in ("LocationRequiredSkillModifier", "LocationGroupModifier"):
                    kind = "turret_damage" if attr == ATTR_DAMAGE_MULTIPLIER else "turret_rof"
                elif attr == ATTR_MINING_AMOUNT and "Drone" in effect["name"]:
                    kind = "drone_mining"
                elif attr == ATTR_DURATION and "Salvage" in effect["name"]:
                    kind = "salvage_cycle"
                elif self.data.attr_name(attr) == "baseSensorStrength":
                    kind = "probe_strength"
                if not kind or (kind, by) in seen:
                    continue
                seen.add((kind, by))
                value = self.data.attr(ship_type_id, by, 0)
                per_level_skill = self._bonus_skill(ship_type_id, self.data.attr_name(by))
                percent = value * levels.get(per_level_skill, 0) if per_level_skill else value
                bonuses.append((kind, 1 + percent / 100))
        return bonuses, unknown

    # ---------- ミサイル ----------

    def _best_charge(self, launcher_id, candidates):
        groups = {int(self.data.attr(launcher_id, a, 0)) for a in CHARGE_GROUP_ATTRS} - {0}
        size = self.data.attr(launcher_id, ATTR_CHARGE_SIZE, 0)
        usable = [c for c in candidates if self.data.types[c]["group_id"] in groups
                  and (not size or not self.data.attr(c, ATTR_CHARGE_SIZE, 0) or self.data.attr(c, ATTR_CHARGE_SIZE, 0) == size)]
        return max(usable, key=lambda c: sum(self.data.attr(c, a, 0) for a in DAMAGE_ATTRS), default=None)

    def missile_dps(self, ship_type_id, fitted, loaded, bay_charges, levels, hull):
        launchers = [t for t in fitted if self.data.types[t]["group_id"] in MISSILE_LAUNCHER_GROUPS]
        if not launchers:
            return 0.0, []
        notes = []
        bcs = [m for m in fitted if self.data.types[m]["group_id"] == BCS_GROUP]
        dmg_mods = stacking([self.data.attr(m, ATTR_MISSILE_DAMAGE_MULT, 1) for m in bcs])
        rof_mods = stacking([self.data.attr(m, ATTR_SPEED_MULTIPLIER, 1) for m in fitted
                             if self.data.types[m]["group_id"] in {BCS_GROUP} | MISSILE_RIG_ROF_GROUPS])
        hull_rof = math.prod(v for k, v in hull if k == "missile_rof")
        base_rof = (self._skill_bonus(SKILL_MISSILE_LAUNCHER_OPERATION, ATTR_ROF_BONUS, levels)
                    * self._skill_bonus(SKILL_RAPID_LAUNCH, ATTR_ROF_BONUS, levels))
        warhead = self._skill_bonus(SKILL_WARHEAD_UPGRADES, ATTR_DAMAGE_BONUS, levels)

        total = 0.0
        loaded = list(loaded) + [None] * (len(fitted) - len(loaded))  # fitted と同じ並び
        for launcher, charge in zip(fitted, loaded):
            if self.data.types[launcher]["group_id"] not in MISSILE_LAUNCHER_GROUPS:
                continue
            if charge is None or self._best_charge(launcher, [charge]) is None:
                charge = self._best_charge(launcher, bay_charges + [c for c in loaded if c])
            if charge is None:
                notes.append("弾薬の指定が無いランチャーがあります")
                continue
            # 弾薬の必要スキル（Heavy Missiles など）のダメージボーナス
            size_skill = math.prod(self._skill_bonus(s, ATTR_DAMAGE_BONUS, levels)
                                   for s in self._requirement_names(charge).values()
                                   if self.data.attr(s, ATTR_DAMAGE_BONUS, 0))
            damage = 0.0
            for attr, dtype in DAMAGE_ATTRS.items():
                hull_dmg = math.prod(v for k, v in hull if k == f"missile_damage:{dtype}")
                damage += self.data.attr(charge, attr, 0) * hull_dmg
            damage *= warhead * size_skill * dmg_mods
            # ランチャーの必要スキルのうち発射間隔ボーナスがあるもの（専門スキル）
            spec = math.prod(self._skill_bonus(s, ATTR_ROF_BONUS, levels)
                             for s in self._requirement_names(launcher).values()
                             if s not in (SKILL_MISSILE_LAUNCHER_OPERATION, SKILL_RAPID_LAUNCH)
                             and self.data.attr(s, ATTR_ROF_BONUS, 0))
            rof = self.data.attr(launcher, ATTR_SPEED, 0) / 1000 * base_rof * spec * rof_mods * hull_rof
            if rof > 0:
                total += damage / rof
        return total, notes

    # ---------- ドローン ----------

    def drone_dps(self, ship_type_id, fitted, bay, levels, hull):
        drones = [(t, q) for t, q in bay if self.data.attr(t, ATTR_DAMAGE_MULTIPLIER, 0) and self.data.attr(t, ATTR_BANDWIDTH_USED, 0)]
        if not drones:
            return 0.0, [], []
        max_count = min(levels.get(SKILL_DRONES, 0), 5)  # Drones スキル 1 レベルにつき 1 機（最大 5 機）
        bandwidth = self.data.attr(ship_type_id, ATTR_BANDWIDTH, 0)
        for m in fitted:  # ワープコアスタビライザーなどの帯域の減少（-50%）
            bandwidth *= 1 + self.data.attr(m, ATTR_DRONE_BANDWIDTH_PERCENT, 0) / 100
        dda = stacking([1 + self.data.attr(m, ATTR_DRONE_DAMAGE_BONUS, 0) / 100 for m in fitted
                        if self.data.attr(m, ATTR_DRONE_DAMAGE_BONUS, 0)])
        interfacing = self._skill_bonus(SKILL_DRONE_INTERFACING, ATTR_DAMAGE_BONUS, levels)

        def one(t):
            reqs = self._requirement_names(t)
            skills = math.prod(self._skill_bonus(s, ATTR_DAMAGE_BONUS, levels) for s in reqs.values()
                               if s != SKILL_DRONE_INTERFACING and self.data.attr(s, ATTR_DAMAGE_BONUS, 0))
            size = next((w for w, skill_name in DRONE_SIZE_WORDS.items() if skill_name in reqs), None)
            hull_mult = math.prod(v for k, v in hull if k in ("drone_damage:*", f"drone_damage:{size}"))
            damage = sum(self.data.attr(t, a, 0) for a in DAMAGE_ATTRS)
            damage *= self.data.attr(t, ATTR_DAMAGE_MULTIPLIER, 1) * interfacing * skills * dda * hull_mult
            rof = self.data.attr(t, ATTR_SPEED, 0) / 1000
            return damage / rof if rof else 0.0

        units = sorted(((one(t), t) for t, q in drones for _ in range(int(q))), reverse=True)
        chosen, used = [], 0.0
        for d, t in units:
            if len(chosen) >= max_count:
                break
            need = self.data.attr(t, ATTR_BANDWIDTH_USED, 0)
            if used + need <= bandwidth + 1e-6:
                chosen.append((d, t))
                used += need
        notes = [] if max_count else ["Drones スキルが無いため、ドローンを出せません"]
        return sum(d for d, _ in chosen), [t for _, t in chosen], notes

    # ---------- タレット ----------

    def turret_dps(self, ship_type_id, fitted, loaded, bay_charges, levels, hull):
        turrets = [(t, c) for t, c in zip(fitted, list(loaded) + [None] * len(fitted))
                   if self.data.types[t]["group_id"] in TURRET_GROUPS]
        if not turrets:
            return 0.0, []
        notes = []
        surgical = self._skill_bonus(SKILL_SURGICAL_STRIKE, ATTR_DAMAGE_BONUS, levels)
        base_rof = (self._skill_bonus(SKILL_GUNNERY, ATTR_TURRET_SPEED_BONUS, levels)
                    * self._skill_bonus(SKILL_RAPID_FIRING, ATTR_ROF_BONUS, levels))
        hull_dmg = math.prod(v for k, v in hull if k == "turret_damage")
        hull_rof = math.prod(v for k, v in hull if k == "turret_rof")
        total = 0.0
        for turret, charge in turrets:
            group = self.data.types[turret]["group_id"]
            mods = [m for m in fitted if TURRET_DAMAGE_MOD_GROUPS.get(self.data.types[m]["group_id"]) == group]
            dmg_mods = stacking([self.data.attr(m, ATTR_DAMAGE_MULTIPLIER, 1) for m in mods])
            rof_mods = stacking([self.data.attr(m, ATTR_SPEED_MULTIPLIER, 1) for m in mods])
            if charge is None or self._best_charge(turret, [charge]) is None:
                charge = self._best_charge(turret, bay_charges + [c for c in loaded if c])
            if charge is None:
                notes.append("弾の指定が無いタレットがあります")
                continue
            skills = math.prod(self._skill_bonus(s, ATTR_DAMAGE_BONUS, levels)
                               for s in self._requirement_names(turret).values()
                               if s != SKILL_SURGICAL_STRIKE and self.data.attr(s, ATTR_DAMAGE_BONUS, 0))
            damage = sum(self.data.attr(charge, a, 0) for a in DAMAGE_ATTRS)
            damage *= self.data.attr(turret, ATTR_DAMAGE_MULTIPLIER, 1) * surgical * skills * dmg_mods * hull_dmg
            rof = self.data.attr(turret, ATTR_SPEED, 0) / 1000 * base_rof * rof_mods * hull_rof
            if rof > 0:
                total += damage / rof
        return total, notes

    # ---------- ドローン採掘・探査・サルベージ ----------

    def drone_mining(self, ship_type_id, bay, levels, hull):
        """採掘ドローンの 1 分あたりの採掘量（m³）。帯域と出せる数の範囲で、量が最大になるドローンを選ぶ。"""
        drones = [(t, q) for t, q in bay if self.data.attr(t, ATTR_MINING_AMOUNT, 0) and self.data.attr(t, ATTR_BANDWIDTH_USED, 0)]
        if not drones:
            return 0.0
        max_count = min(levels.get(SKILL_DRONES, 0), 5)
        bandwidth = self.data.attr(ship_type_id, ATTR_BANDWIDTH, 0)
        hull_mult = math.prod(v for k, v in hull if k == "drone_mining")
        common = (self._skill_bonus(SKILL_DRONE_INTERFACING, ATTR_MINING_AMOUNT_BONUS, levels)
                  * self._skill_bonus(SKILL_MINING_DRONE_OPERATION, ATTR_MINING_AMOUNT_BONUS, levels))

        def one(t):
            spec = math.prod(self._skill_bonus(s, ATTR_MINING_AMOUNT_BONUS, levels) for s in self._requirement_names(t).values()
                             if s not in (SKILL_DRONE_INTERFACING, SKILL_MINING_DRONE_OPERATION)
                             and self.data.attr(s, ATTR_MINING_AMOUNT_BONUS, 0))
            minutes = self.data.attr(t, ATTR_DURATION, 60000) / 60000
            return self.data.attr(t, ATTR_MINING_AMOUNT, 0) * common * spec * hull_mult / minutes

        units = sorted(((one(t), t) for t, q in drones for _ in range(int(q))), reverse=True)
        total, used, count = 0.0, 0.0, 0
        for amount, t in units:
            if count >= max_count:
                break
            need = self.data.attr(t, ATTR_BANDWIDTH_USED, 0)
            if used + need <= bandwidth + 1e-6:
                total += amount
                used += need
                count += 1
        return total

    def module_mining(self, ship_type_id, fitted, levels):
        """採掘モジュール（採掘レーザー・ストリップマイナー・氷・ガス）の 1 秒あたりの採掘量（m³）。種類ごと。

        反映するもの: 艦ボーナス（採掘量・サイクル時間。鉱石・氷・ガスを属性名で判別）、Mining・Astrogeology（鉱石）、
        Ice Harvesting とアイスハーベスターのアップグレード・リグ（氷）、採掘レーザーのアップグレード（鉱石）。
        含めないもの: 採掘クリスタル、クリティカル（大当たり）・残渣（取りこぼし）、艦隊のブースト。
        """
        mods = [m for m in fitted if self.data.attr(m, ATTR_MINING_AMOUNT, 0) and not self.data.attr(m, ATTR_BANDWIDTH_USED, 0)]
        if not mods:
            return None

        def kind_of(m):
            name = self.type_cache.get(m)["name"]
            if self.data.types[m]["group_id"] in GAS_HARVESTER_GROUPS or "Gas" in name:
                return "gas"
            return "ice" if "Ice " in name else "ore"  # Ice Harvester・Ice Mining Laser

        # 艦ボーナス（採掘量・サイクル時間）
        amount = {"ore": 1.0, "ice": 1.0, "gas": 1.0}
        cycle = {"ore": 1.0, "ice": 1.0, "gas": 1.0}
        for effect in self.data.type_effects(ship_type_id):
            for mod in effect["modifiers"]:
                if mod["attr"] not in (ATTR_MINING_AMOUNT, ATTR_DURATION) or not mod["by"]:
                    continue
                by_name = self.data.attr_name(mod["by"])
                if "Drone" in by_name or "Drone" in effect["name"]:
                    continue
                # 種類の語が無いボーナス（Venture の ×2 など）は Mining スキルが必要なモジュール＝鉱石にだけ効く
                kinds = [k for k, word in (("ice", "Ice"), ("gas", "Gas"), ("ore", "Ore")) if word in by_name] or ["ore"]
                value = self.data.attr(ship_type_id, mod["by"], 0)
                if mod["op"] == 4 or by_name == "miningAmountMultiplier":  # 掛け算（固定）
                    factor = value
                else:
                    skill = next((s for prefix, s in MINING_HULL_SKILLS.items() if by_name.startswith(prefix)), None)
                    if skill is None and not ROLE_RE.match(by_name) and not by_name.startswith("shipRole"):
                        skill = self._bonus_skill(ship_type_id, by_name)
                    per_level = skill is not None and not by_name.startswith("shipRole")
                    factor = 1 + value * (levels.get(skill, 0) if per_level else 1) / 100
                for k in kinds:
                    (amount if mod["attr"] == ATTR_MINING_AMOUNT else cycle)[k] *= factor
        # スキル
        self.data.ensure([SKILL_MINING, SKILL_ASTROGEOLOGY, SKILL_ICE_HARVESTING])
        amount["ore"] *= self._skill_bonus(SKILL_MINING, ATTR_MINING_AMOUNT_BONUS, levels)
        amount["ore"] *= self._skill_bonus(SKILL_ASTROGEOLOGY, ATTR_MINING_AMOUNT_BONUS, levels)
        cycle["ice"] *= 1 + self.data.attr(SKILL_ICE_HARVESTING, ATTR_ICE_CYCLE_BONUS, 0) * levels.get(SKILL_ICE_HARVESTING, 0) / 100
        # 強化モジュール・リグ（採掘レーザーのアップグレード・アイスハーベスターのアップグレード / アクセラレーター）
        for m in fitted:
            if m in mods:
                continue
            if self.data.attr(m, ATTR_MINING_AMOUNT_BONUS, 0):
                amount["ore"] *= 1 + self.data.attr(m, ATTR_MINING_AMOUNT_BONUS, 0) / 100
            if self.data.attr(m, ATTR_ICE_CYCLE_BONUS, 0):
                cycle["ice"] *= 1 + self.data.attr(m, ATTR_ICE_CYCLE_BONUS, 0) / 100
        per_second = {"ore": 0.0, "ice": 0.0, "gas": 0.0}
        for m in mods:
            k = kind_of(m)
            seconds = self.data.attr(m, ATTR_DURATION, 0) / 1000 * cycle[k]
            if seconds > 0:
                per_second[k] += self.data.attr(m, ATTR_MINING_AMOUNT, 0) * amount[k] / seconds
        total = sum(per_second.values())
        return {**{k: round(v, 3) for k, v in per_second.items()}, "total": round(total, 3), "modules": len(mods),
                "per_hour": round(total * 3600)}

    def exploration(self, ship_type_id, fitted, hull):
        """ハッキングの強さ（アナライザー＋艦ボーナス）とプローブの強さのボーナス（%）。"""
        analyzers = [m for m in fitted if self.data.attr(m, ATTR_VIRUS_STRENGTH, 0)]
        virus = max((self.data.attr(m, ATTR_VIRUS_STRENGTH, 0) for m in analyzers), default=0)
        if virus:
            virus += self.data.attr(ship_type_id, ATTR_VIRUS_STRENGTH_BONUS, 0)
        probe = math.prod(v for k, v in hull if k == "probe_strength")
        launcher = max((self.data.attr(m, ATTR_SCAN_STRENGTH_BONUS, 0) for m in fitted), default=0)
        probe *= 1 + launcher / 100
        return {"virus_strength": virus, "analyzers": len(analyzers), "probe_bonus": round((probe - 1) * 100, 1)}

    def salvage(self, ship_type_id, fitted, levels, hull):
        """サルベージャー・トラクタービームの数と、サルベージャー 1 回の作業時間（秒）。"""
        # サルベージ用のリグにも成功率ボーナスの属性があるので、名前でサルベージャーだけを数える
        salvagers = [m for m in fitted if "Salvager" in self.type_cache.get(m)["name"]]
        tractors = [m for m in fitted if "Tractor Beam" in self.type_cache.get(m)["name"]]
        cycle = min((self.data.attr(m, ATTR_DURATION, 0) for m in salvagers), default=0) / 1000
        cycle *= math.prod(v for k, v in hull if k == "salvage_cycle")
        chance = max((self.data.attr(m, ATTR_ACCESS_DIFFICULTY_BONUS, 0) for m in salvagers), default=0)
        return {"salvagers": len(salvagers), "tractors": len(tractors), "cycle": round(cycle, 1),
                "access_bonus": chance + 5 * levels.get(SKILL_SALVAGING, 0) if salvagers else 0}

    # ---------- まとめ ----------

    def compute(self, ship_type_id, fitted, loaded, bay, levels):
        """fitted: 装着モジュール、loaded: ランチャーごとの装填弾薬（None 可）、bay: [(type_id, 個数)]"""
        charge_ids = [c for c in loaded if c]
        bay_ids = [t for t, _ in bay]
        self.data.ensure([ship_type_id, *fitted, *charge_ids, *bay_ids])
        skill_ids = {s for t in {*fitted, *charge_ids, *bay_ids} for s, _ in self.type_cache.get(t)["requirements"]}
        self.data.ensure([*skill_ids, SKILL_MISSILE_LAUNCHER_OPERATION, SKILL_RAPID_LAUNCH, SKILL_WARHEAD_UPGRADES,
                          SKILL_DRONES, SKILL_DRONE_INTERFACING, SKILL_GUNNERY, SKILL_RAPID_FIRING, SKILL_SURGICAL_STRIKE,
                          SKILL_MINING_DRONE_OPERATION])
        hull, unknown = self._hull_bonuses(ship_type_id, levels)
        bay_charges = [t for t in bay_ids if any(self.data.attr(t, a, 0) for a in DAMAGE_ATTRS)
                       and not self.data.attr(t, ATTR_BANDWIDTH_USED, 0)]
        missile, notes = self.missile_dps(ship_type_id, fitted, loaded, bay_charges, levels, hull)
        drone, drones_used, drone_notes = self.drone_dps(ship_type_id, fitted, bay, levels, hull)
        turret, turret_notes = self.turret_dps(ship_type_id, fitted, loaded, bay_charges, levels, hull)
        notes += drone_notes + turret_notes
        if unknown:
            notes.append("一部の艦ボーナスは未反映")
        return {"missile": round(missile, 1), "drone": round(drone, 1), "turret": round(turret, 1),
                "total": round(missile + drone + turret, 1), "drones_used": drones_used,
                "mining_m3_min": round(self.drone_mining(ship_type_id, bay, levels, hull), 1),
                "mining": self.module_mining(ship_type_id, fitted, levels),
                "exploration": self.exploration(ship_type_id, fitted, hull),
                "salvage": self.salvage(ship_type_id, fitted, levels, hull),
                "notes": list(dict.fromkeys(notes))}
