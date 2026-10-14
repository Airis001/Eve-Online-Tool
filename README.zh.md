🌐 [English](README.md) · [日本語](README.ja.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [Español](README.es.md) · [Русский](README.ru.md) · [한국어](README.ko.md) · **中文**

# EVE Tool（EVE Online 技能检查器）

从 ESI 读取你的 EVE Online 角色的技能、资产、钱包等数据，在一个地方查看你能驾驶哪些舰船和装配、接下来该训练什么，以及在哪里赚 ISK。
这是一个在浏览器中打开的 Web 应用，可以在自己的电脑上、作为桌面应用（.exe）或在云端运行。

## 功能

| 分类 | 功能 |
|---|---|
| 技能 | 技能检查器（舰船和装备所需的技能与训练时间）、技能列表、属性重新分配 |
| 装配 | 推荐装配和舰船、PvE / PvP 装配、装配工具（PG、CPU、DPS 估算）、装配对比 |
| ISK | 市场、钱包、资产、估价、空间站交易、星系枢纽间运输、PLEX 与商店、LP 兑现（ISK/LP 与成交量） |
| 工业 | 制造与反应、PI（行星开发）汇总与布局规划 |
| 移动与情报 | 安全路线与自动导航时间、配送任务、任务敌人的伤害类型与弱点、虫洞、信号、本地 / D-Scan / 击毁 |

可以添加多个角色并一起查看。

界面支持日语、英语、德语、法语、西班牙语、俄语、韩语和中文。在导航栏的“🌐”菜单中切换语言（首次打开时使用浏览器的语言）。舰船和装备名称与游戏中的写法一致（该语言没有名称时显示英文名）。

## 下载（Windows）

从 [Releases](https://github.com/Airis001/Eve-Online-Tool/releases/latest) 下载 zip，解压后运行 `EVE Tool.exe`。无需安装 Python。
首次启动如果出现“Windows 已保护你的电脑”，请选择“更多信息”→“仍要运行”（因为应用没有签名）。

## 从源码运行

需要：Python 3（已在 3.14 上测试；Windows 上使用 `py` 命令）

1. 在 https://developers.eveonline.com/ 创建应用。
   - Callback URL：`http://localhost:8080/callback`
   - Scopes：选择所需功能对应的权限（参见 [fetch_skills.py](fetch_skills.py) 中以 `SCOPE_` 开头的行）。
     技能检查器只需要 `esi-skills.read_skills.v1` 和 `esi-skills.read_skillqueue.v1` 即可使用。
2. 将 `.env.example` 复制为 `.env`，填入应用的 Client ID 和 Secret Key。
3. 安装依赖并启动应用。
   ```powershell
   py -m pip install -r requirements.txt
   py app.py
   ```
4. 浏览器会打开 http://localhost:8080，点击“+ 添加角色”登录 EVE。

首次启动需要下载舰船和装备名称列表以及 CCP 的静态数据（SDE），所以会稍慢一些。

## 其他运行方式

- **自行构建桌面应用（.exe）**：将 `desktop.env.example` 复制为 `desktop.env`，填入 Client ID，然后运行 `py build_exe.py`（参见 [build_exe.py](build_exe.py)）。
- **云端（用手机访问）**：Fly.io — [DEPLOY.md](DEPLOY.md)；VPS — [DEPLOY_CONOHA.md](DEPLOY_CONOHA.md)（均为日语）。
  只有知道邀请码的人才能创建账户，每个账户的数据分别加密保存。

## 你的数据

- 角色的登录信息和获取的数据只保存在运行应用的电脑（或服务器）上。
- `.env` 等设置文件和角色数据不会进入 Git（参见 [.gitignore](.gitignore)）。

## 添加或修改界面文字

界面文字用日语编写，译文放在 [static/i18n/](static/i18n/) 中按语言分开的文件里（`en.json`、`de.json` 等）。日语句子本身就是键。某种语言缺少译文时显示英文。

- JS：写成 `tr("{0} 星系", n)`。舰船和装备名称使用 `nm(item)`，它会选择当前语言的名称。
- Python：带有值的句子使用 `tr("{0} が見つかりません", name)`（`from i18n import tr`）。API 响应中与词典键完全一致的字符串会自动翻译。
- HTML 页面（static/*.html）中的固定文字由服务器在发送页面时翻译。

修改文字后，运行 `py check_i18n.py` 检查所有语言是否有缺失的译文（`py check_i18n.py --missing zh` 会列出中文缺少的文字及其英文译文）。

## 许可证

[MIT License](LICENSE)

## 版权声明

EVE Online and the EVE logo are the registered trademarks of CCP hf. All rights are reserved worldwide. All other trademarks are the property of their respective owners. EVE Online, the EVE logo, EVE and all associated logos and designs are the intellectual property of CCP hf. All artwork, screenshots, characters, vehicles, storylines, world facts or other recognizable features of the intellectual property relating to these trademarks are likewise the intellectual property of CCP hf. CCP hf. has granted permission to this tool to use EVE Online and all associated logos and designs for promotional and information purposes but does not endorse, and is not in any way affiliated with, this tool. CCP is in no way responsible for the content on or functioning of this tool, nor can it be liable for any damage arising from the use of this tool.

本工具不是 CCP hf. 的官方工具。
