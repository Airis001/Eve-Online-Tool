🌐 [English](README.md) · [日本語](README.ja.md) · **Deutsch** · [Français](README.fr.md) · [Español](README.es.md) · [Русский](README.ru.md) · [한국어](README.ko.md) · [中文](README.zh.md)

# EVE Tool (EVE Online Skill-Checker)

Ein Tool, das Skills, Assets, Wallet und mehr deiner EVE-Online-Charaktere aus ESI liest. So siehst du an einem Ort, welche Schiffe und Fits du fliegen kannst, was du als Nächstes trainieren solltest und wo du ISK verdienen kannst.
Es ist eine Web-App im Browser – auf deinem eigenen PC, als Desktop-App (.exe) oder in der Cloud.

## Funktionen

| Bereich | Funktionen |
|---|---|
| Skills | Skill-Checker (benötigte Skills und Trainingszeit für Schiffe und Module), Skill-Liste, Attributverteilung |
| Fits | Empfohlene Fits und Schiffe, PvE-/PvP-Fits, Fitting-Tool (PG-, CPU- und DPS-Richtwerte), Fit-Vergleich |
| ISK | Markt, Wallet, Assets, Schätzung, Stationshandel, Hub-Transport, PLEX & Store, LP-Auszahlung (ISK/LP und Volumen) |
| Industrie | Fertigung und Reaktionen, PI (planetare Industrie): Übersicht und Layout-Planung |
| Reisen & Aufklärung | Sichere Routen und Autopilot-Zeit, Vertriebsmissionen, Wurmlöcher, Signaturen, Local / D-Scan / Abschüsse |

Füge mehrere Charaktere hinzu und prüfe sie gemeinsam.

Die Oberfläche gibt es auf Japanisch, Englisch, Deutsch, Französisch, Spanisch, Russisch, Koreanisch und Chinesisch. Die Sprache wählst du im „🌐“-Menü der Navigation (beim ersten Besuch wird die Sprache deines Browsers verwendet). Schiffs- und Modulnamen werden wie im Spiel angezeigt (auf Englisch, wenn es keinen Namen in der Sprache gibt).

## Download (Windows)

Lade die ZIP-Datei unter [Releases](https://github.com/Airis001/Eve-Online-Tool/releases/latest) herunter, entpacke sie und starte `EVE Tool.exe`. Python wird nicht benötigt.
Erscheint beim ersten Start „Der Computer wurde durch Windows geschützt“, wähle „Weitere Informationen“ → „Trotzdem ausführen“ (die App ist nicht signiert).

## Aus dem Quellcode starten

Voraussetzung: Python 3 (getestet mit 3.14; unter Windows der Befehl `py`)

1. Erstelle eine Anwendung unter https://developers.eveonline.com/.
   - Callback URL: `http://localhost:8080/callback`
   - Scopes: wähle die für die gewünschten Funktionen (siehe die Zeilen mit `SCOPE_` in [fetch_skills.py](fetch_skills.py)).
     Der Skill-Checker funktioniert schon mit `esi-skills.read_skills.v1` und `esi-skills.read_skillqueue.v1`.
2. Kopiere `.env.example` nach `.env` und trage Client ID und Secret Key deiner Anwendung ein.
3. Installiere die Abhängigkeiten und starte die App.
   ```powershell
   py -m pip install -r requirements.txt
   py app.py
   ```
4. http://localhost:8080 öffnet sich im Browser. Melde dich über „+ Charakter hinzufügen“ bei EVE an.

Der erste Start dauert etwas länger, weil die Liste der Schiffs- und Modulnamen und die statischen Daten von CCP (SDE) heruntergeladen werden.

## Weitere Möglichkeiten

- **Desktop-App (.exe) selbst bauen**: kopiere `desktop.env.example` nach `desktop.env`, trage die Client ID ein und führe `py build_exe.py` aus (siehe [build_exe.py](build_exe.py)).
- **Cloud (vom Smartphone nutzen)**: Fly.io – [DEPLOY.md](DEPLOY.md); VPS – [DEPLOY_CONOHA.md](DEPLOY_CONOHA.md) (beide auf Japanisch).
  Nur wer den Einladungscode kennt, kann ein Konto erstellen; die Daten jedes Kontos werden getrennt und verschlüsselt gespeichert.

## Deine Daten

- Charakter-Anmeldungen und abgerufene Daten werden nur auf dem PC (oder Server) gespeichert, auf dem die App läuft.
- Einstellungsdateien wie `.env` und Charakterdaten gelangen nicht in Git (siehe [.gitignore](.gitignore)).

## Texte hinzufügen oder ändern

Die Texte der Oberfläche werden auf Japanisch geschrieben; die Übersetzungen liegen in Dateien pro Sprache in [static/i18n/](static/i18n/) (`en.json`, `de.json`, …). Der japanische Satz selbst ist der Schlüssel. Fehlt eine Übersetzung, wird Englisch angezeigt.

- JS: `tr("{0} 星系", n)` schreiben. Für Schiffs- und Modulnamen `nm(item)` verwenden, das den Namen für die aktuelle Sprache wählt.
- Python: Sätze mit Werten als `tr("{0} が見つかりません", name)` schreiben (`from i18n import tr`). Zeichenketten in API-Antworten, die genau einem Schlüssel entsprechen, werden automatisch übersetzt.
- Feste Texte der HTML-Seiten (static/*.html) übersetzt der Server beim Ausliefern.

Führe nach Änderungen `py check_i18n.py` aus, um alle Sprachen auf fehlende Übersetzungen zu prüfen (`py check_i18n.py --missing de` listet die auf Deutsch fehlenden Texte mit englischer Übersetzung).

## Lizenz

[MIT License](LICENSE)

## Copyright-Hinweis

EVE Online and the EVE logo are the registered trademarks of CCP hf. All rights are reserved worldwide. All other trademarks are the property of their respective owners. EVE Online, the EVE logo, EVE and all associated logos and designs are the intellectual property of CCP hf. All artwork, screenshots, characters, vehicles, storylines, world facts or other recognizable features of the intellectual property relating to these trademarks are likewise the intellectual property of CCP hf. CCP hf. has granted permission to this tool to use EVE Online and all associated logos and designs for promotional and information purposes but does not endorse, and is not in any way affiliated with, this tool. CCP is in no way responsible for the content on or functioning of this tool, nor can it be liable for any damage arising from the use of this tool.

Dies ist kein offizielles Tool von CCP hf.
