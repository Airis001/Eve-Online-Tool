"""キャラクターの ESI データ（ウォレット・注文・ジョブ・PI など）を、その場で取得して短時間キャッシュする。"""

import re
import threading
import time

import requests


class ScopeMissing(Exception):
    """キャラクターに必要なスコープが無い（再ログインが必要）。"""

    def __init__(self, scope):
        super().__init__(scope)
        self.scope = scope


class EsiForbidden(Exception):
    """ESI が 403 を返した（コーポレーションの役職が無いなど）。"""


def esi_status(error):
    """「ESI エラー (403) ...」（英語の画面では「ESI error (403) ...」）から HTTP ステータスを取り出す。"""
    m = re.match(r"ESI (?:エラー|error) \((\d+)\)", str(error))
    return int(m[1]) if m else None


class Live:
    def __init__(self, esi_get, esi_get_all_pages, token_fn, scopes_fn, owner_fn=lambda: None):
        """token_fn(char_id) → アクセストークン、scopes_fn(char_id) → 許可済みスコープの一覧。

        owner_fn() → いまのアカウント。キャラクターのデータのキャッシュはアカウントごとに分ける。
        """
        self.esi_get = esi_get
        self.esi_get_all_pages = esi_get_all_pages
        self.token_fn = token_fn
        self.scopes_fn = scopes_fn
        self.owner_fn = owner_fn
        self._cache = {}
        self._lock = threading.Lock()

    def has(self, char_id, scope):
        return scope in self.scopes_fn(char_id)

    def get(self, char_id, path, scope, ttl=300, pages=False, params=None, force=False):
        if scope and not self.has(char_id, scope):
            raise ScopeMissing(scope)
        key = (self.owner_fn(), char_id, path, tuple(sorted((params or {}).items())), pages)
        with self._lock:
            hit = self._cache.get(key)
        if hit and not force and time.time() - hit[0] < ttl:
            return hit[1]
        token = self.token_fn(char_id)
        try:
            data = self.esi_get_all_pages(path, token) if pages else self.esi_get(path, token, params=params)
        except RuntimeError as e:
            if esi_status(e) in (401, 403):
                raise EsiForbidden(str(e).splitlines()[0]) from e
            raise
        with self._lock:
            self._cache[key] = (time.time(), data)
        return data

    def public(self, path, ttl=3600, params=None, force=False):
        """ログイン不要の ESI（キャッシュ付き）。"""
        key = (None, path, tuple(sorted((params or {}).items())), False)
        with self._lock:
            hit = self._cache.get(key)
        if hit and not force and time.time() - hit[0] < ttl:
            return hit[1]
        data = self.esi_get(path, params=params)
        with self._lock:
            self._cache[key] = (time.time(), data)
        return data


def safe(fn, *args, **kwargs):
    """キャラクターごとの取得で、失敗をエラー情報に変える（1 人の失敗で全体を止めない）。

    返り値: (データ, None) または (None, {"needs_scope": ...} / {"error": ...})
    """
    try:
        return fn(*args, **kwargs), None
    except ScopeMissing as e:
        return None, {"needs_scope": e.scope}
    except EsiForbidden as e:
        return None, {"forbidden": str(e)}
    except (RuntimeError, requests.RequestException, KeyError) as e:
        return None, {"error": str(e).splitlines()[0] if str(e) else repr(e)}
