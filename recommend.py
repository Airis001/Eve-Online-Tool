"""キャラクターごとのおすすめフィット・おすすめ艦船。

おすすめフィット:
  候補 = fit_templates.py の定番フィット ＋ このアプリに保存したフィット ＋ ゲーム内のフィット（役割は装備から自動判定）
  「今すぐ使える」「10 日以内の訓練で使える」に分け、戦闘用は DPS の目安、輸送は容量、採掘は格・採掘カーゴで並べる。
  今すぐ使える戦闘用フィットには、10 日以内の訓練で DPS をどれだけ上げられるかも出す。
おすすめ艦船:
  全艦船の艦ボーナス・グループから役割を判定し、今乗れる艦・10 日以内に乗れる艦を艦の格の順に並べる。
"""

import re

import align
import fetch_skills as core
import fit_rules
import pvp_stats
import skill_check
from autofit import REMOVE_ORDER, AutoFitter
from dps import MISSILE_LAUNCHER_GROUPS, SKILL_GUNNERY, SKILL_RAPID_FIRING, SKILL_SURGICAL_STRIKE, TURRET_GROUPS, SKILL_DRONE_INTERFACING, SKILL_DRONES, \
    SKILL_MISSILE_LAUNCHER_OPERATION, SKILL_RAPID_LAUNCH, SKILL_WARHEAD_UPGRADES, DpsCalculator
from fit_templates import PURPOSE, ROLES, TEMPLATES
import fitting
from i18n import tr

SOON_MINUTES = 10 * 24 * 60  # 「10 日以内」
COMBAT_ROLES = ("drone", "missile", "turret", "bomber", "brawler", "kiter")  # DPS で並べる・DPS の強化を出す役割
# T2 の弾（T2 の武器専用）→ T1 版フィットで使う T1 の弾
T2_AMMO_TO_T1 = {"Null": "Antimatter Charge", "Void": "Antimatter Charge", "Barrage": "EMP", "Hail": "EMP",
                 "Scorch": "Multifrequency", "Conflagration": "Multifrequency", "Javelin": "Antimatter Charge",
                 "Spike": "Antimatter Charge", "Quake": "EMP", "Tremor": "EMP", "Aurora": "Multifrequency", "Gleam": "Multifrequency"}


def t1_name(catalog, name):
    """T2 の装備・ドローン・リグ（「… II」）→ T1（「… I」）、T2 の弾 → T1 の弾。T1 が無いものはそのまま（英語名）。"""
    name = name.strip()
    kind, _, size = name.rpartition(" ")
    if kind in T2_AMMO_TO_T1 and size in ("S", "M", "L", "XL"):  # T2 の弾は T2 の武器でしか撃てない
        return f"{T2_AMMO_TO_T1[kind]} {size}"
    if name.endswith(" II") and catalog.find_by_name(name[:-3] + " I"):
        return name[:-3] + " I"
    return name


WARP_SCRAMBLER_GROUP = 52
WEBIFIER_GROUP = 65
# 専用カーゴ（特殊輸送艦）: 属性 ID と、評価結果の holds のキー
SPECIAL_HOLD_ATTRS = {1653: "pi_hold", 1646: "command_center_hold", 1558: "mineral_hold", 3136: "ice_hold",
                      1557: "gas_hold", 1573: "ammo_hold", 908: "ship_maintenance_bay"}
ATTR_TURRET_SLOTS = 102
ATTR_VIRUS_STRENGTH_BONUS = 1918

def bill_of_materials(cand):
    """購入費の計算用の部品表 [[type_id, 個数, 種類]]。種類: ship / module / bay（ドローン・カーゴ）"""
    counts = {}
    for type_id, qty, kind in [(cand["ship_type_id"], 1, "ship"), *((t, 1, "module") for t in cand["fitted"]),
                               *((t, q, "bay") for t, q in cand["bay"])]:
        counts[(type_id, kind)] = counts.get((type_id, kind), 0) + qty
    return [[type_id, qty, kind] for (type_id, kind), qty in counts.items()]


def special_hold_total(e):
    return sum(v["total"] for k, v in e["holds"].items() if k in SPECIAL_HOLD_ATTRS.values() or k == "mining_hold")


