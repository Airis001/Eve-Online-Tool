"""アカウント（ユーザー名とパスワード）と、アカウントごとのデータの置き場所。

APP_PASSWORD（招待コード）を設定して公開しているときだけ使う。設定していないとき（自分の PC で使うとき）は
アカウントなしで、データは今まで通り DATA_DIR の直下に置く。

  users.json      アカウントの一覧
  users/<id>/     そのアカウントのキャラクターのログイン情報・スキル・保存したフィットなど（暗号化して保存）

アカウントのデータは、アカウントごとの鍵で暗号化する。鍵そのものはパスワードで暗号化して users.json に置くので、
パスワードを知らないと（サーバーのファイルを見られる管理者でも）中身は読めない。
サインイン中は、鍵をブラウザーのクッキー（セッション）に持たせ、リクエストのあいだだけサーバーのメモリーに置く。
パスワードを忘れると、そのアカウントのデータは誰にも読めなくなる。
"""

import base64
import concurrent.futures
import contextvars
import datetime as dt
import hashlib
import hmac
import json
import os
import re
import secrets
import threading

from cryptography.fernet import Fernet, InvalidToken

from i18n import tr
from paths import DATA_DIR

USERS_FILE = DATA_DIR / "users.json"
USERS_DIR = DATA_DIR / "users"
# アカウントごとに分けるデータ（これ以外のキャッシュ類は全員で共有する）
USER_FILES = [".eve_tokens.json", "groups.json", "saved_fits.json", "market_watchlist.json", "targets.json",
              "pi_layouts.json", "sig_log.json", "nes_offers.json"]
USER_DIRS = ["skills"]

NAME_PATTERN = re.compile(r"[A-Za-z0-9_-]{3,20}")
MIN_PASSWORD = 8

_lock = threading.Lock()
_users = None  # [{"id", "name", "salt", "key", "created_at"}]
_current = contextvars.ContextVar("account_id", default=None)
_key = contextvars.ContextVar("account_key", default=None)


# ---------- いまのリクエストのアカウント ----------

def set_current(uid, key=None):
    _current.set(uid)
    _key.set(key)


def current_uid():
    """サインイン中のアカウントの ID（アカウントなしで使っているときは None）。"""
    return _current.get()


def user_dir():
    uid = current_uid()
    return USERS_DIR / uid if uid else DATA_DIR


def user_file(name):
    """いまのアカウントのデータのファイル。アカウントなしのときは、DATA_DIR の直下のふつうのファイル。"""
    path, key = user_dir() / name, _key.get()
    return UserFile(path, key) if key else path


class UserFile:
    """アカウントのデータのファイル（Path の代わり）。そのアカウントの鍵で暗号化して読み書きする。

    フォルダーの中のファイル名（キャラクター名が入る）も、鍵が無いと分からない名前に置き換える。
    """

    def __init__(self, path, key):
        self.path = path
        self.key = key

    @property
    def name(self):
        return self.path.name

    def __truediv__(self, name):
        hidden = hmac.new(self.key.encode(), name.encode(), "sha256").hexdigest()[:32]
        return UserFile(self.path / hidden, self.key)

    def exists(self):
        return self.path.exists()

    def mkdir(self, **kwargs):
        self.path.mkdir(**kwargs)

    def read_text(self, encoding="utf-8"):
        try:
            return Fernet(self.key).decrypt(self.path.read_bytes()).decode(encoding)
        except InvalidToken as e:  # 壊れている・別の鍵で書かれている → 無いものとして扱う
            raise FileNotFoundError(tr("{0} を読めません", self.path.name)) from e

    def write_text(self, text, encoding="utf-8"):
        # 書いている途中で止まっても（更新での再起動など）元のファイルが壊れないよう、別名で書いてから入れ替える
        tmp = self.path.with_name(f"{self.path.name}.{secrets.token_hex(4)}.tmp")
        tmp.write_bytes(Fernet(self.key).encrypt(text.encode(encoding)))
        os.replace(tmp, self.path)


class ThreadPoolExecutor(concurrent.futures.ThreadPoolExecutor):
    """スレッドの中でも、どのアカウントのリクエストかが分かる ThreadPoolExecutor。"""

    def submit(self, fn, /, *args, **kwargs):
        return super().submit(contextvars.copy_context().run, fn, *args, **kwargs)


# ---------- アカウントの一覧 ----------

def _load():
    global _users
    if _users is None:
        try:
            _users = json.loads(USERS_FILE.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            _users = []
    return _users


def _save():
    # 書いている途中で止まっても一覧が壊れないよう、別名で書いてから入れ替える
    tmp = USERS_FILE.with_name(USERS_FILE.name + ".tmp")
    tmp.write_text(json.dumps(_users, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, USERS_FILE)


def get(uid):
    with _lock:
        return next((u for u in _load() if u["id"] == uid), None) if uid else None


def _find(name):
    return next((u for u in _load() if u["name"].lower() == name.lower()), None)


def _password_key(password, salt):
    """パスワードから作る鍵（データの鍵を暗号化するのに使う）。"""
    return base64.urlsafe_b64encode(hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32))


def _wrap(password, key):
    """データの鍵をパスワードで暗号化したもの（users.json に置く）。"""
    salt = os.urandom(16)
    return {"salt": base64.b64encode(salt).decode(),
            "key": Fernet(_password_key(password, salt)).encrypt(key.encode()).decode()}


def _inherit(target, key):
    """最初のアカウントは、アカウントなしで使っていたときのデータ（DATA_DIR の直下）を引き継ぐ。"""
    for name in USER_FILES:
        if (DATA_DIR / name).is_file():
            UserFile(target / name, key).write_text((DATA_DIR / name).read_text(encoding="utf-8"))
    for name in USER_DIRS:
        if (DATA_DIR / name).is_dir():
            folder = UserFile(target / name, key)
            folder.mkdir()
            for src in (DATA_DIR / name).iterdir():
                if src.is_file():
                    (folder / src.name).write_text(src.read_text(encoding="utf-8"))


def check_new_password(password):
    if len(password) < MIN_PASSWORD:
        raise ValueError(tr("パスワードは {0} 文字以上にしてください。", MIN_PASSWORD))


def create(name, password):
    """アカウントを作り、(アカウント, データの鍵) を返す。入力に問題があれば ValueError（メッセージは画面に出す）。"""
    if not NAME_PATTERN.fullmatch(name):
        raise ValueError("ユーザー名は、半角の英数字と _ - で 3〜20 文字にしてください。")
    check_new_password(password)
    with _lock:
        users = _load()
        if _find(name):
            raise ValueError(tr("「{0}」というユーザー名はすでに使われています。", name))
        key = Fernet.generate_key().decode()
        user = {"id": secrets.token_hex(8), "name": name, **_wrap(password, key),
                "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        target = USERS_DIR / user["id"]
        target.mkdir(parents=True)
        if not users:
            _inherit(target, key)
        users.append(user)
        _save()
    return user, key


def check(name, password):
    """ユーザー名とパスワードが合っていれば (アカウント, データの鍵)。ちがえば None。"""
    with _lock:
        user = _find(name)
    if not user:
        return None
    try:
        key = Fernet(_password_key(password, base64.b64decode(user["salt"]))).decrypt(user["key"].encode()).decode()
    except InvalidToken:
        return None
    return user, key


def set_password(uid, password):
    """パスワードを変える（データの鍵はそのまま、新しいパスワードで暗号化し直す）。"""
    check_new_password(password)
    with _lock:
        user = next(u for u in _load() if u["id"] == uid)
        user.update(_wrap(password, _key.get()))
        _save()
