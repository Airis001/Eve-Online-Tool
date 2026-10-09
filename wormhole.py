"""ワームホールの判別（ESI の Wormhole グループのデータ）と、星系の種類（J 空間のクラス・セキュリティ）。"""

import json
import threading
from concurrent.futures import ThreadPoolExecutor

from i18n import tr
from paths import DATA_DIR

CACHE_FILE = DATA_DIR / "wormhole_cache.json"
CACHE_VERSION = 1
WORMHOLE_GROUP_ID = 988

ATTR_TARGET_CLASS = 1381
ATTR_LIFETIME = 1382       # 分
ATTR_TOTAL_MASS = 1383     # kg
ATTR_MASS_REGEN = 1384     # kg（ほぼ 0）
ATTR_MAX_JUMP_MASS = 1385  # kg
ATTR_MASS = 4
ATTR_MASS_ADDITION = 796   # アーマープレート・推進モジュールの追加質量
PROPULSION_GROUP_ID = 46   # アフターバーナー・マイクロワープドライブ（起動中だけ重くなる）

# 行き先のクラス（属性 1381 の値）→ 表示名
CLASS_LABELS = {
    1: "C1", 2: "C2", 3: "C3", 4: "C4", 5: "C5", 6: "C6",
    7: "ハイセク", 8: "ローセク", 9: "ヌルセク", 12: "Thera", 13: "C13（フリゲートのみ）",
    14: "C14 Sentinel（ドリフター）", 15: "C15 Barbican（ドリフター）", 16: "C16 Vidette（ドリフター）",
    17: "C17 Conflux（ドリフター）", 18: "C18 Redoubt（ドリフター）", 25: "Pochven", -1: "Pochven 内",
}

# J 空間の地域名の頭文字 → クラス（A-R00001 = C1 … K-R00033 = ドリフター）
REGION_LETTER_CLASS = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 12, "H": 13}
DRIFTER_SYSTEMS = {"J055520": 14, "J110145": 15, "J164710": 16, "J200727": 17, "J174618": 18}
THERA_SYSTEM_ID = 31000005
POCHVEN_REGION_ID = 10000070
WORMHOLE_SYSTEM_MIN, WORMHOLE_SYSTEM_MAX = 31000000, 31999999


class WormholeData:
    """ワームホールの種類（コード → 行き先・寿命・質量）。初回は ESI から取得して wormhole_cache.json に保存する。"""

    def __init__(self, esi_get, path=CACHE_FILE):
        self.esi_get = esi_get
        self.path = path
        self._lock = threading.Lock()
        self._types = None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if raw.get("version") == CACHE_VERSION:
                self._types = raw["types"]
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            pass

    def types(self):
        with self._lock:
            if self._types is None:
                self._types = self._build()
                self.path.write_text(json.dumps({"version": CACHE_VERSION, "types": self._types}, ensure_ascii=False),
                                     encoding="utf-8")
            return self._types

    def _build(self):
        type_ids = self.esi_get(f"/universe/groups/{WORMHOLE_GROUP_ID}/")["types"]
        with ThreadPoolExecutor(max_workers=10) as pool:
            data = list(pool.map(lambda t: self.esi_get(f"/universe/types/{t}/"), type_ids))
        result = {}
        for d in sorted(data, key=lambda d: d["type_id"]):
            name = d.get("name", "")
            if not name.startswith("Wormhole "):  # 開発用（QA Wormhole）は除く
                continue
            code = name.split(" ", 1)[1]
            attrs = {a["attribute_id"]: a["value"] for a in d.get("dogma_attributes", [])}
            target = attrs.get(ATTR_TARGET_CLASS)
            entry = {
                "code": code, "type_id": d["type_id"],
                "target_class": int(target) if target is not None else None,
                "target_label": CLASS_LABELS.get(int(target), tr("クラス {0}", int(target))) if target is not None else None,
                "lifetime_hours": attrs[ATTR_LIFETIME] / 60 if ATTR_LIFETIME in attrs else None,
                "total_mass": attrs.get(ATTR_TOTAL_MASS),
                "max_jump_mass": attrs.get(ATTR_MAX_JUMP_MASS),
                "mass_regen": attrs.get(ATTR_MASS_REGEN, 0),
            }
            if code == "K162":
                entry["note"] = "出口側の穴。行き先は反対側の穴の種類で決まります（ゲーム内で穴の情報を見ると大まかな行き先が出ます）。"
            result.setdefault(code, entry)  # 同じコードが複数ある（C729 など）ときは最初のもの
        return sorted(result.values(), key=lambda e: e["code"])


