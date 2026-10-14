🌐 **English** · [日本語](README.ja.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [Español](README.es.md) · [Русский](README.ru.md) · [한국어](README.ko.md) · [中文](README.zh.md)

# EVE Tool (EVE Online Skill Checker)

A tool that reads your EVE Online characters' skills, assets, wallet and more from ESI, so you can see in one place which ships and fits you can fly, what to train next, and where to make ISK.
It's a web app that runs in your browser — on your own PC, as a desktop app (.exe), or in the cloud.

## Features

| Area | Features |
|---|---|
| Skills | Skill checker (skills and training time needed for ships and modules), skill list, attribute remap |
| Fits | Recommended fits and ships, PvE / PvP fits, fitting tool (PG, CPU and DPS estimates), fit comparison |
| ISK | Market, wallet, assets, appraisal, station trading, hub hauling, PLEX & store, LP cash-out (ISK/LP and volume) |
| Industry | Manufacturing and reactions, PI (planetary industry) totals and layout planning |
| Travel & intel | Safe routes and autopilot time, distribution missions, mission enemy damage types and weaknesses, wormholes, signatures, local / D-Scan / kills |

Add several characters and check them all together.

The UI is available in Japanese, English, German, French, Spanish, Russian, Korean and Chinese. Switch languages from the "🌐" menu in the navigation bar (on first visit, your browser's language is used). Ship and module names are shown as they appear in the game (English when there is no name in that language).

## Download (Windows)

Download the zip from [Releases](https://github.com/Airis001/Eve-Online-Tool/releases/latest), extract it, and run `EVE Tool.exe`. No Python needed.
If "Windows protected your PC" appears on first launch, choose "More info" → "Run anyway" (the app isn't code-signed).

## Running from source

Requirements: Python 3 (tested with 3.14; on Windows use the `py` command)

1. Create an application at https://developers.eveonline.com/.
   - Callback URL: `http://localhost:8080/callback`
   - Scopes: choose the ones for the features you want (see the lines starting with `SCOPE_` in [fetch_skills.py](fetch_skills.py)).
     The skill checker works with just `esi-skills.read_skills.v1` and `esi-skills.read_skillqueue.v1`.
2. Copy `.env.example` to `.env` and fill in your app's Client ID and Secret Key.
3. Install the dependencies and start the app.
   ```powershell
   py -m pip install -r requirements.txt
   py app.py
   ```
4. http://localhost:8080 opens in your browser. Log in to EVE with "+ Add character".

The first start takes a little longer while the ship and module name list and CCP's static data (SDE) are downloaded.

## Other ways to run it

- **Build the desktop app (.exe) yourself**: copy `desktop.env.example` to `desktop.env`, fill in the Client ID, and run `py build_exe.py` (see [build_exe.py](build_exe.py)).
- **Cloud (use it from your phone)**: Fly.io — [DEPLOY.md](DEPLOY.md); VPS — [DEPLOY_CONOHA.md](DEPLOY_CONOHA.md) (both in Japanese).
  Only people with the invite code can create an account, and each account's data is stored separately and encrypted.

## Your data

- Character logins and fetched data are stored only on the PC (or server) running the app.
- Settings files such as `.env` and character data are kept out of Git (see [.gitignore](.gitignore)).

## Adding or changing UI text

UI text is written in Japanese, and translations live in per-language files in [static/i18n/](static/i18n/) (`en.json`, `de.json`, …). The Japanese sentence itself is the key. Text without a translation in a language falls back to English.

- JS: write `tr("{0} 星系", n)`. For ship and module names, use `nm(item)` to pick the name for the current language.
- Python: for sentences with values, use `tr("{0} が見つかりません", name)` (`from i18n import tr`). Strings in API responses that match a dictionary key exactly are translated automatically.
- Fixed text in the HTML pages (static/*.html) is translated by the server when the page is sent.

After changing text, run `py check_i18n.py` to check every language for missing translations (`py check_i18n.py --missing de` lists the text missing in German, with the English translation).

## License

[MIT License](LICENSE)

## Copyright notice

EVE Online and the EVE logo are the registered trademarks of CCP hf. All rights are reserved worldwide. All other trademarks are the property of their respective owners. EVE Online, the EVE logo, EVE and all associated logos and designs are the intellectual property of CCP hf. All artwork, screenshots, characters, vehicles, storylines, world facts or other recognizable features of the intellectual property relating to these trademarks are likewise the intellectual property of CCP hf. CCP hf. has granted permission to this tool to use EVE Online and all associated logos and designs for promotional and information purposes but does not endorse, and is not in any way affiliated with, this tool. CCP is in no way responsible for the content on or functioning of this tool, nor can it be liable for any damage arising from the use of this tool.

This is not an official CCP hf. tool.
