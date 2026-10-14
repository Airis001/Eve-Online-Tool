🌐 [English](README.md) · [日本語](README.ja.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [Español](README.es.md) · [Русский](README.ru.md) · **한국어** · [中文](README.zh.md)

# EVE Tool (EVE Online 스킬 체커)

EVE Online 캐릭터의 스킬, 자산, 지갑 등을 ESI에서 불러와 어떤 함선과 피팅을 탈 수 있는지, 다음에 무엇을 훈련할지, 어디서 ISK를 벌 수 있는지를 한곳에서 확인할 수 있는 도구입니다.
브라우저에서 여는 웹 앱으로, 내 PC·데스크톱 앱(.exe)·클라우드 어디서든 실행할 수 있습니다.

## 기능

| 분류 | 기능 |
|---|---|
| 스킬 | 스킬 체커(함선·모듈에 필요한 스킬과 훈련 시간), 스킬 목록, 능력치 재분배 |
| 피팅 | 추천 피팅·함선, PvE / PvP 피팅, 피팅 도구(PG·CPU·DPS 추정), 피팅 비교 |
| ISK | 시장, 지갑, 자산, 감정, 스테이션 트레이딩, 허브 간 운송, PLEX 및 상점, LP 환전(ISK/LP와 거래량) |
| 산업 | 제조·반응, PI(행성 산업) 집계와 배치 계획 |
| 이동·정보 | 안전한 경로와 오토파일럿 소요 시간, 유통 미션, 미션 적의 속성·약점, 웜홀, 시그니처, 로컬 / D-Scan / 격추 |

여러 캐릭터를 등록해 한꺼번에 확인할 수 있습니다.

화면은 일본어·영어·독일어·프랑스어·스페인어·러시아어·한국어·중국어를 지원합니다. 내비게이션의 「🌐」 메뉴에서 언어를 바꿀 수 있습니다(처음 열 때는 브라우저 언어를 사용합니다). 함선·모듈 이름도 게임과 같은 표기로 보여 줍니다(해당 언어 이름이 없으면 영어 이름).

## 다운로드 (Windows)

[Releases](https://github.com/Airis001/Eve-Online-Tool/releases/latest)에서 zip을 내려받아 압축을 풀고 `EVE Tool.exe`를 실행하세요. Python은 필요 없습니다.
처음 실행할 때 「Windows의 PC 보호」가 표시되면 「추가 정보」 → 「실행」을 선택하세요(서명되지 않은 앱이기 때문입니다).

## 소스에서 실행하기

필요한 것: Python 3(3.14에서 확인, Windows에서는 `py` 명령)

1. https://developers.eveonline.com/ 에서 애플리케이션을 만듭니다.
   - Callback URL: `http://localhost:8080/callback`
   - Scopes: 사용할 기능에 맞는 것을 선택합니다([fetch_skills.py](fetch_skills.py)에서 `SCOPE_`로 시작하는 줄 참고).
     스킬 체커는 `esi-skills.read_skills.v1`과 `esi-skills.read_skillqueue.v1`만 있으면 동작합니다.
2. `.env.example`을 `.env`로 복사하고 애플리케이션의 Client ID와 Secret Key를 입력합니다.
3. 의존성을 설치하고 앱을 실행합니다.
   ```powershell
   py -m pip install -r requirements.txt
   py app.py
   ```
4. 브라우저에서 http://localhost:8080 이 열리면 「+ 캐릭터 추가」로 EVE에 로그인합니다.

처음 실행할 때는 함선·모듈 이름 목록과 CCP 정적 데이터(SDE)를 내려받기 때문에 시간이 조금 더 걸립니다.

## 다른 실행 방법

- **데스크톱 앱(.exe) 직접 만들기**: `desktop.env.example`을 `desktop.env`로 복사해 Client ID를 입력하고 `py build_exe.py`를 실행합니다([build_exe.py](build_exe.py) 참고).
- **클라우드(휴대폰에서 사용)**: Fly.io — [DEPLOY.md](DEPLOY.md), VPS — [DEPLOY_CONOHA.md](DEPLOY_CONOHA.md)(둘 다 일본어).
  초대 코드를 아는 사람만 계정을 만들 수 있으며, 각 계정의 데이터는 따로 암호화해 저장합니다.

## 데이터 취급

- 캐릭터 로그인 정보와 가져온 데이터는 앱을 실행하는 PC(또는 서버)에만 저장됩니다.
- `.env` 같은 설정 파일과 캐릭터 데이터는 Git에 들어가지 않도록 되어 있습니다([.gitignore](.gitignore) 참고).

## 화면 문구를 추가하거나 바꿀 때

화면 문구는 일본어로 쓰고, 번역은 [static/i18n/](static/i18n/)의 언어별 파일(`en.json`, `de.json` 등)에 둡니다. 일본어 문장 자체가 키입니다. 어떤 언어에 번역이 없으면 영어로 표시됩니다.

- JS: `tr("{0} 星系", n)`처럼 씁니다. 함선·모듈 이름은 현재 언어에 맞는 이름을 고르는 `nm(item)`을 사용합니다.
- Python: 값을 넣는 문장은 `tr("{0} が見つかりません", name)`(`from i18n import tr`)을 사용합니다. API 응답 중 사전 키와 정확히 일치하는 문자열은 자동으로 번역됩니다.
- HTML 페이지(static/*.html)의 고정 문구는 서버가 페이지를 보낼 때 번역합니다.

문구를 바꾼 뒤에는 `py check_i18n.py`를 실행해 모든 언어에서 빠진 번역이 없는지 확인하세요(`py check_i18n.py --missing ko`로 한국어에 빠진 문구를 영어 번역과 함께 볼 수 있습니다).

## 라이선스

[MIT License](LICENSE)

## 저작권 고지

EVE Online and the EVE logo are the registered trademarks of CCP hf. All rights are reserved worldwide. All other trademarks are the property of their respective owners. EVE Online, the EVE logo, EVE and all associated logos and designs are the intellectual property of CCP hf. All artwork, screenshots, characters, vehicles, storylines, world facts or other recognizable features of the intellectual property relating to these trademarks are likewise the intellectual property of CCP hf. CCP hf. has granted permission to this tool to use EVE Online and all associated logos and designs for promotional and information purposes but does not endorse, and is not in any way affiliated with, this tool. CCP is in no way responsible for the content on or functioning of this tool, nor can it be liable for any damage arising from the use of this tool.

이 도구는 CCP hf.의 공식 도구가 아닙니다.
