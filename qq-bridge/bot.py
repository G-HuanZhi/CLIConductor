"""QQ Bridge 入口 — 启动 NoneBot2 并加载插件。"""

import nonebot

nonebot.init()
nonebot.load_plugin("plugin")
nonebot.load_adapter("nonebot.adapters.onebot.v11")
nonebot.run()