def fit_sort_key(e):
    """役割ごとの「良さ」の順（小さいほど上）。"""
    role = e["role"]
    if role in COMBAT_ROLES:
        return (-e["dps"]["total"],)
    if role == "tackle":  # 速いほど上
        sp = (e.get("pvp") or {}).get("speed") or {}
        return (-(sp.get("prop") or sp.get("base") or 0),)
    if role == "logistics":  # 回復量が多いほど上
        r = (e.get("pvp") or {}).get("reps") or {}
        return (-(r.get("armor", 0) + r.get("shield", 0)),)
    if role == "hauler":
        return (-(e["holds"].get("cargo") or {}).get("total", 0),)
    if role == "special_hauler":
        return (-special_hold_total(e),)
    if role == "drone_mining":
        return (-e["dps"]["mining_m3_min"],)
    if role == "exploration":
        x = e["dps"]["exploration"]
        return (-x["virus_strength"], -x["probe_bonus"])
    if role == "salvage":
        x = e["dps"]["salvage"]
        return (-x["salvagers"], -x["tractors"], x["cycle"])
    # 採掘: 1 秒あたりの採掘量が多い順（同じなら格・採掘カーゴ）
    return (-((e["dps"].get("mining") or {}).get("total") or 0), -e["tier"], -(e["holds"].get("mining_hold") or {}).get("total", 0))


# 艦のグループ → 艦の大きさ（並び順に使う）
SHIP_CLASS = {
    "Frigate": 1, "Assault Frigate": 1, "Interceptor": 1, "Covert Ops": 1, "Stealth Bomber": 1,
    "Electronic Attack Ship": 1, "Expedition Frigate": 1, "Logistics Frigate": 1,
    "Destroyer": 2, "Interdictor": 2, "Command Destroyer": 2, "Tactical Destroyer": 2,
    "Cruiser": 3, "Heavy Assault Cruiser": 3, "Force Recon Ship": 3, "Combat Recon Ship": 3, "Logistics": 3,
    "Heavy Interdiction Cruiser": 3, "Strategic Cruiser": 3, "Flag Cruiser": 3,
    "Combat Battlecruiser": 4, "Attack Battlecruiser": 4, "Command Ship": 4,
    "Battleship": 5, "Marauder": 5, "Black Ops": 5,
    "Hauler": 2, "Blockade Runner": 3, "Deep Space Transport": 3,
    "Mining Barge": 3, "Exhumer": 4, "Industrial Command Ship": 5, "Expedition Command Ship": 5,
    "Freighter": 6, "Jump Freighter": 7,
}
HAULER_GROUPS = {"Hauler", "Blockade Runner", "Deep Space Transport", "Freighter", "Jump Freighter"}
MINING_GROUPS = {"Mining Barge", "Exhumer", "Expedition Frigate"}
ORE_EFFECT_RE = re.compile(r"OreMiningYield|OreDestroyer")          # ドローン採掘・採掘支援艦は含めない
GAS_EFFECT_RE = re.compile(r"GasHarvesting|GasCloudHarvesting|GasCloudDuration")
# 氷: 氷採掘の時間・距離・量のボーナス（ドローンでの氷採掘の支援艦・氷の輸送艦は含めない）
ICE_EFFECT_RE = re.compile(r"IceHarvesting(Duration|Range|ActivationCost)|IceMining")
ICE_MODULE_WORDS = ("Ice Harvester", "Ice Mining Laser")  # 「Ice Harvester Upgrade」は強化モジュールなので除く
MIN_DRONE_BANDWIDTH = 25  # これ未満の艦はドローン艦として扱わない
GAS_MODULE_GROUPS = {"Gas Cloud Scoops", "Gas Cloud Harvesters"}
ORE_MODULE_GROUPS = {"Mining Laser", "Strip Miner", "Frequency Mining Laser"}
ATTR_TECH_LEVEL = 422
ATTR_META_LEVEL = 633
ATTR_LAUNCHER_SLOTS = 101


