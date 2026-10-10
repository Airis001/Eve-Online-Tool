"""CCP の静的データ（SDE）から、ESI に無いデータを取り出して sde_data.json に保存する。

  - 設計図の材料・製品・時間（製造・リアクション）
  - PI（惑星開発）のレシピと、惑星の種類ごとの資源（P0）
  - 上記に出てくるアイテムの日本語名・英語名
  - 公開されている全アイテムの、日本語・英語以外の名前（画面の言語に合わせて名前を出すため）

SDE は約 100MB の zip なので、初回（または更新ボタン）のときだけダウンロードし、必要な部分を取り出したら消す。
"""

import io
import json
import threading
import time
import zipfile

import requests

from i18n import tr
from paths import DATA_DIR

DATA_FILE = DATA_DIR / "sde_data.json"
TMP_ZIP = DATA_DIR / ".sde_download.zip"
SDE_URL = "https://developers.eveonline.com/static-data/eve-online-static-data-latest-jsonl.zip"
DATA_VERSION = 8  # 6: ゲート（星系のつながりと位置）、7: エージェント・ステーションの星系・NPC コーポの名前、8: ほかの言語の名前
# 日本語・英語のほかに名前を取り出す言語（SDE の name のキー）
LOC_LANGS = ("de", "fr", "es", "ru", "ko", "zh")
# 残すエージェント: 部門（流通・採掘・セキュリティ）と種類（ふつうのエージェント・CONCORD）
AGENT_DIVISIONS = {22: "distribution", 23: "mining", 24: "security"}
AGENT_TYPES = {2, 5}
OLDEST_USABLE = 5  # これ以降の版は、作り直すまでのあいだそのまま使う

# 惑星の種類 → 採れる資源（P0）。ESI の planet_type と同じ名前
PLANET_RESOURCES = {
    "barren": ["Aqueous Liquids", "Base Metals", "Carbon Compounds", "Microorganisms", "Noble Metals"],
    "gas": ["Aqueous Liquids", "Base Metals", "Ionic Solutions", "Noble Gas", "Reactive Gas"],
    "ice": ["Aqueous Liquids", "Heavy Metals", "Microorganisms", "Noble Gas", "Planktic Colonies"],
    "lava": ["Base Metals", "Felsic Magma", "Heavy Metals", "Non-CS Crystals", "Suspended Plasma"],
    "oceanic": ["Aqueous Liquids", "Carbon Compounds", "Complex Organisms", "Microorganisms", "Planktic Colonies"],
    "plasma": ["Base Metals", "Heavy Metals", "Noble Metals", "Non-CS Crystals", "Suspended Plasma"],
    "storm": ["Aqueous Liquids", "Base Metals", "Ionic Solutions", "Noble Gas", "Suspended Plasma"],
    "temperate": ["Aqueous Liquids", "Autotrophs", "Carbon Compounds", "Complex Organisms", "Microorganisms"],
}
# 惑星のアイテム（ESI の /universe/planets の type_id）の英語名 → 種類
PLANET_TYPE_NAMES = {f"Planet ({k.capitalize()})": k for k in PLANET_RESOURCES}


