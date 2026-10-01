# CrowPanel Knob

Macro-pad rond pour PC, basé sur l'**Elecrow CrowPanel 1.28" ESP32-S3 Rotary Display**
(écran IPS rond 240×240, tactile, molette crantée cliquable, 5 LEDs RGB).

L'écran s'adapte à la fenêtre au premier plan : vraie icône de l'app, couleur d'accent
extraite de l'icône, et une molette qui fait ce qu'il faut selon l'app.

## Fonctionnalités

- **Tuile application** : icône + halo + anneau à la couleur de l'app, LEDs qui respirent.
- **Tuile volume** (glisser vers la gauche) : volume général Windows synchronisé en temps réel,
  molette = volume, clic = mute. Retour auto après 8 s ou au changement de fenêtre.
- **Widgets**
  - *Média* (Spotify, VLC) : titre, artiste, pochette ronde, avancement du morceau ;
    molette = piste suivante/précédente, clic = play/pause, appui long = volume de l'app.
  - *Bambu Lab* (Bambu Studio) : progression, temps restant, couches, état de l'imprimante,
    en MQTT local (découverte SSDP + codes d'accès lus dans Bambu Studio).
  - *Claude Code* (Windows Terminal) : statut des sessions (au travail / attend ta réponse /
    terminé) via un hook ; molette = flèches, clic = Entrée, appui long = Échap.
- **Tableau de bord** (3e tuile) : horloge avec anneau des secondes, date, météo (Open-Meteo),
  prochain rendez-vous Outlook, ligne d'état (impression en cours, Claude qui attend).
- **Tuile Philips Hue** (4e tuile) : molette = luminosité de la pièce, clic = on/off,
  appui long = pièce suivante, anneau à la couleur réelle des lampes. Association : clic sur la
  tuile puis bouton du pont (clé stockée dans `knob/pc/hue.json`, hors git).
- **Alertes globales** : fin/échec/pause d'impression, Claude qui attend ou a terminé — bulle
  plein écran et LEDs qui clignotent, quelle que soit l'app ; clic ou tap pour fermer.
- **Veille** : écran tamisé + horloge quand la session est verrouillée ou après 10 min
  d'inactivité, quasi éteint et LEDs coupées la nuit ; molette ou toucher = réveil.
- **Caméra Bambu** (X1 / H2D) : appui long dans Bambu Studio, image ronde à 3 i/s dans
  l'anneau de progression (ffmpeg requis).
- **Profils par app** (Chrome, Discord, Outlook, Teams, Telegram, WhatsApp, Mattermost…),
  surchargeables à chaud dans `knob/pc/profiles.json`.
- Sans PC, le module reste un bouton de volume USB HID autonome.

## Structure

```
knob/firmware/   Firmware PlatformIO (Arduino + LVGL 8.3)
  src/hw.*       Écran GC9A01, tactile CST816D, molette (interruptions), LEDs, USB TinyUSB
  src/ui.*       Interface LVGL (tuiles, animations, widgets)
  src/main.cpp   Boucle + protocole série
knob/pc/         Compagnon Windows (Python)
  knob_companion.py  Fenêtre active, icônes, profils, actions
  media.py           Lecteurs média (API Windows GSMTC)
  bambu.py           Imprimantes Bambu Lab (SSDP + MQTT local)
  claude_hook.py     Hook Claude Code -> ~/.claude/knob_status.json
mount/           Support 3D pour Keychron K10 Max (OpenSCAD + STL)
```

## Installation

### Firmware

```powershell
cd knob/firmware
pio run -t upload
```

Le module expose un périphérique USB composite (HID consumer control + CDC série) avec son
propre PID (`303A:4C4B`). Le flash se fait sans toucher au module : reset 1200 bauds, puis
`post_upload.py` efface le drapeau `FORCE_DOWNLOAD_BOOT` pour relancer le firmware.
Ajuster `upload_port` dans `platformio.ini` (port COM du module).

### Compagnon PC

```powershell
cd knob/pc
python -m venv .venv
.venv\Scripts\python -m pip install pycaw pyserial psutil pillow numpy icoextract pywin32 "paho-mqtt>=2" `
    winrt-runtime winrt-Windows.Media.Control winrt-Windows.Foundation `
    winrt-Windows.Foundation.Collections winrt-Windows.Storage.Streams
.venv\Scripts\pythonw knob_companion.py
```

Pour le lancer au démarrage : raccourci vers `.venv\Scripts\pythonw.exe knob_companion.py`
dans `shell:startup`.

### Statut Claude Code (optionnel)

Ajouter dans `~/.claude/settings.json`, sur les événements `UserPromptSubmit`, `PreToolUse`,
`PermissionRequest`, `Notification`, `Stop` et `SessionEnd` :

```json
{ "hooks": [{ "type": "command", "async": true, "timeout": 10,
              "command": "python \"<chemin>\\knob\\pc\\claude_hook.py\"" }] }
```

## Protocole série

| Sens | Message | Rôle |
|---|---|---|
| PC → module | `V<vol> M<0\|1>` | volume général |
| | `I<w> <h> <len>` + octets | icône RGB565 LE + alpha |
| | `A<nom>\t<mode>\t<rrggbb>\t<indice>` | app au premier plan (`master`, `appvol`, `scroll`, `keys`, `media`, `progress`) |
| | `a<vol> M<0\|1>` | volume de l'app |
| | `T<ligne1>\t<ligne2>` / `P<‰>\t<texte>` / `C<rrggbb>` / `U` / `F<symbole>` | widgets |
| module → PC | `R<crans>` / `C` / `L` / `H` | molette, clic, appui long, bonjour |

## Pièges connus

- Le CDC TinyUSB n'émet que si le PC active **DTR** (le compagnon l'active, sans RTS).
- Ne jamais ouvrir le port `303A:1001` (USB-JTAG du bootloader) : ça bloque le module en mode flash.
