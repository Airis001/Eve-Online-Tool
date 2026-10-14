🌐 [English](README.md) · [日本語](README.ja.md) · [Deutsch](README.de.md) · **Français** · [Español](README.es.md) · [Русский](README.ru.md) · [한국어](README.ko.md) · [中文](README.zh.md)

# EVE Tool (vérificateur de compétences EVE Online)

Un outil qui lit depuis l'ESI les compétences, actifs, portefeuille et plus de vos personnages EVE Online, pour voir au même endroit quels vaisseaux et fits vous pouvez piloter, quoi entraîner ensuite et où gagner des ISK.
C'est une application web qui s'ouvre dans le navigateur — sur votre PC, en application de bureau (.exe) ou dans le cloud.

## Fonctionnalités

| Domaine | Fonctionnalités |
|---|---|
| Compétences | Vérificateur (compétences et temps d'entraînement requis pour vaisseaux et modules), liste des compétences, remap d'attributs |
| Fits | Fits et vaisseaux recommandés, fits PvE / PvP, outil d'équipement (estimations PG, CPU et DPS), comparaison de fits |
| ISK | Marché, portefeuille, actifs, estimation, commerce en station, transport entre hubs, PLEX et boutique, conversion des LP (ISK/LP et volume) |
| Industrie | Fabrication et réactions, PI (industrie planétaire) : totaux et planification des dispositions |
| Voyage et renseignements | Routes sûres et temps de pilote automatique, missions de distribution, dégâts et faiblesses des ennemis de mission, trous de ver, signatures, local / D-Scan / destructions |

Ajoutez plusieurs personnages et consultez-les ensemble.

L'interface existe en japonais, anglais, allemand, français, espagnol, russe, coréen et chinois. Changez de langue avec le menu « 🌐 » de la barre de navigation (à la première visite, la langue du navigateur est utilisée). Les noms de vaisseaux et de modules s'affichent comme dans le jeu (en anglais s'il n'existe pas de nom dans la langue).

## Téléchargement (Windows)

Téléchargez le zip depuis [Releases](https://github.com/Airis001/Eve-Online-Tool/releases/latest), extrayez-le et lancez `EVE Tool.exe`. Python n'est pas nécessaire.
Si « Windows a protégé votre ordinateur » apparaît au premier lancement, choisissez « Informations complémentaires » → « Exécuter quand même » (l'application n'est pas signée).

## Lancer depuis les sources

Prérequis : Python 3 (testé avec 3.14 ; sous Windows, commande `py`)

1. Créez une application sur https://developers.eveonline.com/.
   - Callback URL : `http://localhost:8080/callback`
   - Scopes : choisissez ceux des fonctions voulues (voir les lignes commençant par `SCOPE_` dans [fetch_skills.py](fetch_skills.py)).
     Le vérificateur de compétences fonctionne avec seulement `esi-skills.read_skills.v1` et `esi-skills.read_skillqueue.v1`.
2. Copiez `.env.example` vers `.env` et saisissez le Client ID et la Secret Key de votre application.
3. Installez les dépendances et lancez l'application.
   ```powershell
   py -m pip install -r requirements.txt
   py app.py
   ```
4. http://localhost:8080 s'ouvre dans le navigateur. Connectez-vous à EVE avec « + Ajouter un personnage ».

Le premier lancement prend un peu plus de temps, le temps de télécharger la liste des noms de vaisseaux et modules et les données statiques de CCP (SDE).

## Autres façons de l'utiliser

- **Construire soi-même l'application de bureau (.exe)** : copiez `desktop.env.example` vers `desktop.env`, saisissez le Client ID et lancez `py build_exe.py` (voir [build_exe.py](build_exe.py)).
- **Cloud (depuis votre téléphone)** : Fly.io — [DEPLOY.md](DEPLOY.md) ; VPS — [DEPLOY_CONOHA.md](DEPLOY_CONOHA.md) (tous deux en japonais).
  Seules les personnes ayant le code d'invitation peuvent créer un compte, et les données de chaque compte sont stockées séparément et chiffrées.

## Vos données

- Les connexions des personnages et les données récupérées sont stockées uniquement sur le PC (ou serveur) qui exécute l'application.
- Les fichiers de réglages comme `.env` et les données des personnages sont exclus de Git (voir [.gitignore](.gitignore)).

## Ajouter ou modifier des textes

Les textes de l'interface sont écrits en japonais et les traductions se trouvent dans des fichiers par langue dans [static/i18n/](static/i18n/) (`en.json`, `de.json`, …). La phrase japonaise sert de clé. Un texte sans traduction dans une langue s'affiche en anglais.

- JS : écrivez `tr("{0} 星系", n)`. Pour les noms de vaisseaux et modules, utilisez `nm(item)` qui choisit le nom de la langue courante.
- Python : pour les phrases avec des valeurs, utilisez `tr("{0} が見つかりません", name)` (`from i18n import tr`). Les chaînes des réponses de l'API qui correspondent exactement à une clé sont traduites automatiquement.
- Les textes fixes des pages HTML (static/*.html) sont traduits par le serveur à l'envoi de la page.

Après une modification, lancez `py check_i18n.py` pour vérifier les traductions manquantes dans toutes les langues (`py check_i18n.py --missing fr` liste les textes manquants en français, avec la traduction anglaise).

## Licence

[MIT License](LICENSE)

## Mentions de droits d'auteur

EVE Online and the EVE logo are the registered trademarks of CCP hf. All rights are reserved worldwide. All other trademarks are the property of their respective owners. EVE Online, the EVE logo, EVE and all associated logos and designs are the intellectual property of CCP hf. All artwork, screenshots, characters, vehicles, storylines, world facts or other recognizable features of the intellectual property relating to these trademarks are likewise the intellectual property of CCP hf. CCP hf. has granted permission to this tool to use EVE Online and all associated logos and designs for promotional and information purposes but does not endorse, and is not in any way affiliated with, this tool. CCP is in no way responsible for the content on or functioning of this tool, nor can it be liable for any damage arising from the use of this tool.

Cet outil n'est pas un outil officiel de CCP hf.
