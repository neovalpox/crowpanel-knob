// CrowPanel Knob : macro-pad rond.
// Protocole série (lignes texte, champs séparés par des tabulations) avec knob_companion.py :
//   PC -> module : "V<vol> M<0|1>"                      volume général
//                  "I<w> <h> <len>" + <len> octets       icône (RGB565 LE + alpha)
//                  "A<nom>\t<mode>\t<rrggbb>\t<indice>"  app au premier plan
//                  "a<vol> M<0|1>"                      volume de l'app
//                  "T<ligne1>\t<ligne2>"                textes (titre/artiste, imprimante/détails)
//                  "P<pour mille>\t<texte>"             jauge + texte central (MEDIA/PROGRESS)
//                  "C<rrggbb>"                          nouvelle couleur d'accent
//                  "U"                                  applique l'icône reçue sans transition
//                  "F<texte>"                           flash d'un symbole géant
//                  "N<symbole>\t<titre>\t<sous-titre>\t<rrggbb>"  alerte plein écran
//                  "K<secondes depuis minuit>\t<date>"  horloge
//                  "W<temp>\t<description>"             météo
//                  "E<texte>" / "S<texte>\t<rrggbb>"    prochain événement / ligne d'état
//                  "Z<rétroéclairage> <leds 0|1> <horloge 0|1> [<plafond LEDs>]"  veille / nuit
//                  "J<w> <h> <len>" + octets RGB565 LE  image caméra ; "j" la masque
//                  "Y<nom>\t<pour mille>\t<valeur>\t<rrggbb>\t<indice>"  tuile Hue
//                  "G<cpu>	<gpu>	<ram>	<temp gpu>"  tuile système (-1 = indisponible)
//                  "D<nom>"                             sortie audio courante
//                  "O#<n>" puis "O<i>	<libellé>	<rrggbb>	<symbole>"  lanceur radial
//                  "o<i> <w> <h> <len>" + octets         icône du raccourci i (RGB565 + alpha)
//                  "Q<tuile> <ms app> <ms autres>"      écran d'accueil et délais de retour
//                  "e<0|1>"                             mode dédié média (verrouillage)
//                  "k<titre>\t<artiste>\t<rrggbb>\t<‰>\t<0|1 lecture>"  morceau en mode dédié
//                  "u"                                  applique l'icône reçue comme pochette du mode dédié
//                  "v<25 car.>"                         spectre : 24 bandes + basse, '0' + niveau 0..63
//                  "y<tuile> <masque>"                  molette/clic/appui long gérés par le module (bits 1/2/4)
//                  "n<symbole>\t<titre>\t<sous-titre>\t<rrggbb>"  alerte silencieuse (historique)
//                  "m<0|1|2>\t<app>"                    réunion : aucune / micro ouvert / coupé
//                  "B<‰ desc.>\t<débit desc.>\t<‰ mont.>\t<débit mont.>"  tuile réseau
//                  "X<id>\t<titre>\t<détail>\t<LIB,rrggbb|...>"  question à choix ; "x<id>" la ferme
//                  "w=<ssid>\t<mot de passe>\t<clé hex>" / "w-"   Wi-Fi : configurer / oublier (USB seulement)
//                  "w?" (scan) ; "w!" (état)
//                  "!<taille>\t<md5>" + octets         nouveau firmware (mise à jour sans fil)
//   module -> PC : "H" (bonjour), "Q<tuile>", "R<crans>", "C" (clic), "L" (appui long),
//                  "x<id> <index>" (réponse, -1 = rendre la main au terminal), "o<i>" (raccourci lancé),
//                  "T" (triple clic : ouvrir l'éditeur), "k<usage hex>" (touche multimédia à appuyer
//                  par le PC, en Wi-Fi), "wi<état>	<ssid>	<ip>	<rssi>", "ws<rssi>	<ssid>", "w." (fin du scan),
//                  "!ok" / "!err <raison>" (mise à jour)
// La même liaison passe par l'USB (CDC) ou par le Wi-Fi (TCP, voir net.h).
#include <Arduino.h>
#include "USBHIDConsumerControl.h"
#include <Update.h>
#include "hw.h"
#include "net.h"
#include "ui.h"

