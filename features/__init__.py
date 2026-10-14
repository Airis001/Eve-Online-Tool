"""追加機能（お金・生産・PI・移動・ゲームの操作）の API。app.py から register() で登録する。"""

from . import assets_todo, distribution, fitbuilder, haul, industry, lp, missions, money, nes, planets, signals, skilllist, tools, tradebuild, travel
from .common import Ctx


def register(app, ctx: Ctx):
    for module in (money, industry, planets, travel, tradebuild, fitbuilder, skilllist, signals, tools, assets_todo, nes, haul, distribution, lp, missions):
        module.register(app, ctx)