def system_class(system_id, system_name, region_id, region_name, security):
    """星系の種類。{"kind": "wormhole"|"highsec"|"lowsec"|"nullsec"|"pochven", "class": int|None, "label": str}"""
    if system_id == THERA_SYSTEM_ID:
        return {"kind": "wormhole", "class": 12, "label": "Thera"}
    if WORMHOLE_SYSTEM_MIN <= system_id <= WORMHOLE_SYSTEM_MAX:
        cls = DRIFTER_SYSTEMS.get(system_name) or REGION_LETTER_CLASS.get((region_name or " ")[0])
        if cls is None and (region_name or "").startswith("K-R"):
            return {"kind": "wormhole", "class": None, "label": "ドリフター"}
        return {"kind": "wormhole", "class": cls, "label": CLASS_LABELS.get(cls, "J 空間")}
    if region_id == POCHVEN_REGION_ID:
        return {"kind": "pochven", "class": 25, "label": "Pochven"}
    if security >= 0.45:
        return {"kind": "highsec", "class": 7, "label": "ハイセク"}
    if security > 0.0:
        return {"kind": "lowsec", "class": 8, "label": "ローセク"}
    return {"kind": "nullsec", "class": 9, "label": "ヌルセク"}


def display_security(security):
    """ゲーム内の表示と同じセキュリティ（0 より大きく 0.05 未満は 0.1 と表示される）。"""
    if 0.0 < security < 0.05:
        return 0.1
    return round(security, 1)


class Universe:
    """星系・星座・地域の情報（変わらないのでメモリにキャッシュ）。"""

    def __init__(self, esi_get):
        self.esi_get = esi_get
        self._cache = {}
        self._lock = threading.Lock()

    def _get(self, path):
        with self._lock:
            if path in self._cache:
                return self._cache[path]
        data = self.esi_get(path)
        with self._lock:
            self._cache[path] = data
        return data

    def system(self, system_id):
        s = self._get(f"/universe/systems/{system_id}/")
        constellation = self._get(f"/universe/constellations/{s['constellation_id']}/")
        region = self._get(f"/universe/regions/{constellation['region_id']}/")
        security = s.get("security_status", 0.0)
        return {
            "id": system_id, "name": s["name"], "security": security, "security_display": display_security(security),
            "constellation": constellation["name"], "region_id": region["region_id"], "region": region["name"],
            **system_class(system_id, s["name"], region["region_id"], region["name"], security),
        }

    def gates(self, system_id):
        """星系のゲート {行き先の星系 ID: ゲートの座標}（オートパイロットの時間の見積もり用）。"""
        s = self._get(f"/universe/systems/{system_id}/")
        out = {}
        for gate_id in s.get("stargates", []):
            g = self._get(f"/universe/stargates/{gate_id}/")
            out[g["destination"]["system_id"]] = g["position"]
        return out

    def station(self, station_id):
        """ステーションの情報（名前・星系・座標）。"""
        return self._get(f"/universe/stations/{station_id}/")


def ship_masses(data, ship_type_id, fitted):
    """艦の質量（kg）。cold: 推進モジュール停止、hot: 起動中（一番重くなるもの 1 つ）。プレートなどは常に加算。"""
    data.ensure([ship_type_id, *fitted])
    cold = data.attr(ship_type_id, ATTR_MASS, 0)
    prop = 0.0
    for t in fitted:
        add = data.attr(t, ATTR_MASS_ADDITION, 0)
        if data.types[t]["group_id"] == PROPULSION_GROUP_ID:
            prop = max(prop, add)
        else:
            cold += add
    return {"cold": cold, "hot": cold + prop, "prop": prop}
