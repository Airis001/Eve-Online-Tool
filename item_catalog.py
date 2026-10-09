"""艦・装備の名前一覧（英語名・日本語名）と検索。

ESI には公開の部分一致検索がないため、初回に対象カテゴリの全アイテムを取得して
item_catalog.json に保存する。同時に必要スキル情報を TypeCache に入れておき、判定を速くする。
"""

import json
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor

from paths import DATA_DIR
from skill_check import type_info

CATALOG_FILE = DATA_DIR / "item_catalog.json"

# ESI のカテゴリ ID → 表示名（検索結果とチェックリストの見出しに使う）
CATEGORIES = {
    6: "艦船",
    7: "モジュール",
    18: "ドローン",
    87: "ファイター",
    32: "サブシステム",
    8: "弾薬・チャージ",
    20: "インプラント・ブースター",
    # マーケットの相場比較用
    4: "鉱物・素材",
    25: "鉱石",
    43: "PI 資材",
    17: "交易品",
    16: "スキルブック",
    5: "PLEX・インジェクター",
}
CATEGORY_ORDER = list(CATEGORIES.values())
CATALOG_VERSION = 2  # CATEGORIES を変えたら上げる（古い一覧は裏で作り直す）


def normalize(text):
    """検索用の正規化: 全角英数→半角、小文字化、ひらがな→カタカナ。"""
    text = unicodedata.normalize("NFKC", text).lower()
    return "".join(chr(ord(ch) + 0x60) if "ぁ" <= ch <= "ゖ" else ch for ch in text)


class ItemCatalog:
    def __init__(self, esi_get, esi_post, path=CATALOG_FILE):
        self.esi_get = esi_get
        self.esi_post = esi_post
        self.path = path
        self.items = []
        self.by_id = {}
        self.by_name = {}
        self.progress = {"status": "missing", "done": 0, "total": 0, "error": None}
        self.outdated = False  # 古い版の一覧（検索には使えるが、作り直しが必要）
        self._lock = threading.Lock()
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            saved = None
        if isinstance(saved, list):  # 版番号の無い最初の形式
            self._set_items(saved)
            self.outdated = True
        elif isinstance(saved, dict):
            self._set_items(saved.get("items", []))
            self.outdated = saved.get("version") != CATALOG_VERSION

    def _set_items(self, items):
        for item in items:
            item["_search"] = normalize(item["en"]) + "\n" + normalize(item["ja"])
        self.items = items
        self.by_id = {item["id"]: item for item in items}
        self.by_name = {}
        for item in items:
            self.by_name.setdefault(normalize(item["en"]), item["id"])
            self.by_name.setdefault(normalize(item["ja"]), item["id"])
        self.progress = {"status": "ready", "done": len(items), "total": len(items), "error": None}

    @property
    def ready(self):
        """検索に使える一覧があるか（作り直し中でも、古い一覧があれば True）。"""
        return bool(self.items)

    @property
    def status(self):
        return {**self.progress, "searchable": self.ready}

    # ---------- 構築 ----------

    def build_async(self, type_cache, on_done=None):
        """バックグラウンドで一覧を作る（すでに作成中なら何もしない）。"""
        with self._lock:
            if self.progress["status"] == "building":
                return
            self.progress = {"status": "building", "done": 0, "total": 0, "error": None}
        threading.Thread(target=self._build, args=(type_cache, on_done), daemon=True).start()

    def _build(self, type_cache, on_done):
        try:
            groups = []
            for cat_id, cat_name in CATEGORIES.items():
                category = self.esi_get(f"/universe/categories/{cat_id}/")
                with ThreadPoolExecutor(max_workers=10) as pool:
                    for group in pool.map(lambda g: self.esi_get(f"/universe/groups/{g}/"), category["groups"]):
                        if group.get("published"):
                            groups.append((cat_name, group))

            type_ids = [t for _, g in groups for t in g["types"]]
            group_of = {t: (cat, g["name"]) for cat, g in groups for t in g["types"]}
            self.progress["total"] = len(type_ids)

            en_names = {}
            for i in range(0, len(type_ids), 1000):
                for entry in self.esi_post("/universe/names/", type_ids[i:i + 1000]):
                    en_names[entry["id"]] = entry["name"]

            # 日本語名は型情報を 1 件ずつ取得するしかない。ついでに必要スキルもキャッシュする
            def fetch(type_id):
                return type_id, self.esi_get(f"/universe/types/{type_id}/", params={"language": "ja"})

            items = []
            with ThreadPoolExecutor(max_workers=20) as pool:
                for type_id, data in pool.map(fetch, type_ids):
                    self.progress["done"] += 1
                    if not data.get("published"):
                        continue
                    en = en_names.get(type_id, data["name"])
                    type_cache.put(type_id, type_info(data, name=en))
                    cat, group = group_of[type_id]
                    items.append({"id": type_id, "en": en, "ja": data["name"], "category": cat, "group": group})

            type_cache.save()
            self.path.write_text(json.dumps({"version": CATALOG_VERSION, "items": items}, ensure_ascii=False), encoding="utf-8")
            self.outdated = False
            self._set_items(items)
            if on_done:
                on_done()
        except Exception as e:  # noqa: BLE001 - 失敗理由を画面に出す
            self.progress = {**self.progress, "status": "error", "error": str(e).splitlines()[0]}

    # ---------- 検索 ----------

    def search(self, query, limit=30):
        # 空白区切りの語をすべて含むものを探す（例: "シールド エクステンダー"）
        words = normalize(query).split()
        if not words or not self.ready:
            return []
        q = " ".join(words)
        scored = []
        for item in self.items:
            if not all(w in item["_search"] for w in words):
                continue
            en, ja = normalize(item["en"]), normalize(item["ja"])
            if q in (en, ja):
                rank = 0
            elif en.startswith(q) or ja.startswith(q):
                rank = 1
            else:
                rank = 2
            scored.append((rank, CATEGORY_ORDER.index(item["category"]), len(item["en"]), item))
        scored.sort(key=lambda s: s[:3])
        return [public(s[3]) for s in scored[:limit]]

    def get(self, type_id):
        item = self.by_id.get(type_id)
        return public(item) if item else None

    def find_by_name(self, name):
        """英語名・日本語名の完全一致（大文字小文字・全角半角・ひらがなは区別しない）→ type_id。"""
        return self.by_name.get(normalize(name))


def public(item):
    return {k: v for k, v in item.items() if not k.startswith("_")}
