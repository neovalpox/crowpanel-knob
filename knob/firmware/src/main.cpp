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
//                  "Z<rétroéclairage> <leds 0|1> <horloge 0|1>"  veille
//                  "J<w> <h> <len>" + octets RGB565 LE  image caméra ; "j" la masque
//                  "Y<nom>\t<pour mille>\t<valeur>\t<rrggbb>\t<indice>"  tuile Hue
//   module -> PC : "H" (bonjour), "Q<tuile>", "R<crans>", "C" (clic), "L" (appui long)
#include <Arduino.h>
#include "USBHIDConsumerControl.h"
#include "hw.h"
#include "ui.h"

#define SYNC_TIMEOUT_MS 5000
#define ICON_MAX (96 * 96 * 3)
#define CAM_SIZE 160

static char line[256];
static int lineLen = 0;
static unsigned long lastRx = 0;
static bool synced = false;

// Double tampon : on reçoit dans l'un pendant que LVGL affiche l'autre.
static uint8_t iconData[2][ICON_MAX];
static lv_img_dsc_t iconDsc[2];
static int iconBack = 0;
static bool iconPending = false;

// Image caméra : un seul tampon, la réception bloque la boucle LVGL donc pas de déchirure.
static uint8_t camData[CAM_SIZE * CAM_SIZE * 2];
static lv_img_dsc_t camDsc;

static bool readExact(uint8_t *dst, int len) {
  int got = 0;
  unsigned long t0 = millis();
  while (got < len && millis() - t0 < 1000) {
    int n = usbSerial.read(dst + got, len - got);
    if (n > 0) got += n; else delay(1);
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

static void receiveCamera(int w, int h, int len) {
  if (w != CAM_SIZE || h != CAM_SIZE || len != (int)sizeof camData) return;
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
      int bl, leds, clock;
      if (sscanf(s, "Z%d %d %d", &bl, &leds, &clock) == 3) uiSetSleep(bl, leds != 0, clock != 0);
      break;
    }
    case 'Y':
      if (splitFields(s + 1, f, 5) == 5) uiSetHue(f[0], atoi(f[1]), f[2], strtoul(f[3], nullptr, 16), f[4]);
      break;
  }
}

static void pollLink() {
  while (usbSerial.available()) {
    char c = usbSerial.read();
    lastRx = millis();
    if (c == '\n') {
      line[lineLen] = 0;
      handleLine(line);
      lineLen = 0;
    } else if (lineLen < (int)sizeof(line) - 1) {
      line[lineLen++] = c;
    }
  }
  bool nowSynced = millis() - lastRx < SYNC_TIMEOUT_MS && lastRx != 0;
  if (nowSynced != synced) {
    synced = nowSynced;
    uiSetSynced(synced);
    if (synced) usbSerial.printf("H\nQ%d\nM%u\n", (int)uiTile(), (unsigned)ESP.getFreeHeap());
  }
}

static void handleKnob() {
  int steps = hwTakeEncoderSteps();
  if (steps != 0) {
    uiKnobFeedback(steps);
    // Sur la tuile volume, ou sans PC, la molette pilote le volume en HID.
    if (uiTile() == TILE_VOL || !synced) {
      for (int i = 0; i < abs(steps); i++)
        hwSendMediaKey(steps > 0 ? CONSUMER_CONTROL_VOLUME_INCREMENT : CONSUMER_CONTROL_VOLUME_DECREMENT);
    } else {
      usbSerial.printf("R%d\n", steps);  // le PC sait sur quelle tuile on est (Q)
    }
  }

  ButtonEvent b = hwPollButton();
  if (b == BTN_NONE) return;
  lv_disp_trig_activity(NULL);
  uiWake();
  if (b == BTN_CLICK && uiNotifyVisible()) {
    uiNotifyDismiss();
  } else if (uiTile() == TILE_VOL || !synced) {
    if (b == BTN_CLICK) hwSendMediaKey(CONSUMER_CONTROL_MUTE);
  } else {
    usbSerial.print(b == BTN_CLICK ? "C\n" : "L\n");
  }
}

void setup() {
  hwBegin();
  uiBegin();
  uiSetSynced(false);
}

void loop() {
  pollLink();
  handleKnob();
  uiTick();
  lv_timer_handler();
  delay(2);
}
