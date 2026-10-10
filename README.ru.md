🌐 [English](README.md) · [日本語](README.ja.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [Español](README.es.md) · **Русский** · [한국어](README.ko.md) · [中文](README.zh.md)

# EVE Tool (проверка навыков EVE Online)

Инструмент, который загружает из ESI навыки, имущество, кошелёк и другие данные ваших персонажей EVE Online, чтобы в одном месте видеть, на каких кораблях и с какими фитами вы можете летать, что учить дальше и где заработать ISK.
Это веб-приложение, которое открывается в браузере: на вашем ПК, как настольное приложение (.exe) или в облаке.

## Возможности

| Раздел | Функции |
|---|---|
| Навыки | Проверка навыков (нужные навыки и время обучения для кораблей и модулей), список навыков, перераспределение атрибутов |
| Фиты | Рекомендуемые фиты и корабли, фиты для PvE / PvP, фитинг (оценка PG, CPU и DPS), сравнение фитов |
| ISK | Рынок, кошелёк, имущество, оценка, станционная торговля, перевозки между хабами, PLEX и магазин |
| Производство | Производство и реакции, PI (планетарная индустрия): итоги и планирование размещения |
| Перемещение и разведка | Безопасные маршруты и время автопилота, миссии по доставке, червоточины, сигнатуры, локал / D-Scan / уничтожения |

Добавьте несколько персонажей и просматривайте их вместе.

Интерфейс доступен на японском, английском, немецком, французском, испанском, русском, корейском и китайском. Язык меняется в меню «🌐» на панели навигации (при первом открытии используется язык браузера). Названия кораблей и модулей показываются так же, как в игре (на английском, если перевода на этот язык нет).

## Загрузка (Windows)

Скачайте zip со страницы [Releases](https://github.com/Airis001/Eve-Online-Tool/releases/latest), распакуйте его и запустите `EVE Tool.exe`. Python не нужен.
Если при первом запуске появится «Система Windows защитила ваш компьютер», выберите «Подробнее» → «Выполнить в любом случае» (приложение не подписано).

## Запуск из исходного кода

Требования: Python 3 (проверено на 3.14; в Windows используйте команду `py`)

1. Создайте приложение на https://developers.eveonline.com/.
   - Callback URL: `http://localhost:8080/callback`
   - Scopes: выберите нужные для желаемых функций (см. строки, начинающиеся с `SCOPE_`, в [fetch_skills.py](fetch_skills.py)).
     Для проверки навыков достаточно `esi-skills.read_skills.v1` и `esi-skills.read_skillqueue.v1`.
2. Скопируйте `.env.example` в `.env` и укажите Client ID и Secret Key вашего приложения.
3. Установите зависимости и запустите приложение.
   ```powershell
   py -m pip install -r requirements.txt
   py app.py
   ```
4. В браузере откроется http://localhost:8080. Войдите в EVE через «+ Добавить персонажа».

Первый запуск занимает немного больше времени: загружаются список названий кораблей и модулей и статические данные CCP (SDE).

## Другие способы запуска

- **Собрать настольное приложение (.exe) самостоятельно**: скопируйте `desktop.env.example` в `desktop.env`, укажите Client ID и выполните `py build_exe.py` (см. [build_exe.py](build_exe.py)).
- **Облако (доступ с телефона)**: Fly.io — [DEPLOY.md](DEPLOY.md); VPS — [DEPLOY_CONOHA.md](DEPLOY_CONOHA.md) (оба на японском).
  Создать учётную запись могут только те, у кого есть код приглашения; данные каждой учётной записи хранятся отдельно и в зашифрованном виде.

## Ваши данные

- Входы персонажей и полученные данные хранятся только на ПК (или сервере), где запущено приложение.
- Файлы настроек, такие как `.env`, и данные персонажей не попадают в Git (см. [.gitignore](.gitignore)).

## Добавление и изменение текста интерфейса

Текст интерфейса пишется на японском, а переводы лежат в файлах для каждого языка в [static/i18n/](static/i18n/) (`en.json`, `de.json`, …). Ключом служит сама японская фраза. Если перевода на язык нет, показывается английский.

- JS: пишите `tr("{0} 星系", n)`. Для названий кораблей и модулей используйте `nm(item)` — она выбирает название на текущем языке.
- Python: для фраз со значениями используйте `tr("{0} が見つかりません", name)` (`from i18n import tr`). Строки в ответах API, точно совпадающие с ключом словаря, переводятся автоматически.
- Постоянный текст HTML-страниц (static/*.html) переводит сервер при отдаче страницы.

После изменения текста запустите `py check_i18n.py`, чтобы проверить пропущенные переводы на всех языках (`py check_i18n.py --missing ru` выводит недостающие на русском фразы с английским переводом).

## Лицензия

[MIT License](LICENSE)

## Уведомление об авторских правах

EVE Online and the EVE logo are the registered trademarks of CCP hf. All rights are reserved worldwide. All other trademarks are the property of their respective owners. EVE Online, the EVE logo, EVE and all associated logos and designs are the intellectual property of CCP hf. All artwork, screenshots, characters, vehicles, storylines, world facts or other recognizable features of the intellectual property relating to these trademarks are likewise the intellectual property of CCP hf. CCP hf. has granted permission to this tool to use EVE Online and all associated logos and designs for promotional and information purposes but does not endorse, and is not in any way affiliated with, this tool. CCP is in no way responsible for the content on or functioning of this tool, nor can it be liable for any damage arising from the use of this tool.

Это не официальный инструмент CCP hf.