#define SYNC_TIMEOUT_MS 5000
#define ICON_MAX (96 * 96 * 3)
#define CAM_SIZE 160

// Une ligne en cours de réception par liaison ; les réponses partent sur la dernière
// liaison qui a parlé (le compagnon utilise l'USB ou le Wi-Fi, pas les deux).
struct LineBuf {
  char text[256];
  int len;
};
static LineBuf usbLine, netLine;
static Stream *out = &usbSerial;  // liaison des réponses
static Stream *rxSrc = &usbSerial;  // liaison de la commande en cours
static bool outNet = false, rxNet = false;
static unsigned long lastRx = 0;
static bool synced = false;

// Par tuile : ce que le module gère lui-même (sinon envoyé au PC, qui applique le profil
// de la tuile). Bits : molette, clic, appui long. Réglé par le PC ("y<tuile> <masque>").
#define LOCAL_KNOB 1
#define LOCAL_CLICK 2
#define LOCAL_LONG 4
static uint8_t tileLocal[8] = {
    0,                         // app : tout passe par le PC (profil de l'app)
    LOCAL_KNOB | LOCAL_CLICK,  // volume : volume HID + mute ; appui long = choix de sortie (PC)
    LOCAL_KNOB | LOCAL_CLICK,  // tableau de bord : clic = historique
    0, 0, 0, 0, 0};

static bool isLocal(Tile t, uint8_t what) { return !synced || (tileLocal[t] & what); }


// Double tampon : on reçoit dans l'un pendant que LVGL affiche l'autre.
static uint8_t iconData[2][ICON_MAX];
static lv_img_dsc_t iconDsc[2];
static int iconBack = 0;
static bool iconPending = false;

// Image caméra : un seul tampon, la réception bloque la boucle LVGL donc pas de déchirure.
#define CAM_BYTES (CAM_SIZE * CAM_SIZE * 2)
static uint8_t *camData;  // en PSRAM : la RAM interne reste au Wi-Fi
static lv_img_dsc_t camDsc;

// Icônes du lanceur radial
#define RAD_MAX 8
#define RAD_ICON 32
#define RAD_BYTES (RAD_ICON * RAD_ICON * 3)
static uint8_t *radIconData[RAD_MAX];

