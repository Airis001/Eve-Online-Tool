🌐 [English](README.md) · [日本語](README.ja.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · **Español** · [Русский](README.ru.md) · [한국어](README.ko.md) · [中文](README.zh.md)

# EVE Tool (comprobador de habilidades de EVE Online)

Una herramienta que lee desde ESI las habilidades, bienes, cartera y más de tus personajes de EVE Online, para ver en un solo lugar qué naves y fits puedes pilotar, qué entrenar después y dónde ganar ISK.
Es una aplicación web que se abre en el navegador: en tu propio PC, como aplicación de escritorio (.exe) o en la nube.

## Funciones

| Área | Funciones |
|---|---|
| Habilidades | Comprobador (habilidades y tiempo de entrenamiento para naves y módulos), lista de habilidades, remapeo de atributos |
| Fits | Fits y naves recomendados, fits PvE / PvP, herramienta de equipamiento (estimaciones de PG, CPU y DPS), comparación de fits |
| ISK | Mercado, cartera, bienes, tasación, comercio en estación, transporte entre hubs, PLEX y tienda, canje de LP (ISK/LP y volumen) |
| Industria | Fabricación y reacciones, PI (industria planetaria): totales y planificación de distribuciones |
| Viaje e inteligencia | Rutas seguras y tiempo de piloto automático, misiones de distribución, agujeros de gusano, firmas, local / D-Scan / destrucciones |

Añade varios personajes y revísalos juntos.

La interfaz está en japonés, inglés, alemán, francés, español, ruso, coreano y chino. Cambia de idioma con el menú «🌐» de la barra de navegación (en la primera visita se usa el idioma del navegador). Los nombres de naves y módulos aparecen como en el juego (en inglés si no hay nombre en ese idioma).

## Descarga (Windows)

Descarga el zip desde [Releases](https://github.com/Airis001/Eve-Online-Tool/releases/latest), extráelo y ejecuta `EVE Tool.exe`. No hace falta Python.
Si al iniciarlo por primera vez aparece «Windows protegió su PC», elige «Más información» → «Ejecutar de todas formas» (la aplicación no está firmada).

## Ejecutar desde el código fuente

Requisitos: Python 3 (probado con 3.14; en Windows usa el comando `py`)

1. Crea una aplicación en https://developers.eveonline.com/.
   - Callback URL: `http://localhost:8080/callback`
   - Scopes: elige los de las funciones que quieras (mira las líneas que empiezan por `SCOPE_` en [fetch_skills.py](fetch_skills.py)).
     El comprobador de habilidades funciona solo con `esi-skills.read_skills.v1` y `esi-skills.read_skillqueue.v1`.
2. Copia `.env.example` a `.env` y rellena el Client ID y la Secret Key de tu aplicación.
3. Instala las dependencias e inicia la aplicación.
   ```powershell
   py -m pip install -r requirements.txt
   py app.py
   ```
4. Se abre http://localhost:8080 en el navegador. Inicia sesión en EVE con «+ Añadir personaje».

El primer inicio tarda un poco más mientras se descargan la lista de nombres de naves y módulos y los datos estáticos de CCP (SDE).

## Otras formas de usarla

- **Crear tú mismo la aplicación de escritorio (.exe)**: copia `desktop.env.example` a `desktop.env`, rellena el Client ID y ejecuta `py build_exe.py` (consulta [build_exe.py](build_exe.py)).
- **Nube (úsala desde el móvil)**: Fly.io — [DEPLOY.md](DEPLOY.md); VPS — [DEPLOY_CONOHA.md](DEPLOY_CONOHA.md) (ambos en japonés).
  Solo quien tenga el código de invitación puede crear una cuenta, y los datos de cada cuenta se guardan por separado y cifrados.

## Tus datos

- Los inicios de sesión de los personajes y los datos obtenidos se guardan solo en el PC (o servidor) que ejecuta la aplicación.
- Los archivos de configuración como `.env` y los datos de personajes no se incluyen en Git (consulta [.gitignore](.gitignore)).

## Añadir o cambiar textos

Los textos de la interfaz se escriben en japonés y las traducciones están en archivos por idioma en [static/i18n/](static/i18n/) (`en.json`, `de.json`, …). La frase en japonés es la clave. Si falta la traducción en un idioma, se muestra en inglés.

- JS: escribe `tr("{0} 星系", n)`. Para nombres de naves y módulos, usa `nm(item)`, que elige el nombre del idioma actual.
- Python: para frases con valores, usa `tr("{0} が見つかりません", name)` (`from i18n import tr`). Las cadenas de las respuestas de la API que coinciden exactamente con una clave se traducen solas.
- Los textos fijos de las páginas HTML (static/*.html) los traduce el servidor al enviar la página.

Tras cambiar textos, ejecuta `py check_i18n.py` para comprobar las traducciones que faltan en todos los idiomas (`py check_i18n.py --missing es` lista los textos que faltan en español, con la traducción al inglés).

## Licencia

[MIT License](LICENSE)

## Aviso de derechos de autor

EVE Online and the EVE logo are the registered trademarks of CCP hf. All rights are reserved worldwide. All other trademarks are the property of their respective owners. EVE Online, the EVE logo, EVE and all associated logos and designs are the intellectual property of CCP hf. All artwork, screenshots, characters, vehicles, storylines, world facts or other recognizable features of the intellectual property relating to these trademarks are likewise the intellectual property of CCP hf. CCP hf. has granted permission to this tool to use EVE Online and all associated logos and designs for promotional and information purposes but does not endorse, and is not in any way affiliated with, this tool. CCP is in no way responsible for the content on or functioning of this tool, nor can it be liable for any damage arising from the use of this tool.

Esta no es una herramienta oficial de CCP hf.