class SdeData:
    def __init__(self, path=DATA_FILE):
        self.path = path
        self._lock = threading.Lock()
        self.data = None
        self.gates = {}
        self.agents, self.stations, self.corp_names = {}, {}, {}
        self.loc_names = {}
        self.outdated = True
        self.status = {"state": "missing", "progress": 0, "error": None}
        self.on_loaded = []  # 読み込んだとき（作り直したときも）に呼ぶ関数
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if OLDEST_USABLE <= raw.get("version", 0) <= DATA_VERSION:
                self._load(raw)
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def _load(self, raw):
        self.data = raw
        self.blueprints = {int(k): v for k, v in raw["blueprints"].items()}
        self.product_bp = {int(k): v for k, v in raw["product_bp"].items()}
        self.schematics = {int(k): v for k, v in raw["schematics"].items()}
        self.names = {int(k): v for k, v in raw["names"].items()}
        self.planet_types = {int(k): v for k, v in raw["planet_types"].items()}
        self.planet_resources = raw["planet_resources"]
        self.pi_tiers = {int(k): v for k, v in raw["pi_tiers"].items()}
        self.volumes = {int(k): v for k, v in raw.get("volumes", {}).items()}
        self.npc_factions = {int(k): v for k, v in raw.get("npc_factions", {}).items()}
        # 星系 {id: [英語名, 日本語名, セキュリティ, 地域 ID, ワームホールのクラス]}・地域 {id: [英語名, 日本語名, クラス]}
        self.systems = {int(k): v for k, v in raw.get("systems", {}).items()}
        self.regions = {int(k): v for k, v in raw.get("regions", {}).items()}
        # 同じ装備の仲間（T1・メタ・T2・勢力など）: 親（T1）→ [[type_id, メタグループ, メタレベル], …]、各アイテム → 親
        self.variants = {int(k): v for k, v in raw.get("variants", {}).items()}
        self.variant_parent = {t: parent for parent, rows in self.variants.items() for t, _, _ in rows}
        # ゲート {星系 ID: {行き先の星系 ID: 座標}}（ルートとオートパイロットの時間の計算用。古い版には無い）
        self.gates = {int(k): {int(d): {"x": x, "y": y, "z": z} for d, x, y, z in v} for k, v in raw.get("gates", {}).items()}
        # エージェント {id: [英語名, 日本語名, 部門, レベル, ステーション, コーポ, ロケーター]}・ステーション {id: 星系}・
        # NPC コーポ {id: [英語名, 日本語名]}（古い版には無い）
        self.agents = {int(k): v for k, v in raw.get("agents", {}).items()}
        self.stations = {int(k): v for k, v in raw.get("stations", {}).items()}
        self.corp_names = {int(k): v for k, v in raw.get("corp_names", {}).items()}
        # ほかの言語の名前 {言語: {type_id: 名前}}（古い版には無い）
        self.loc_names = {lang: {int(k): v for k, v in names.items()} for lang, names in raw.get("loc_names", {}).items()}
        self.outdated = raw.get("version") != DATA_VERSION
        self.status = {"state": "ready", "progress": 100, "error": None, "build": raw.get("build"),
                       "release": raw.get("release")}
        for callback in self.on_loaded:
            callback()

    @property
    def ready(self):
        return self.data is not None

    def localized(self, type_id, language):
        """日本語・英語以外の言語の名前（分からなければ None）。"""
        return self.loc_names.get(language, {}).get(type_id) if self.data else None

    def name(self, type_id):
        """(日本語名, 英語名)"""
        ja, en = self.names.get(type_id, (None, None))
        return ja or en or f"#{type_id}", en or f"#{type_id}"

    def build_async(self):
        with self._lock:
            if self.status["state"] == "building":
                return
            self.status = {"state": "building", "progress": 0, "error": None}
        threading.Thread(target=self._build_safe, daemon=True).start()

    def _build_safe(self):
        try:
            raw = self._build()
            self.path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
            self._load(raw)
        except Exception as e:  # noqa: BLE001 - 失敗は画面に出す
            self.status = {"state": "error", "progress": 0, "error": str(e).splitlines()[0] if str(e) else repr(e)}
        finally:
            TMP_ZIP.unlink(missing_ok=True)

    def _download(self):
        with requests.get(SDE_URL, stream=True, timeout=60) as res:
            res.raise_for_status()
            total = int(res.headers.get("Content-Length", 0)) or 100_000_000
            done = 0
            with TMP_ZIP.open("wb") as f:
                for chunk in res.iter_content(1 << 20):
                    f.write(chunk)
                    done += len(chunk)
                    self.status["progress"] = min(80, int(done / total * 80))

    def _build(self):
        self._download()
        z = zipfile.ZipFile(TMP_ZIP)

        def rows(name):
            with z.open(name) as f:
                for line in io.TextIOWrapper(f, encoding="utf-8"):
                    if line.strip():
                        yield json.loads(line)

        meta = next(rows("_sde.jsonl"))
        blueprints, product_bp = {}, {}
        for bp in rows("blueprints.jsonl"):
            for act in ("manufacturing", "reaction"):
                a = bp.get("activities", {}).get(act)
                if not a or not a.get("products"):
                    continue
                product = a["products"][0]
                blueprints[bp["blueprintTypeID"]] = {
                    "activity": act, "time": a.get("time", 0), "limit": bp.get("maxProductionLimit"),
                    "materials": [[m["typeID"], m["quantity"]] for m in a.get("materials", [])],
                    "skills": [[k["typeID"], k["level"]] for k in a.get("skills", [])],
                    "product": [product["typeID"], product["quantity"]],
                }
                product_bp.setdefault(product["typeID"], bp["blueprintTypeID"])
        self.status["progress"] = 84

        schematics = {}
        for s in rows("planetSchematics.jsonl"):
            inputs = [[t["_key"], t["quantity"]] for t in s["types"] if t["isInput"]]
            output = next([t["_key"], t["quantity"]] for t in s["types"] if not t["isInput"])
            schematics[s["_key"]] = {"name": [s["name"].get("ja"), s["name"].get("en")], "cycle": s["cycleTime"],
                                     "inputs": inputs, "output": output}

        wanted = set(blueprints) | set(product_bp)
        for b in blueprints.values():
            wanted.update(t for t, _ in b["materials"])
        for s in schematics.values():
            wanted.update(t for t, _ in s["inputs"])
            wanted.add(s["output"][0])
        resource_names = {n for names in PLANET_RESOURCES.values() for n in names}
        names, by_en, planet_types, volumes = {}, {}, {}, {}
        meta, children = {}, {}
        loc_names = {lang: {} for lang in LOC_LANGS}
        for t in rows("types.jsonl"):
            en = t.get("name", {}).get("en")
            if t.get("published"):
                for lang in LOC_LANGS:
                    name = t.get("name", {}).get(lang)
                    if name and name != en:  # 英語と同じなら持たない（英語名を使う）
                        loc_names[lang][t["_key"]] = name
            if t.get("published") and t.get("metaGroupID"):
                meta[t["_key"]] = (t["metaGroupID"], t.get("metaLevel", 0), t["name"].get("ja"), en)
                if t.get("variationParentTypeID"):
                    children.setdefault(t["variationParentTypeID"], []).append(t["_key"])
            if t["_key"] in wanted or en in resource_names:
                names[t["_key"]] = [t["name"].get("ja"), en]
                if t.get("volume") is not None:
                    volumes[t["_key"]] = t["volume"]
            if en in resource_names and t.get("published", True):
                by_en.setdefault(en, t["_key"])
            if t.get("groupID") == 7 and en in PLANET_TYPE_NAMES:
                planet_types[t["_key"]] = PLANET_TYPE_NAMES[en]
                names[t["_key"]] = [t["name"].get("ja"), en]
        variants = {}
        for parent, kids in children.items():
            members = [parent, *kids] if parent in meta else kids
            variants[parent] = [[t, meta[t][0], meta[t][1]] for t in members if t in meta]
            for t in members:
                if t in meta:
                    names.setdefault(t, [meta[t][2], meta[t][3]])
        corps = list(rows("npcCorporations.jsonl"))
        npc_factions = {c["_key"]: c["factionID"] for c in corps if c.get("factionID")}
        agents = {}
        for c in rows("npcCharacters.jsonl"):
            a = c.get("agent")
            if a and a.get("divisionID") in AGENT_DIVISIONS and a.get("agentTypeID") in AGENT_TYPES:
                agents[c["_key"]] = [c["name"].get("en"), c["name"].get("ja"), a["divisionID"], a.get("level"),
                                     c.get("locationID"), c.get("corporationID"), bool(a.get("isLocator"))]
        used_corps = {a[5] for a in agents.values()}
        corp_names = {c["_key"]: [c["name"].get("en"), c["name"].get("ja")] for c in corps if c["_key"] in used_corps}
        stations = {st["_key"]: st["solarSystemID"] for st in rows("npcStations.jsonl")}
        regions = {r["_key"]: [r["name"].get("en"), r["name"].get("ja"), r.get("wormholeClassID")] for r in rows("mapRegions.jsonl")}
        systems = {s["_key"]: [s["name"].get("en"), s["name"].get("ja"), round(s.get("securityStatus", 0.0), 4), s.get("regionID"),
                               s.get("wormholeClassID") or regions.get(s.get("regionID"), [None, None, None])[2]]
                   for s in rows("mapSolarSystems.jsonl")}
        gates = {}
        for g in rows("mapStargates.jsonl"):
            pos = g["position"]
            gates.setdefault(g["solarSystemID"], []).append([g["destination"]["solarSystemID"], round(pos["x"]), round(pos["y"]), round(pos["z"])])
        self.status["progress"] = 96
        missing = resource_names - set(by_en)
        if missing:
            raise RuntimeError(tr("SDE に資源が見つかりません: {0}", (', '.join(sorted(missing)))))

        # PI の段階: P0 = どのレシピの出力でもない入力。P1 以降は入力の最大段階 + 1
        outputs = {s["output"][0]: s for s in schematics.values()}
        tiers = {}

        def tier(t):
            if t not in tiers:
                s = outputs.get(t)
                tiers[t] = 0 if s is None else 1 + max(tier(i) for i, _ in s["inputs"])
            return tiers[t]
        for t in outputs:
            tier(t)

        return {
            "version": DATA_VERSION, "build": meta.get("buildNumber"), "release": meta.get("releaseDate"),
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "blueprints": blueprints, "product_bp": product_bp, "schematics": schematics, "names": names,
            "volumes": volumes, "planet_types": planet_types, "pi_tiers": tiers, "npc_factions": npc_factions,
            "systems": systems, "regions": regions, "variants": variants, "gates": gates,
            "agents": agents, "stations": stations, "corp_names": corp_names, "loc_names": loc_names,
            "planet_resources": {k: [by_en[n] for n in v] for k, v in PLANET_RESOURCES.items()},
        }
