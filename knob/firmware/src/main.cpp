// CrowPanel Knob : macro-pad rond.
// Protocole série (lignes texte) avec knob_companion.py :
//   PC -> module : "V<vol> M<0|1>"                      volume général
//                  "I<w> <h> <len>" + <len> octets       icône (RGB565 LE + alpha)
//                  "A<nom>\t<master|appvol|scroll>\t<rrggbb>\t<indice>"  app au premier plan
//                  "a<vol> M<0|1>"                      volume de l'app
//                  "T<ligne1>\t<ligne2>"                textes (titre/artiste, imprimante/détails)
//                  "P<pour mille>\t<texte>"             jauge + texte central (MEDIA/PROGRESS)
//                  "C<rrggbb>"                          nouvelle couleur d'accent
//                  "U"                                  applique l'icône reçue sans transition
//                  "F<texte>"                           flash d'un symbole géant
//   module -> PC : "H" (bonjour), "R<crans>", "C" (clic), "L" (appui long)
#include <Arduino.h>
#include "USBHIDConsumerControl.h"
#include "hw.h"
#include "ui.h"

#define SYNC_TIMEOUT_MS 5000
#define ICON_MAX (96 * 96 * 3)

static char line[160];
static int lineLen = 0;
static unsigned long lastRx = 0;
static bool synced = false;

// Double tampon : on reçoit dans l'un pendant que LVGL affiche l'autre.
static uint8_t iconData[2][ICON_MAX];
static lv_img_dsc_t iconDsc[2];
static int iconBack = 0;
static bool iconPending = false;

static void receiveIcon(int w, int h, int len) {
  if (len != w * h * 3 || len > ICON_MAX) return;
  uint8_t *dst = iconData[iconBack];
  int got = 0;
  unsigned long t0 = millis();
  while (got < len && millis() - t0 < 1000) {
    int n = usbSerial.read(dst + got, len - got);
    if (n > 0) got += n; else delay(1);
  }
  if (got != len) return;
  lv_img_dsc_t &d = iconDsc[iconBack];
  memset(&d, 0, sizeof d);
  d.header.always_zero = 0;
  d.header.cf = LV_IMG_CF_TRUE_COLOR_ALPHA;
  d.header.w = w;
  d.header.h = h;
  d.data_size = len;
  d.data = dst;
  iconPending = true;
}

static void handleLine(char *s) {
  int v, m, w, h, len;
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
    case 'A': {
      char *name = s + 1;
      char *mode = strchr(name, '\t');
      if (!mode) return;
      *mode++ = 0;
      char *color = strchr(mode, '\t');
      if (!color) return;
      *color++ = 0;
      char *hint = strchr(color, '\t');
      if (!hint) return;
      *hint++ = 0;
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
      uiSetApp(name, am, strtoul(color, nullptr, 16), hint, icon);
      break;
    }
    case 'T': {
      char *second = strchr(s + 1, '\t');
      if (!second) return;
      *second++ = 0;
      uiSetTexts(s + 1, second);
      break;
    }
    case 'P': {
      char *text = strchr(s + 1, '\t');
      if (!text) return;
      *text++ = 0;
      uiSetProgress(atoi(s + 1), text);
      break;
    }
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
    if (synced) usbSerial.print("H\n");
  }
}

static void handleKnob() {
  int steps = hwTakeEncoderSteps();
  if (steps != 0) {
    uiKnobFeedback(steps);
    // Sur la tuile volume, ou sans PC, la molette pilote le volume en HID.
    if (uiOnVolumeTile() || !synced) {
      for (int i = 0; i < abs(steps); i++)
        hwSendMediaKey(steps > 0 ? CONSUMER_CONTROL_VOLUME_INCREMENT : CONSUMER_CONTROL_VOLUME_DECREMENT);
    } else {
      usbSerial.printf("R%d\n", steps);
    }
  }

  ButtonEvent b = hwPollButton();
  if (b == BTN_NONE) return;
  lv_disp_trig_activity(NULL);
  if (uiOnVolumeTile() || !synced) {
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