static uint8_t *bigAlloc(size_t n) {
  void *p = heap_caps_malloc(n, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  return (uint8_t *)(p ? p : malloc(n));
}

static void allocBuffers() {
  camData = bigAlloc(CAM_BYTES);
  for (int i = 0; i < RAD_MAX; i++) radIconData[i] = bigAlloc(RAD_BYTES);
}
static lv_img_dsc_t radIconDsc[RAD_MAX];

// Lit len octets sur la liaison qui a envoyé la commande en cours (USB ou Wi-Fi).
static bool readExact(uint8_t *dst, int len, unsigned long timeoutMs = 1000) {
  int got = 0;
  unsigned long t0 = millis();
  while (got < len && millis() - t0 < timeoutMs) {
    int avail = rxSrc->available();
    int n = avail > 0 ? rxSrc->readBytes(dst + got, min(avail, len - got)) : 0;
    if (n > 0) {
      got += n;
      t0 = millis();
    } else {
      delay(1);
    }
  }
  return got == len;
}

static void receiveIcon(int w, int h, int len) {
  if (len != w * h * 3 || len > ICON_MAX) return;
  uint8_t *dst = iconData[iconBack];
  if (!readExact(dst, len)) return;
  lv_img_dsc_t &d = iconDsc[iconBack];
  memset(&d, 0, sizeof d);
  d.header.cf = LV_IMG_CF_TRUE_COLOR_ALPHA;
  d.header.w = w;
  d.header.h = h;
  d.data_size = len;
  d.data = dst;
  iconPending = true;
}

static void receiveLauncherIcon(int idx, int w, int h, int len) {
  if (idx < 0 || idx >= RAD_MAX || w != RAD_ICON || h != RAD_ICON || len != RAD_BYTES) return;
  if (!readExact(radIconData[idx], len)) return;
  lv_img_dsc_t &d = radIconDsc[idx];
  memset(&d, 0, sizeof d);
  d.header.cf = LV_IMG_CF_TRUE_COLOR_ALPHA;
  d.header.w = w;
  d.header.h = h;
  d.data_size = len;
  d.data = radIconData[idx];
  uiLauncherIcon(idx, &d);
}

static void receiveCamera(int w, int h, int len) {
  if (w != CAM_SIZE || h != CAM_SIZE || len != CAM_BYTES) return;
  if (!readExact(camData, len)) return;
  memset(&camDsc, 0, sizeof camDsc);
  camDsc.header.cf = LV_IMG_CF_TRUE_COLOR;
  camDsc.header.w = w;
  camDsc.header.h = h;
  camDsc.data_size = len;
  camDsc.data = camData;
  uiShowCamera(&camDsc);
}

// Découpe s (après la lettre de commande) en champs séparés par des tabulations.
static int splitFields(char *s, char **fields, int max) {
  int n = 0;
  fields[n++] = s;
  while (n < max && (s = strchr(s, '\t'))) {
    *s++ = 0;
    fields[n++] = s;
  }
  return n;
}

static void receiveFirmware(int size, const char *md5);
static bool mirrorOn = false;  // l'éditeur 3D du PC affiche l'écran réel ("s1" / "s0")

static void handleLine(char *s) {
  int v, m, w, h, len;
  char *f[6];
  switch (s[0]) {
    case 'V':
      if (sscanf(s, "V%d M%d", &v, &m) == 2) uiSetMaster(v, m != 0);
      break;
    case 'a':
      if (sscanf(s, "a%d M%d", &v, &m) == 2) uiSetAppValue(v, m != 0);
      break;
    case 'I':
      if (sscanf(s, "I%d %d %d", &w, &h, &len) == 3) receiveIcon(w, h, len);
      break;
    case 'J':
      if (sscanf(s, "J%d %d %d", &w, &h, &len) == 3) receiveCamera(w, h, len);
      break;
    case 'j':
      uiHideCamera();
      break;
    case 'A': {
      if (splitFields(s + 1, f, 4) != 4) return;
      const char *mode = f[1];
      AppMode am = !strcmp(mode, "appvol")                              ? MODE_APPVOL
                   : !strcmp(mode, "scroll") || !strcmp(mode, "keys")   ? MODE_SCROLL
                   : !strcmp(mode, "media")                             ? MODE_MEDIA
                   : !strcmp(mode, "progress")                          ? MODE_PROGRESS
                                                                        : MODE_MASTER;
      const lv_img_dsc_t *icon = nullptr;
      if (iconPending) {
        icon = &iconDsc[iconBack];
        iconBack ^= 1;
        iconPending = false;
      }
      uiSetApp(f[0], am, strtoul(f[2], nullptr, 16), f[3], icon);
      break;
    }
    case 'T':
      if (splitFields(s + 1, f, 2) == 2) uiSetTexts(f[0], f[1]);
      break;
    case 'P':
      if (splitFields(s + 1, f, 2) == 2) uiSetProgress(atoi(f[0]), f[1]);
      break;
    case 'C':
      uiSetColor(strtoul(s + 1, nullptr, 16));
      break;
    case 'U':
      if (iconPending) {
        uiUpdateIcon(&iconDsc[iconBack]);
        iconBack ^= 1;
        iconPending = false;
      }
      break;
    case 'F':
      uiFlash(s + 1);
      break;
    case 'N':
      if (splitFields(s + 1, f, 4) == 4) uiNotify(f[0], f[1], f[2], strtoul(f[3], nullptr, 16));
      break;
    case 'K':
      if (splitFields(s + 1, f, 2) == 2) uiSetClock(atol(f[0]), f[1]);
      break;
    case 'W':
      if (splitFields(s + 1, f, 2) == 2) uiSetWeather(f[0], f[1]);
      break;
    case 'E':
      uiSetEvent(s + 1);
      break;
    case 'S':
      if (splitFields(s + 1, f, 2) == 2) uiSetStatus(f[0], strtoul(f[1], nullptr, 16));
      break;
    case 'Z': {
      int bl, leds, clock, ledMax = 255;
      if (sscanf(s, "Z%d %d %d %d", &bl, &leds, &clock, &ledMax) >= 3) uiSetSleep(bl, leds != 0, clock != 0, ledMax);
      break;
    }
    case 'Q': {
      int tile, appMs, otherMs;
      if (sscanf(s, "Q%d %d %d", &tile, &appMs, &otherMs) == 3) uiSetHome((Tile)tile, appMs, otherMs);
      break;
    }
    case 'e':
      uiMediaLock(s[1] == '1');
      break;
    case 'k':
      if (splitFields(s + 1, f, 5) == 5)
        uiMediaInfo(f[0], f[1], strtoul(f[2], nullptr, 16), atoi(f[3]), f[4][0] == '1');
      break;
    case 'u':
      if (iconPending) {
        uiMediaCover(&iconDsc[iconBack]);
        iconBack ^= 1;
        iconPending = false;
      }
      break;
    case 'v': {
      // 24 bandes + basse, chacune codée '0' + niveau (0..63).
      uint8_t bands[24];
      int n = 0;
      for (const char *p = s + 1; *p && n < 25; p++, n++) {
        int level = *p - '0';
        if (n < 24) bands[n] = constrain(level, 0, 63);
        else uiSetSpectrum(bands, 24, constrain(level, 0, 63));
      }
      break;
    }
    case 'y': {
      int tile, mask;
      if (sscanf(s, "y%d %d", &tile, &mask) == 2 && tile >= 0 && tile < 8) tileLocal[tile] = mask;
      break;
    }
    case 'n':
      if (splitFields(s + 1, f, 4) == 4) uiNotifySilent(f[0], f[1], f[2], strtoul(f[3], nullptr, 16));
      break;
    case 'm':
      if (splitFields(s + 1, f, 2) == 2) uiSetMeeting(atoi(f[0]), f[1]);
      break;
    case 'G': {
      int cpu, gpu, ram, temp;
      if (sscanf(s, "G%d %d %d %d", &cpu, &gpu, &ram, &temp) == 4) uiSetSystem(cpu, gpu, ram, temp);
      break;
    }
    case 'D':
      uiSetAudioDevice(s + 1);
      break;
    case 'O':
      if (s[1] == '#') {
        uiLauncherReset(atoi(s + 2));
      } else if (splitFields(s + 1, f, 4) == 4) {
        uiLauncherSet(atoi(f[0]), f[1], strtoul(f[2], nullptr, 16), f[3]);
      }
      break;
    case 'o': {
      int idx;
      if (sscanf(s, "o%d %d %d %d", &idx, &w, &h, &len) == 4) receiveLauncherIcon(idx, w, h, len);
      break;
    }
    case 'B':
      if (splitFields(s + 1, f, 4) == 4) uiSetNet(atoi(f[0]), f[1], atoi(f[2]), f[3]);
      break;
    case 'X':
      if (splitFields(s + 1, f, 4) == 4) uiAsk(atoi(f[0]), f[1], f[2], f[3]);
      break;
    case 'x':
      if (atoi(s + 1) == uiAskId()) uiAskClose();
      break;
    case 'Y':
      if (splitFields(s + 1, f, 5) == 5) uiSetHue(f[0], atoi(f[1]), f[2], strtoul(f[3], nullptr, 16), f[4]);
      break;
    case 'w':
      // Wi-Fi : identifiants modifiables seulement depuis l'USB (pas par le réseau lui-même).
      if (s[1] == '?') {
        netScan(*out);
      } else if (s[1] == '=' && !rxNet) {
        // Redémarrage après enregistrement : le Wi-Fi repart proprement (un changement à chaud
        // laissait la liaison décrocher toutes les 20 à 40 s).
        if (splitFields(s + 2, f, 3) == 3 && netConfigure(f[0], f[1], f[2])) {
          out->print("wi1\t\t\t0\n");
          out->flush();
          delay(200);
          ESP.restart();
        }
        netStatus(*out);
      } else if (s[1] == '-' && !rxNet) {
        netForget();
        uiSetLinkSymbol(LV_SYMBOL_USB);
        netStatus(*out);
      } else if (s[1] == '!') {
        netStatus(*out);
      }
      break;
    case '!':
      if (splitFields(s + 1, f, 2) == 2) receiveFirmware(atoi(f[0]), f[1]);
      break;
    case 's':
      hwMirrorEnable(s[1] == '1');
      mirrorOn = s[1] == '1';
      break;
  }
}

// Bonjour au compagnon : tuile affichée + diagnostic (tas, PSRAM, cause du dernier redémarrage).
static void sendHello() {
  out->printf("H\nQ%d\nM%u psram=%u reset=%d uptime=%lus\n", (int)uiTile(), (unsigned)ESP.getFreeHeap(),
              (unsigned)ESP.getFreePsram(), (int)esp_reset_reason(), millis() / 1000);
}

static void pollStream(Stream *s, LineBuf &b, bool net) {
  while (s->available()) {
    char c = s->read();
    lastRx = millis();
    if (c == '\n') {
      b.text[b.len] = 0;
      b.len = 0;
      rxSrc = s;
      rxNet = net;
      out = s;
      outNet = net;
      handleLine(b.text);
    } else if (b.len < (int)sizeof(b.text) - 1) {
      b.text[b.len++] = c;
    }
  }
}

static void pollLink() {
  pollStream(&usbSerial, usbLine, false);
  netLoop();
  static uint32_t gen = 0;
  WiFiClient *nc = netClient();
  if (nc && netGeneration() != gen) {
    // Nouveau compagnon en Wi-Fi : il devient la liaison des réponses.
    gen = netGeneration();
    netLine.len = 0;
    mirrorOn = false;  // le nouveau compagnon le redemandera si son éditeur est ouvert
    hwMirrorEnable(false);
    out = nc;
    outNet = true;
    lastRx = millis();
    sendHello();
  }
  static unsigned long lastBeat = 0;
  if (nc && millis() - lastBeat > 2000) {  // le PC détecte ainsi un module débranché
    lastBeat = millis();
    nc->print("p\n");
  }
  if (nc) pollStream(nc, netLine, true);
  else if (outNet) {  // client Wi-Fi perdu : retour sur l'USB
    out = rxSrc = &usbSerial;
    outNet = rxNet = false;
  }
  bool nowSynced = millis() - lastRx < SYNC_TIMEOUT_MS && lastRx != 0;
  if (nowSynced != synced) {
    synced = nowSynced;
    uiSetSynced(synced);
    if (synced) sendHello();
  }
}

// Miroir de l'écran : envoie la zone modifiée, compressée par plages, au plus ~8 fois par seconde
// en USB, ~5 en Wi-Fi. Format : "s<x> <y> <w> <h> <octets>" puis les données ; chaque bloc
// commence par un octet n : n >= 128 -> (n - 127) fois le pixel qui suit, sinon n + 1 pixels bruts.
static void sendMirror() {
  static unsigned long last = 0;
  static uint8_t *pack = nullptr;  // pire cas : tout en pixels bruts + un octet par bloc de 128
  if (!mirrorOn || !synced || !hwMirror || hwMirrorX1 > hwMirrorX2) return;
  if (!pack && !(pack = bigAlloc(240 * 240 * 2 + 240 * 240 / 128 + 16))) return;
  // Cadence adaptée : si l'envoi précédent a bloqué (Wi-Fi encombré), on espace les images.
  static unsigned long interval = 120;
  if (millis() - last < interval) return;
  last = millis();
  int x1 = hwMirrorX1, y1 = hwMirrorY1, x2 = hwMirrorX2, y2 = hwMirrorY2;
  hwMirrorX1 = 1;
  hwMirrorX2 = 0;
  int w = x2 - x1 + 1, h = y2 - y1 + 1, n = w * h, len = 0, i = 0;
  auto px = [&](int k) { return hwMirror[(y1 + k / w) * 240 + x1 + k % w]; };
  while (i < n) {
    uint16_t c = px(i);
    int run = 1;
    while (i + run < n && run < 128 && px(i + run) == c) run++;
    if (run >= 3) {
      pack[len++] = 127 + run;
      pack[len++] = c & 0xFF;
      pack[len++] = c >> 8;
      i += run;
      continue;
    }
    // Pixels bruts jusqu'à la prochaine plage d'au moins 3 pixels identiques.
    int start = i, lit = 0;
    while (i < n && lit < 128) {
      uint16_t v = px(i);
      if (i + 2 < n && px(i + 1) == v && px(i + 2) == v) break;
      i++;
      lit++;
    }
    pack[len++] = lit - 1;
    for (int k = start; k < start + lit; k++) {
      uint16_t v = px(k);
      pack[len++] = v & 0xFF;
      pack[len++] = v >> 8;
    }
  }
  out->printf("s%d %d %d %d %d\n", x1, y1, w, h, len);
  unsigned long t0 = millis();
  out->write(pack, len);
  unsigned long took = millis() - t0, base = outNet ? 200 : 120;
  interval = took > 150 ? min(2000UL, interval * 2) : max(base, interval - interval / 4);
}

// Touches multimédia : en Wi-Fi, c'est le PC qui les appuie (pas d'USB HID vers lui).
static bool mediaKeyOverNet(uint16_t usage) {
  if (!outNet || !synced) return false;
  out->printf("k%X\n", usage);
  return true;
}

// Nouveau firmware envoyé par le PC (en Wi-Fi) : écrit dans l'autre partition puis redémarre.
static void receiveFirmware(int size, const char *md5) {
  if (size <= 0 || !Update.begin(size)) {
    out->printf("!err %s\n", Update.errorString());
    return;
  }
  if (strlen(md5) == 32) Update.setMD5(md5);
  static uint8_t chunk[4096];
  int done = 0, shown = -1;
  while (done < size) {
    int n = min((int)sizeof chunk, size - done);
    if (!readExact(chunk, n, 30000) || Update.write(chunk, n) != (size_t)n) break;
    done += n;
    // Accusé tous les 16 Ko : le PC n'envoie jamais plus de 32 Ko d'avance (pas de file
    // d'attente qui déborde pendant les effacements de flash, où le Wi-Fi marque des pauses).
    if (done % 16384 == 0 || done == size) out->printf("!a%d\n", done);
    int pct = (long long)done * 100 / size;
    if (pct != shown) {
      shown = pct;
      uiFirmwareProgress(pct);
      lv_timer_handler();
    }
  }
  if (done == size && Update.end()) {
    out->print("!ok\n");
    uiFirmwareProgress(100);
    lv_timer_handler();
    delay(500);
    ESP.restart();
  }
  Update.abort();
  out->printf("!err %s a %d/%d\n", done == size ? Update.errorString() : "reception", done, size);
  uiFirmwareProgress(-1);
  // Le reste du binaire arriverait comme des commandes : on coupe, le PC se reconnectera.
  if (rxNet) netDrop();
}

// Triple clic : le PC ouvre l'éditeur de profils dans le navigateur.
static void openEditor() {
  if (!synced) return;
  out->print("T\n");
  uiFlash(LV_SYMBOL_SETTINGS);
}

static void handleKnob() {
  int steps = hwTakeEncoderSteps();
  // Lanceur radial ouvert : la molette choisit, le clic lance, l'appui long ferme.
  if (uiLauncherVisible()) {
    if (steps) uiLauncherRotate(steps);
    ButtonEvent b = hwPollButton();
    if (b == BTN_CLICK || b == BTN_DOUBLE || b == BTN_TRIPLE) {
      out->printf("o%d\n", uiLauncherIndex());
      uiLauncherClose();
      uiFlash(LV_SYMBOL_OK);
    } else if (b == BTN_LONG) {
      uiLauncherClose();
    }
    return;
  }
  // Historique ouvert : la molette fait défiler, un clic ou un appui long ferme.
  if (uiHistoryVisible()) {
    if (steps) {
      uiWake();
      uiHistoryRotate(steps);
    }
    if (hwPollButton() != BTN_NONE) uiHistoryClose();
    return;
  }
  // Une question est affichée : la molette lui appartient.
  if (uiAskVisible()) {
    if (steps) {
      uiWake();
      uiAskRotate(steps);
    }
    ButtonEvent b = hwPollButton();
    if (b != BTN_NONE) {
      out->printf("x%d %d\n", uiAskId(), b == BTN_LONG ? -1 : uiAskIndex());
      uiAskClose();
    }
    return;
  }
  // Mode dédié média : tout part au PC (suivant/précédent, lecture, appui long = déverrouiller).
  if (uiMediaLocked()) {
    if (steps) {
      uiWake();
      out->printf("R%d\n", steps);
    }
    ButtonEvent b = hwPollButton();
    if (b == BTN_TRIPLE) {
      openEditor();
    } else if (b != BTN_NONE && b != BTN_LONG && uiNotifyVisible()) {
      uiNotifyDismiss();
    } else if (b != BTN_NONE) {
      out->print(b == BTN_LONG ? "L\n" : "C\n");  // double clic = un seul play/pause
    }
    return;
  }
  Tile t = uiTile();
  if (steps != 0) {
    uiKnobFeedback(steps);
    if (isLocal(t, LOCAL_KNOB)) {
      // Comportement propre à la tuile : volume HID sur la tuile volume (et sans PC).
      if (t == TILE_VOL || !synced)
        for (int i = 0; i < abs(steps); i++)
          hwSendMediaKey(steps > 0 ? CONSUMER_CONTROL_VOLUME_INCREMENT : CONSUMER_CONTROL_VOLUME_DECREMENT);
    } else {
      out->printf("R%d\n", steps);  // le PC sait sur quelle tuile on est (Q)
    }
  }

  ButtonEvent b = hwPollButton();
  if (b == BTN_NONE) return;
  lv_disp_trig_activity(NULL);
  uiWake();
  if (b == BTN_TRIPLE) {
    openEditor();
    return;
  }
  if (b != BTN_LONG && uiNotifyVisible()) {
    uiNotifyDismiss();
    return;
  }
  // Un double clic garde le comportement de deux clics (ex. deux onglets plus loin).
  int repeat = b == BTN_DOUBLE ? 2 : 1;
  if (b == BTN_DOUBLE) b = BTN_CLICK;
  uint8_t what = b == BTN_CLICK ? LOCAL_CLICK : LOCAL_LONG;
  for (int i = 0; i < repeat; i++) {
    if (!isLocal(t, what)) {
      out->print(b == BTN_CLICK ? "C\n" : "L\n");
    } else if (b == BTN_CLICK && (t == TILE_VOL || !synced)) {
      hwSendMediaKey(CONSUMER_CONTROL_MUTE);
    } else if (b == BTN_CLICK && t == TILE_DASH && i == 0) {
      uiHistoryOpen();  // clic sur le tableau de bord : historique des alertes
    }
  }
}

void setup() {
  hwBegin();
  allocBuffers();
  uiBegin();
  uiSetSynced(false);
  hwMediaKeyHook = mediaKeyOverNet;
  uiSendHook = [](const char *msg) {
    if (synced) out->print(msg);
  };
  netBegin();
  if (netConfigured()) uiSetLinkSymbol(LV_SYMBOL_WIFI);
}

// Diagnostic : toutes les 2 s, pire temps de rendu LVGL, mémoire LVGL libre et tas libre.
static void reportPerf(unsigned long renderMs) {
  static unsigned long worst = 0, last = 0, frames = 0;
  worst = max(worst, renderMs);
  frames++;
  if (millis() - last < 2000) return;
  lv_mem_monitor_t mon;
  lv_mem_monitor(&mon);
  if (synced && (uiMediaLocked() || worst > 80))
    out->printf("M%u lv=%u frag=%u%% rendu_max=%lums boucles=%lu refr=%u px_max=%u refr_ms_max=%u anims=%u\n",
                     (unsigned)ESP.getFreeHeap(), (unsigned)mon.free_size, (unsigned)mon.frag_pct, worst, frames,
                     (unsigned)hwRefrCount, (unsigned)hwRefrPx, (unsigned)hwRefrMs,
                     (unsigned)lv_anim_count_running());
  hwRefrCount = hwRefrPx = hwRefrMs = 0;
  worst = 0;
  frames = 0;
  last = millis();
}

void loop() {
  pollLink();
  handleKnob();
  uiTick();
  unsigned long t0 = millis();
  lv_timer_handler();
  reportPerf(millis() - t0);
  sendMirror();
  // Tuile affichée : signalée au PC sur la liaison active (glissement ou retour automatique).
  static int lastTile = -1;
  if (synced && (int)uiTile() != lastTile) {
    lastTile = uiTile();
    out->printf("Q%d\n", lastTile);
  }
  delay(2);
}