class Recommender:
    def __init__(self, type_cache, catalog, fitting_data, resolve_eft):
        self.type_cache = type_cache
        self.catalog = catalog
        self.data = fitting_data
        self.calc = DpsCalculator(fitting_data, type_cache)
        self.resolve_eft = resolve_eft
        self._templates = None
        self._all_v = None
        self.autofitter = AutoFitter(fitting_data, type_cache, catalog, self.calc, self.all_v_character)

    def all_v_character(self):
        """全スキル V のキャラクター（自動で組むフィットが PG・CPU に収まるかの確認用）。"""
        if self._all_v is None:
            skills = core.load_skill_catalog()
            self._all_v = {"skills": [{"skill_id": sid, "trained_level": 5, "skillpoints": 10_000_000} for sid in skills],
                           "skill_queue": [], "attributes": {}}
        return self._all_v

    # ---------- 候補 ----------

    def _from_eft(self, eft, role, source, key, tier=0):
        fit = self.resolve_eft(eft)
        parsed = skill_check.parse_eft(eft)
        ids = {name: self.catalog.find_by_name(name) for name in parsed["items"]}
        loaded = [ids.get(c) if c else None for c, name in zip(parsed["loaded"], parsed["fitted"]) if ids.get(name)]
        bay = [(ids[n], q) for n, q in parsed["bay"] if ids.get(n)]
        return {"key": key, "source": source, "role": role, "tier": tier, "name": fit["name"],
                "ship_type_id": fit["ship_type_id"], "fitted": fit["fitted"], "loaded": loaded, "bay": bay,
                "type_ids": fit["type_ids"], "eft": fit["eft"]}

    def t1_variant(self, eft):
        """T2 のモジュール・ドローン・弾（名前が「… II」）を T1（「… I」）に置き換えた EFT。T1 が無いものはそのまま。"""
        def swap(name):
            return t1_name(self.catalog, name)

        lines = []
        for line in eft.strip().splitlines():
            if not line.strip() or line.startswith("["):
                lines.append(line)
                continue
            base, sep, count = line.rpartition(" x")
            if sep and count.isdigit():
                lines.append(f"{swap(base)} x{count}")
            else:
                lines.append(", ".join(swap(part) for part in line.split(",")))
        first = lines[0]
        lines[0] = first[:-1] + "（T1 装備）]"
        return "\n".join(lines) + "\n"

    def templates(self):
        """定番フィットと、その T1 装備版（T2 を使えないキャラクター向け）。"""
        if self._templates is None:
            self._templates = []
            for n, t in enumerate(TEMPLATES):
                base = self._from_eft(t["eft"], t["role"], "template", f"template:{n}", t["tier"])
                base["variant"], base["base_key"] = "t2", base["key"]
                self._templates.append(base)
                t1_eft = self.t1_variant(t["eft"])
                if t1_eft.split("\n", 1)[1] != t["eft"].strip().split("\n", 1)[1] + "\n":
                    t1 = self._from_eft(t1_eft, t["role"], "template", f"template:{n}:t1", t["tier"])
                    t1["variant"], t1["base_key"] = "t1", base["key"]
                    self._templates.append(t1)
        return self._templates

    def detect_role(self, ship_type_id, fitted, bay):
        """ユーザーのフィットの役割を装備から判定する。判定できなければ None。"""
        self.data.ensure([ship_type_id, *fitted, *[t for t, _ in bay]])
        groups = [self.catalog.get(t)["group"] if self.catalog.get(t) else "" for t in fitted]
        ship = self.catalog.get(ship_type_id) or {}
        if any(g in GAS_MODULE_GROUPS for g in groups):
            return "mining_gas"
        names = [(self.catalog.get(t) or {}).get("en", "") for t in fitted]
        if any(w in n and "Upgrade" not in n for n in names for w in ICE_MODULE_WORDS):
            return "mining_ice"
        if any(g in ORE_MODULE_GROUPS for g in groups):
            return "mining_ore"
        # 採掘ドローンにもダメージ倍率の属性があるので、ダメージがあるものだけを戦闘用とする
        combat_drones = any(self.data.attr(t, 1272, 0) and any(self.data.attr(t, a, 0) for a in (114, 116, 117, 118))
                            for t, _ in bay)
        mining_drones = any(self.data.attr(t, 77, 0) and self.data.attr(t, 1272, 0) for t, _ in bay)
        if mining_drones and not combat_drones:
            return "drone_mining"
        if sum(bool(self.data.attr(t, 902, 0)) for t in fitted) >= 2:  # サルベージャー
            return "salvage"
        if any(self.data.attr(t, 1910, 0) for t in fitted):  # データ・レリックアナライザー
            return "exploration"
        if ship.get("group") == "Stealth Bomber":
            return "bomber"
        # PvP: 遠隔回復が 2 つ以上 → ロジ、ワープ妨害あり → フリゲートで MWD ならタックル、ウェブ・スクランブラーならブローラー、
        # ディスラプターだけならカイト
        remote = sum(any(e["name"] in ("shipModuleRemoteArmorRepairer", "shipModuleRemoteShieldBooster")
                         for e in self.data.type_effects(t)) for t in fitted)
        if remote >= 2:
            return "logistics"
        tackle = pvp_stats.tackle(self.data, fitted)
        if tackle:
            kinds = {t["kind"] for t in tackle}
            has_mwd = any(self.data.types[t]["group_id"] == 46 and self.data.attr(t, 554, 0) for t in fitted)
            if self.data.attr(ship_type_id, 1547, 0) == 1 and has_mwd:  # 小型（リグサイズ 1）で MWD
                return "tackle"
            if kinds & {"scram", "web"}:
                return "brawler"
            return "kiter"
        launchers = sum(self.data.types[t]["group_id"] in MISSILE_LAUNCHER_GROUPS for t in fitted)
        dda = any(g == "Drone Damage Modules" for g in groups)
        if combat_drones and (dda or not launchers):
            return "drone"
        if launchers:
            return "missile"
        if sum(self.data.types[t]["group_id"] in TURRET_GROUPS for t in fitted) >= 2:
            return "turret"
        if self._special_holds(ship_type_id):
            return "special_hauler"
        if ship.get("group") in HAULER_GROUPS:  # サルベージ船などのカーゴ拡張は輸送に含めない
            return "hauler"
        return None

    def _special_holds(self, ship_type_id):
        """専用カーゴの基本容量の合計（Miasmos のような採掘カーゴ付きの輸送艦も含む）。"""
        total = sum(self.data.attr(ship_type_id, a, 0) for a in SPECIAL_HOLD_ATTRS)
        item = self.catalog.get(ship_type_id) or {}
        if item.get("group") == "Hauler":
            total += self.data.attr(ship_type_id, 1556, 0)
        return total

    # ---------- 評価 ----------

    def _levels(self, character):
        return {s["skill_id"]: s["trained_level"] for s in character["skills"]}

    def _with_levels(self, character, new_levels):
        """スキルレベルを変えたキャラクター（訓練後の試算用）。"""
        skills = {s["skill_id"]: dict(s) for s in character["skills"]}
        for skill_id, level in new_levels.items():
            s = skills.setdefault(skill_id, {"skill_id": skill_id, "trained_level": 0, "skillpoints": 0})
            if level > s["trained_level"]:
                rank = self.type_cache.get(skill_id)["rank"] or 1
                s["trained_level"] = level
                s["skillpoints"] = max(s["skillpoints"], skill_check.sp_for_level(rank, level))
        return {**character, "skills": list(skills.values())}

    def evaluate(self, cand, character):
        """1 フィット × 1 キャラクター。"""
        check = skill_check.check_types(self.type_cache, cand["type_ids"], character)
        cost = lambda targets: skill_check.build_plan(self.type_cache, [], character, targets)["total_minutes"]  # noqa: E731
        res = fitting.check_resources(self.data, self.type_cache, cand["ship_type_id"], cand["fitted"], character, cost)
        extra = {s["skill_id"]: s["to"] for s in (res.get("suggestion") or {}).get("skills", [])}
        usable_now = check["status"] == "ok" and res["ok"]
        plan = None
        if not usable_now:
            plan = skill_check.build_plan(self.type_cache, cand["type_ids"], character, extra)
        minutes = 0 if usable_now else plan["total_minutes"]
        impossible = (res.get("suggestion") or {}).get("impossible") or not res["calibration"]["ok"]

        levels = self._levels(character)
        after_levels = dict(levels)
        if plan:
            for step in plan["steps"]:
                after_levels[step["skill_id"]] = max(after_levels.get(step["skill_id"], 0), step["level"])
        after_char = self._with_levels(character, after_levels) if plan else character
        dps = self.calc.compute(cand["ship_type_id"], cand["fitted"], cand["loaded"], cand["bay"], after_levels)
        holds = (fitting.check_resources(self.data, self.type_cache, cand["ship_type_id"], cand["fitted"], after_char)
                 if plan else res)["holds"]

        ship = self.catalog.get(cand["ship_type_id"]) or {"ja": self.type_cache.get(cand["ship_type_id"])["name"],
                                                         "en": self.type_cache.get(cand["ship_type_id"])["name"]}
        return {
            "key": cand["key"], "source": cand["source"], "role": cand["role"], "tier": cand["tier"],
            "variant": cand.get("variant"), "base_key": cand.get("base_key", cand["key"]),
            "name": cand["name"], "ship_type_id": cand["ship_type_id"], "ship_ja": ship.get("ja"),
            "ship_en": ship.get("en"), "type_ids": cand["type_ids"], "eft": cand["eft"],
            "usable_now": usable_now, "impossible": bool(impossible), "minutes": minutes,
            "plan_skills": [[s, lv] for s, lv in extra.items()],
            "dps": dps, "holds": holds, "approximate": res["approximate"],
            "bom": bill_of_materials(cand),
            "align": self._align(cand, after_levels), "prop_swapped": cand.get("prop_swapped"),
            "warp_strength": fit_rules.warp_strength(self.data, cand["ship_type_id"], cand["fitted"]),
            "pvp": pvp_stats.compute(self.data, cand["ship_type_id"], cand["fitted"], after_levels),
            "wcs": cand.get("wcs"),
        }

    def _align(self, cand, levels):
        info = align.align_times(self.data, cand["ship_type_id"], cand["fitted"], levels)
        return {"normal": info["normal"], "trick": info["trick"], "effective": info["effective"]}

    def dps_upgrades(self, cand, character, budget=SOON_MINUTES):
        """今すぐ使える戦闘用フィットの DPS を、budget 分以内の訓練でどれだけ上げられるか（効率の良い順に選ぶ）。"""
        levels = self._levels(character)
        base = self.calc.compute(cand["ship_type_id"], cand["fitted"], cand["loaded"], cand["bay"], levels)["total"]
        if base <= 0:
            return None
        # DPS に関係しうるスキル: ミサイル・ドローンの基本スキル、装備・弾・ドローン・艦の必要スキル
        candidates = {SKILL_MISSILE_LAUNCHER_OPERATION, SKILL_RAPID_LAUNCH, SKILL_WARHEAD_UPGRADES,
                      SKILL_DRONES, SKILL_DRONE_INTERFACING, SKILL_GUNNERY, SKILL_RAPID_FIRING, SKILL_SURGICAL_STRIKE}
        for t in {cand["ship_type_id"], *cand["fitted"], *[c for c in cand["loaded"] if c], *[b for b, _ in cand["bay"]]}:
            candidates |= {s for s, _ in self.type_cache.get(t)["requirements"]}
        self.data.ensure(candidates)

        current = dict(levels)
        steps, spent, dps = [], 0.0, base
        while True:
            best = None
            for skill_id in candidates:
                level = current.get(skill_id, 0)
                if level >= 5 or (level == 0 and skill_id not in levels):
                    continue  # 未注入のスキルは対象外（スキルブックが必要なため）
                trial = {**current, skill_id: level + 1}
                gain = self.calc.compute(cand["ship_type_id"], cand["fitted"], cand["loaded"], cand["bay"], trial)["total"] - dps
                if gain <= 0.05:
                    continue
                trial_char = self._with_levels(character, current)
                minutes = skill_check.build_plan(self.type_cache, [], trial_char, {skill_id: level + 1})["unqueued_minutes"]
                if spent + minutes > budget:
                    continue
                score = gain / max(minutes, 1)
                if not best or score > best[0]:
                    best = (score, skill_id, level + 1, gain, minutes)
            if not best:
                break
            _, skill_id, level, gain, minutes = best
            current[skill_id] = level
            spent += minutes
            dps += gain
            steps.append({"skill_id": skill_id, "name": self.type_cache.get(skill_id)["name"],
                          "level": level, "minutes": minutes, "dps_gain": round(gain, 1)})
        if not steps:
            return None
        return {"steps": steps, "minutes": spent, "dps_before": round(base, 1), "dps_after": round(dps, 1),
                "skills": [[s["skill_id"], s["level"]] for s in steps]}

    # ---------- MWD の小技 ----------

    def adapt_props(self, cands, character):
        """定番・自動のフィットで、MWD の小技でワープが速くならない（このキャラクターのスキルで）ものは
        MWD を同じ大きさのアフターバーナーに替える。替えた結果が他の候補と同じになったら、その候補は出さない。"""
        levels = self._levels(character)
        result, seen = [], set()
        for cand in cands:
            # PvP（ボマーを含む）の MWD は戦闘中の速さのためなので替えない
            if cand["source"] in ("template", "auto") and PURPOSE.get(cand["role"]) != "pvp":
                swapped = self._swap_mwd(cand, levels)
                if swapped and "（MWD）" in cand["name"]:
                    continue  # MWD 版として作った定番（AB 版が別にある）は、小技の効果が無ければ出さない
                cand = swapped or cand
            sig = (cand["ship_type_id"], tuple(sorted(cand["fitted"])), tuple(sorted(cand["bay"])))
            if sig in seen:
                continue  # MWD 版を AB に替えたら AB 版と同じになった
            seen.add(sig)
            result.append(cand)
        return result

    def _swap_mwd(self, cand, levels):
        info = align.align_times(self.data, cand["ship_type_id"], cand["fitted"], levels)
        if not info["mwd"] or info["effective"]:
            return None
        mwd_name = self.catalog.get(info["mwd"])["en"] if self.catalog.get(info["mwd"]) else None
        if not mwd_name:
            return None
        ab = next(((n, t) for n in align.ab_name_for(mwd_name) if (t := self.catalog.find_by_name(n))), None)
        if not ab:
            return None
        ab_name, ab_id = ab
        eft = cand["eft"].replace(mwd_name, ab_name)
        name = cand["name"].replace("（MWD）", "")
        eft = eft.replace(cand["name"], name, 1)
        fitted = [ab_id if t == info["mwd"] else t for t in cand["fitted"]]
        type_ids = sorted({*(t for t in cand["type_ids"] if t != info["mwd"]), ab_id})
        return {**cand, "fitted": fitted, "type_ids": type_ids, "eft": eft, "name": name,
                "prop_swapped": {"from": mwd_name, "to": ab_name, "normal": info["normal"], "trick": info["trick"]}}

    # ---------- ワープコアの強度（スクランブル対策） ----------

    WCS_NAME = "Warp Core Stabilizer I"

    def wcs_variant(self, cand):
        """ローのスロットにワープコアスタビライザーを入れた版（空きが無ければ優先度の低いモジュールと入れ替え）。"""
        wcs_id = self.catalog.find_by_name(self.WCS_NAME)
        if not wcs_id:
            return None
        self.data.ensure([cand["ship_type_id"], *cand["fitted"], wcs_id])
        if fit_rules.warp_strength(self.data, cand["ship_type_id"], cand["fitted"])["wcs"]:
            return None  # もう付いている
        total = int(self.data.attr(cand["ship_type_id"], fit_rules.SHIP_SLOT_ATTRS["low"], 0))
        if not total:
            return None
        lows = [t for t in cand["fitted"] if fit_rules.slot_of(self.data, t) == "low"]
        name_of = lambda t: (self.catalog.get(t) or {}).get("en") or self.type_cache.get(t)["name"]  # noqa: E731
        lines = cand["eft"].strip().splitlines()
        if len(lows) < total:  # 空きスロットに足す（EFT はロースロットが最初のまとまり）
            if lows:
                last = max(i for i, line in enumerate(lines) if line.split(",")[0].strip() in {name_of(t) for t in lows})
                lines.insert(last + 1, self.WCS_NAME)
            else:
                lines[1:1] = [self.WCS_NAME, ""]
            removed = None
        else:  # 優先度の低いモジュールと入れ替え
            victim = next((t for prefix in REMOVE_ORDER for t in lows if name_of(t).startswith(prefix)), lows[-1])
            removed = name_of(victim)
            idx = next(i for i, line in enumerate(lines) if line.split(",")[0].strip() == removed)
            lines[idx] = self.WCS_NAME
        header = lines[0]
        lines[0] = header[:-1] + "（WCS）]"
        v = self._from_eft("\n".join(lines) + "\n", cand["role"], cand["source"], f"{cand['key']}:wcs", cand.get("tier", 0))
        v["variant"] = cand.get("variant")
        v["base_key"] = f"{cand.get('base_key', cand['key'])}:wcs"
        v["wcs"] = {"removed": removed}
        return v

    def add_wcs_variants(self, cands):
        result = list(cands)
        for cand in cands:
            try:
                v = self.wcs_variant(cand)
            except (KeyError, ValueError, StopIteration, RuntimeError):
                v = None
            if v:
                result.append(v)
        return result

    # ---------- おすすめフィット ----------

    def recommend_fits(self, character, user_fits, wcs=False, purpose=None):
        """user_fits: [{"key", "source", "name", "ship_type_id", "fitted", "loaded", "bay", "type_ids", "eft"}]"""
        cands = list(self.templates())
        for f in user_fits:
            role = self.detect_role(f["ship_type_id"], f["fitted"], f["bay"])
            if role:
                cands.append({**f, "role": role, "tier": 0})

        # purpose: "pve" / "pvp" のページでは、その用途の役割だけ（None は全部）
        role_names = {r: label for r, label in ROLES.items() if purpose is None or PURPOSE.get(r) == purpose}
        cands = [c for c in cands if c["role"] in role_names]
        cands = self.adapt_props(cands, character)
        if wcs:
            cands = self.add_wcs_variants(cands)
        roles = {r: {"label": label, "now": [], "soon": []} for r, label in role_names.items()}
        for cand in cands:
            try:
                e = self.evaluate(cand, character)
            except (KeyError, RuntimeError) as err:  # 型情報が取れないなど
                print(f"おすすめの計算を飛ばしました: {cand['name']} ({err})")
                continue
            if e["impossible"]:
                continue
            if e["usable_now"]:
                if e["role"] in COMBAT_ROLES:
                    e["upgrade"] = self.dps_upgrades(cand, character)
                roles[e["role"]]["now"].append(e)
            elif e["minutes"] is not None and e["minutes"] <= SOON_MINUTES:
                roles[e["role"]]["soon"].append(e)

        # 同じ定番フィットの T2 版が今すぐ使えるなら、T1 版は出さない
        t2_now = {e["base_key"] for r in roles.values() for e in r["now"] if e.get("variant") == "t2"}
        for r in roles.values():
            r["now"] = [e for e in r["now"] if not (e.get("variant") == "t1" and e["base_key"] in t2_now)]
            r["soon"] = [e for e in r["soon"] if not (e.get("variant") == "t1" and e["base_key"] in t2_now)]
            now_keys = {e["base_key"] for e in r["now"]}
            for e in r["soon"]:
                e["upgrade_of_now"] = e["base_key"] in now_keys  # 今使えるフィットの強化版（T1 → T2 など）

        def sort_key(e):
            return fit_sort_key(e)

        for r in roles.values():
            r["now"].sort(key=sort_key)
            r["soon"].sort(key=lambda e: (sort_key(e), e["minutes"]))
        self.data.save()
        return roles

    # ---------- 艦を選んだときのフィット ----------

    def fits_for_ship(self, character, ship_type_id, user_fits, wcs=False):
        """1 隻分のフィット: 定番・自分のフィット。無ければ役割に合わせて自動で組む。"""
        cands = [t for t in self.templates() if t["ship_type_id"] == ship_type_id]
        for f in user_fits:
            if f["ship_type_id"] == ship_type_id:
                role = self.detect_role(f["ship_type_id"], f["fitted"], f["bay"])
                cands.append({**f, "role": role or "other", "tier": 0})
        auto = False
        item = self.catalog.get(ship_type_id)
        if item:
            # 登録されたフィットが無い役割は、自動で組む（例: Prospect の定番はガスだけ → 鉱石は自動）
            covered = {c["role"] for c in cands}
            missing_roles = self.ship_roles(ship_type_id, item) - covered
            auto = bool(missing_roles) and not cands
            size_class = SHIP_CLASS.get(item["group"], 3)
            for role in sorted(missing_roles, key=list(ROLES).index):
                eft = self.autofitter.make(ship_type_id, item["en"], role, size_class, item["group"], ROLES[role])
                if not eft:
                    continue
                base = self._from_eft(eft, role, "auto", f"auto:{ship_type_id}:{role}")
                base["variant"], base["base_key"] = "t2", base["key"]
                cands.append(base)
                t1_eft = self.t1_variant(eft)
                if t1_eft.split("\n", 1)[1] != eft.split("\n", 1)[1]:
                    t1 = self._from_eft(t1_eft, role, "auto", f"auto:{ship_type_id}:{role}:t1")
                    t1["variant"], t1["base_key"] = "t1", base["key"]
                    cands.append(t1)

        cands = self.adapt_props(cands, character)
        if wcs:
            cands = self.add_wcs_variants(cands)
        results = []
        for cand in cands:
            try:
                e = self.evaluate(cand, character)
            except (KeyError, RuntimeError) as err:
                print(f"フィットの計算を飛ばしました: {cand['name']} ({err})")
                continue
            if e["usable_now"] and e["role"] in COMBAT_ROLES:
                e["upgrade"] = self.dps_upgrades(cand, character)
            e["role_label"] = ROLES.get(e["role"], "その他")
            results.append(e)
        results.sort(key=lambda e: (not e["usable_now"], e["impossible"], fit_sort_key(e),
                                    e["minutes"] if e["minutes"] is not None else 1e12))
        self.data.save()
        return {"auto": auto, "fits": results}

    # ---------- おすすめ艦船 ----------

    def ship_roles(self, ship_type_id, item):
        """艦船の役割（複数あり）を艦ボーナス・グループから判定する。"""
        roles = set()
        group = item["group"]
        hull, _ = self.calc._hull_bonuses(ship_type_id, {})
        kinds = {k for k, _ in hull}
        effect_names = " ".join(e["name"] for e in self.data.type_effects(ship_type_id))
        industrial = group in HAULER_GROUPS or group in MINING_GROUPS or group == "Industrial Command Ship"
        if any(k.startswith("drone_damage") for k in kinds) and not industrial \
                and self.data.attr(ship_type_id, 1271, 0) >= MIN_DRONE_BANDWIDTH:
            roles.add("drone")
        if group == "Stealth Bomber":
            roles.add("bomber")
        elif any(k.startswith("missile") for k in kinds):
            roles.add("missile")
        if kinds & {"turret_damage", "turret_rof"} and not industrial \
                and self.data.attr(ship_type_id, ATTR_TURRET_SLOTS, 0) >= 2:
            roles.add("turret")
        if self._special_holds(ship_type_id):
            roles.add("special_hauler")
        elif group in HAULER_GROUPS:
            roles.add("hauler")
        if self.data.attr(ship_type_id, ATTR_VIRUS_STRENGTH_BONUS, 0) or "probe_strength" in kinds:
            roles.add("exploration")
        if "salvage_cycle" in kinds or group == "Destroyer":
            roles.add("salvage")
        if "drone_mining" in kinds:
            roles.add("drone_mining")
        # 遠征フリゲートは鉱石の採掘ボーナスがあるものだけ（Endurance は氷専用）
        if group in ("Mining Barge", "Exhumer") or ORE_EFFECT_RE.search(effect_names):
            roles.add("mining_ore")
        if GAS_EFFECT_RE.search(effect_names):
            roles.add("mining_gas")
        if ICE_EFFECT_RE.search(effect_names):
            roles.add("mining_ice")
        return roles

    def recommend_ships(self, character, limit=12):
        ships = [i for i in self.catalog.items if i["category"] == "艦船" and i["group"] in SHIP_CLASS]
        self.data.ensure([s["id"] for s in ships])
        roles = {r: {"label": label, "now": [], "soon": []} for r, label in ROLES.items()}
        for item in ships:
            ship_roles = self.ship_roles(item["id"], item)
            if not ship_roles:
                continue
            check = skill_check.check_target(self.type_cache, item["id"], character)
            minutes = 0 if check["status"] == "ok" else check["total_minutes"]
            if minutes is None or minutes > SOON_MINUTES:
                continue
            entry = {
                "type_id": item["id"], "ja": item["ja"], "en": item["en"], "group": item["group"],
                "class": SHIP_CLASS[item["group"]], "tech": int(self.data.attr(item["id"], ATTR_TECH_LEVEL, 1)),
                "meta": self.data.attr(item["id"], ATTR_META_LEVEL, 0), "minutes": minutes,
                "status": check["status"], "ready_at": check["ready_at"],
                "launchers": int(self.data.attr(item["id"], ATTR_LAUNCHER_SLOTS, 0)),
                "bandwidth": self.data.attr(item["id"], 1271, 0), "drone_bay": self.data.attr(item["id"], 283, 0),
                "cargo": self.data.attr(item["id"], 38, 0), "mining_hold": self.data.attr(item["id"], 1556, 0),
                "turrets": int(self.data.attr(item["id"], ATTR_TURRET_SLOTS, 0)),
                "virus_bonus": self.data.attr(item["id"], ATTR_VIRUS_STRENGTH_BONUS, 0),
                "special_hold": self._special_holds(item["id"]),
                "hi_slots": int(self.data.attr(item["id"], 14, 0)),
            }
            for role in ship_roles:
                roles[role]["now" if minutes == 0 else "soon"].append(entry)

        def sort_key(e, role):
            size = e["class"]
            if role == "hauler":
                return (-e["cargo"],)
            if role == "special_hauler":
                return (-e["special_hold"],)
            if role.startswith("mining"):
                return (-size, -e["mining_hold"])
            if role == "drone_mining":
                return (-e["bandwidth"], -size)
            if role == "exploration":
                return (-e["virus_bonus"], -e["tech"], -size)
            if role == "salvage":
                return (-(e["group"] == "Hauler"), -e["hi_slots"], -e["tech"])  # Noctis（サルベージ専用艦）が先
            return (-size, -e["tech"], -e["meta"])

        for role, r in roles.items():
            r["now"] = sorted(r["now"], key=lambda e: sort_key(e, role))[:limit]
            r["soon"] = sorted(r["soon"], key=lambda e: (sort_key(e, role), e["minutes"]))[:limit]
        self.data.save()
        return roles
