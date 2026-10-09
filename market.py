"""指定した場所（NPC ステーション・プレイヤー建造物）のマーケットの注文と価格。

  NPC ステーション: リージョンの注文（/markets/{region_id}/orders/?type_id=）をステーションで絞り込む。ログイン不要。
  プレイヤー建造物: 建造物の注文（/markets/structures/{id}/）を全ページ取得する。
                    esi-markets.structure_markets.v1 と、その建造物へのドッキング権限が必要。
ESI の注文データは約 5 分ごとに更新されるので、取得結果は 5 分間キャッシュする。
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

STATION_IDS = range(60_000_000, 64_000_000)
STRUCTURE_MIN_ID = 1_000_000_000_000
CACHE_SECONDS = 300

# よく使われる取引拠点
TRADE_HUBS = [
    {"id": 60003760, "name": "Jita IV - Moon 4 - Caldari Navy Assembly Plant", "short": "Jita 4-4", "region_id": 10000002},
    {"id": 60008494, "name": "Amarr VIII (Oris) - Emperor Family Academy", "short": "Amarr", "region_id": 10000043},
    {"id": 60011866, "name": "Dodixie IX - Moon 20 - Federation Navy Assembly Plant", "short": "Dodixie", "region_id": 10000032},
    {"id": 60004588, "name": "Rens VI - Moon 8 - Brutor Tribe Treasury", "short": "Rens", "region_id": 10000030},
    {"id": 60005686, "name": "Hek VIII - Moon 12 - Boundless Creation Factory", "short": "Hek", "region_id": 10000042},
]
DEFAULT_LOCATION_ID = TRADE_HUBS[0]["id"]


class MarketError(RuntimeError):
    pass


class Market:
    def __init__(self, esi_get, esi_get_all_pages, structure_tokens, owner_fn=lambda: None):
        """structure_tokens(): 建造物のマーケットを読めるキャラクターのアクセストークンを順に返す関数。

        owner_fn() → いまのアカウント。建造物の注文（権限が必要）のキャッシュはアカウントごとに分ける。
        """
        self.esi_get = esi_get
        self.esi_get_all_pages = esi_get_all_pages
        self.structure_tokens = structure_tokens
        self.owner_fn = owner_fn
        self._lock = threading.Lock()
        self._orders = {}      # キャッシュ: キー → (取得時刻, 注文)
        self._regions = {hub["id"]: hub["region_id"] for hub in TRADE_HUBS}
        self._names = {hub["id"]: hub["name"] for hub in TRADE_HUBS}

    # ---------- 場所 ----------

    @staticmethod
    def kind(location_id):
        if location_id in STATION_IDS:
            return "station"
        if location_id >= STRUCTURE_MIN_ID:
            return "structure"
        raise MarketError("ステーションかプレイヤー建造物を指定してください。")

    def station_region(self, station_id):
        if station_id not in self._regions:
            station = self.esi_get(f"/universe/stations/{station_id}/")
            system = self.esi_get(f"/universe/systems/{station['system_id']}/")
            constellation = self.esi_get(f"/universe/constellations/{system['constellation_id']}/")
            self._names[station_id] = station["name"]
            self._regions[station_id] = constellation["region_id"]
        return self._regions[station_id]

    def location_name(self, location_id, fallback=None):
        if location_id in self._names:
            return self._names[location_id]
        if self.kind(location_id) == "station":
            self.station_region(location_id)
            return self._names[location_id]
        return fallback or "プレイヤー建造物"

    # ---------- 注文 ----------

    def _cached(self, key, loader):
        with self._lock:
            hit = self._orders.get(key)
            if hit and time.time() - hit[0] < CACHE_SECONDS:
                return hit[1]
        orders = loader()
        with self._lock:
            self._orders[key] = (time.time(), orders)
        return orders

    def _structure_orders(self, structure_id):
        """建造物の全注文。読めるキャラクターが見つかるまで順に試す。"""
        def load():
            tried = False
            for token in self.structure_tokens():
                tried = True
                try:
                    return self.esi_get_all_pages(f"/markets/structures/{structure_id}/", token)
                except RuntimeError:
                    continue  # 403: このキャラクターはドッキング権限・マーケットの閲覧権限がない
            if not tried:
                raise MarketError("プレイヤー建造物のマーケットを見るには、キャラクターの再ログイン（マーケットの権限の許可）が必要です。")
            raise MarketError("この建造物のマーケットを見られるキャラクターがいません（ドッキング権限が必要です）。")
        return self._cached(("structure", structure_id, self.owner_fn()), load)

    def _station_orders(self, station_id, type_id):
        region_id = self.station_region(station_id)
        region_orders = self._cached(
            ("region", region_id, type_id),
            lambda: self.esi_get(f"/markets/{region_id}/orders/", params={"type_id": type_id, "order_type": "all"}),
        )
        return [o for o in region_orders if o["location_id"] == station_id]

    def orders(self, location_id, type_ids):
        """{type_id: [注文, ...]}（その場所の注文だけ）"""
        type_ids = list(dict.fromkeys(type_ids))
        if self.kind(location_id) == "structure":
            wanted = set(type_ids)
            result = {t: [] for t in type_ids}
            for o in self._structure_orders(location_id):
                if o["type_id"] in wanted:
                    result[o["type_id"]].append(o)
            return result
        with ThreadPoolExecutor(max_workers=10) as pool:
            fetched = list(pool.map(lambda t: (t, self._station_orders(location_id, t)), type_ids))
        return dict(fetched)

    def prices(self, location_id, type_ids):
        """{type_id: {"sell": {"price", "volume", "orders"} or None, "buy": {...} or None}}"""
        return {t: summarize(orders) for t, orders in self.orders(location_id, type_ids).items()}


def summarize(orders):
    sells = [o for o in orders if not o["is_buy_order"]]
    buys = [o for o in orders if o["is_buy_order"]]

    def best(side, pick):
        if not side:
            return None
        price = pick(o["price"] for o in side)
        return {
            "price": price,
            "volume": sum(o["volume_remain"] for o in side if o["price"] == price),  # 最良価格で買える・売れる数
            "total_volume": sum(o["volume_remain"] for o in side),
            "orders": len(side),
        }

    return {"sell": best(sells, min), "buy": best(buys, max)}


def order_view(orders, limit=50):
    """注文一覧の表示用（売りは安い順、買いは高い順）。"""
    def row(o):
        return {"price": o["price"], "volume": o["volume_remain"], "min_volume": o.get("min_volume", 1),
                "range": o.get("range"), "issued": o.get("issued"), "duration": o.get("duration")}
    sells = sorted((o for o in orders if not o["is_buy_order"]), key=lambda o: o["price"])
    buys = sorted((o for o in orders if o["is_buy_order"]), key=lambda o: -o["price"])
    return {"sell": [row(o) for o in sells[:limit]], "buy": [row(o) for o in buys[:limit]],
            "sell_count": len(sells), "buy_count": len(buys)}
