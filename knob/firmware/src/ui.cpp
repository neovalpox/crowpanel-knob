#include "ui.h"
#include <Arduino.h>
#include "hw.h"

#define COL_BG 0x000000
#define COL_TRACK 0x1A1D24
#define COL_TEXT 0xF2F4F8
#define COL_DIM 0x7C8494
#define COL_MUTE 0xFF4D5E
#define COL_MASTER 0x22D3EE
#define COL_HUE 0xFFB547
#define ARC_SIZE 228
#define AUTO_RETURN_MS 8000  // Hue -> volume
#define APP_RETURN_MS 5000   // app -> volume (le volume est l'écran d'accueil)
#define NOTIFY_MS 8000
#define WAKE_MS 15000
#define BACKLIGHT_MAX 220
#define TILE_COUNT 6

static lv_obj_t *tv, *tiles[TILE_COUNT];
static lv_obj_t *dots[TILE_COUNT], *usbIcon;

// Tuile application
static lv_obj_t *appContent, *halo, *appIcon, *haloSymbol, *appArc, *appName, *appValue, *appHint;
static lv_obj_t *camBox, *camImg;
static AppMode appMode = MODE_MASTER;
static uint32_t appColor = COL_MASTER;
static int appVolume = -1;
static bool appMuted = false;
static int scrollAngle = 0;
static int appPermille = 0;  // MEDIA / PROGRESS
static char appValueText[32] = "";
static lv_obj_t *flashLabel;

// Tuile volume
static lv_obj_t *volArc, *volNumber, *volSymbol, *volTitle;
static int masterVolume = 0;
static bool masterMuted = false;

// Tableau de bord
static lv_obj_t *secArc, *timeLabel, *dateLabel, *tempLabel, *degRing, *weatherDesc, *eventLabel, *statusLabel;
static long clockBase = -1;  // secondes depuis minuit au moment clockBaseMs
static unsigned long clockBaseMs = 0;
static int shownMinute = -1;

// Réseau
#define COL_DOWN 0x22D3EE
#define COL_UP 0xF472B6
#define NET_POINTS 48
static lv_obj_t *netDownArc, *netUpArc, *netDown, *netUp, *netChart;
static lv_chart_series_t *netDownSeries, *netUpSeries;
static int netDownPermille = 0;

// Mode dédié média : spectre circulaire (24 bandes en miroir = 48 barres) autour de la pochette
#define SPEC_BANDS 24
#define SPEC_INNER 46   // rayon de départ des barres (pochette de 72 px au centre)
#define SPEC_LEN 40     // longueur max d'une barre
#define SPEC_CY -18     // centre vertical de la pochette et du spectre
static lv_obj_t *mediaPanel, *mediaBars, *mediaCover, *mediaProgress, *mediaTitle, *mediaArtist, *mediaPause;
static uint8_t specBands[SPEC_BANDS];
static uint8_t specBass = 0;
static uint32_t mediaColor = 0x1ED760;
static bool mediaLocked = false;

// Système : 4 jauges (CPU, GPU, RAM, température GPU)
static lv_obj_t *sysArc[4], *sysVal[4];
static int sysCpu = 0;

// Lanceur radial
#define RAD_MAX 8
#define RAD_ICON 32
#define RAD_RADIUS 84
static lv_obj_t *radPanel, *radSlot[RAD_MAX], *radSym[RAD_MAX], *radImg[RAD_MAX], *radName, *radHint;
static char radLabels[RAD_MAX][20];
static uint32_t radColors[RAD_MAX];
static int radCount = 0, radIndex = 0;
static bool radOpen = false;
static unsigned long radLast = 0;
static lv_obj_t *volDevice;

// Hue
static lv_obj_t *hueArc, *hueSym, *hueName, *hueValue, *hueHint;
static uint32_t hueColor = COL_HUE;
static int huePermille = 0;

// Alerte
static lv_obj_t *notifPanel, *notifRing, *notifSym, *notifTitle, *notifSub;
static unsigned long notifUntil = 0;
static uint32_t notifColor = 0;

// Question à choix
#define ASK_MAX_OPTS 8
static lv_obj_t *askPanel, *askRing, *askTitle, *askDetail, *askChoice, *askHint;
static char askLabels[ASK_MAX_OPTS][16];
static uint32_t askColors[ASK_MAX_OPTS];
static int askCount = 0, askIndex = 0, askId = -1;

// Veille
static uint8_t ledMax = 255;                 // plafond des LEDs (mode nuit)
static uint8_t wakeBacklight = BACKLIGHT_MAX; // luminosité « réveillé » (mode nuit plus bas)

// Écran d'accueil configurable
static Tile homeTile = TILE_VOL;
static uint32_t appReturnMs = APP_RETURN_MS, otherReturnMs = AUTO_RETURN_MS;

// Historique des alertes (anneau de 12 entrées, la plus récente en tête)
#define HIST_MAX 12
struct HistEntry {
  char sym[8], title[28], sub[32];
  uint32_t color;
  long secOfDay;  // heure de l'alerte (horloge reçue du PC), -1 = inconnue
};
static HistEntry hist[HIST_MAX];
static int histCount = 0, histUnread = 0, histIndex = 0;
static bool histOpen = false;
static lv_obj_t *histPanel, *histSym, *histTitle, *histSub, *histWhen, *histCounter, *dashUnread;

// Badge réunion (micro utilisé par une app)
static lv_obj_t *meetBadge, *meetDot, *meetLabel;
static int meetState = 0;
static uint8_t sleepBacklight = BACKLIGHT_MAX;
static bool sleepLeds = true, sleepClock = false;
static unsigned long wakeUntil = 0;
static float backlight = BACKLIGHT_MAX;

static bool synced = false;
static uint8_t ledFlash = 0;

// ---------- Helpers

static lv_obj_t *makeArc(lv_obj_t *parent, int width) {
  lv_obj_t *arc = lv_arc_create(parent);
  lv_obj_set_size(arc, ARC_SIZE, ARC_SIZE);
  lv_obj_center(arc);
  lv_obj_clear_flag(arc, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_remove_style(arc, NULL, LV_PART_KNOB);
  lv_arc_set_rotation(arc, 135);
  lv_arc_set_bg_angles(arc, 0, 270);
  lv_arc_set_angles(arc, 0, 0);
  lv_obj_set_style_arc_width(arc, width, LV_PART_MAIN);
  lv_obj_set_style_arc_width(arc, width, LV_PART_INDICATOR);
  lv_obj_set_style_arc_color(arc, lv_color_hex(COL_TRACK), LV_PART_MAIN);
  lv_obj_set_style_arc_rounded(arc, true, LV_PART_MAIN);
  lv_obj_set_style_arc_rounded(arc, true, LV_PART_INDICATOR);
  return arc;
}

static lv_obj_t *makeLabel(lv_obj_t *parent, const lv_font_t *font, uint32_t color, int y) {
  lv_obj_t *l = lv_label_create(parent);
  lv_obj_set_style_text_font(l, font, 0);
  lv_obj_set_style_text_color(l, lv_color_hex(color), 0);
  lv_obj_set_style_text_align(l, LV_TEXT_ALIGN_CENTER, 0);
  lv_obj_align(l, LV_ALIGN_CENTER, 0, y);
  lv_label_set_text(l, "");
  return l;
}

static void limitWidth(lv_obj_t *label, int width, lv_label_long_mode_t mode = LV_LABEL_LONG_DOT) {
  lv_label_set_long_mode(label, mode);
  lv_obj_set_width(label, width);
}

static void makeTransparent(lv_obj_t *o) {
  lv_obj_set_style_bg_opa(o, LV_OPA_TRANSP, 0);
  lv_obj_set_style_border_width(o, 0, 0);
  lv_obj_set_style_pad_all(o, 0, 0);
  lv_obj_clear_flag(o, LV_OBJ_FLAG_SCROLLABLE);
}

static lv_obj_t *makeCircle(lv_obj_t *parent, int size) {
  lv_obj_t *o = lv_obj_create(parent);
  lv_obj_set_size(o, size, size);
  lv_obj_set_style_radius(o, LV_RADIUS_CIRCLE, 0);
  lv_obj_set_style_border_width(o, 0, 0);
  lv_obj_set_style_pad_all(o, 0, 0);
  lv_obj_clear_flag(o, LV_OBJ_FLAG_SCROLLABLE | LV_OBJ_FLAG_CLICKABLE);
  return o;
}

// Anime l'extrémité de l'arc (en degrés) pour des transitions douces.
static void arcEndExec(void *arc, int32_t v) { lv_arc_set_angles((lv_obj_t *)arc, 0, v); }

static void animArcTo(lv_obj_t *arc, int toDeg) {
  int from = lv_arc_get_angle_end(arc) - lv_arc_get_angle_start(arc);
  if (from < 0) from += 360;
  lv_anim_del(arc, arcEndExec);
  lv_anim_t a;
  lv_anim_init(&a);
  lv_anim_set_var(&a, arc);
  lv_anim_set_exec_cb(&a, arcEndExec);
  lv_anim_set_values(&a, from, toDeg);
  lv_anim_set_time(&a, 220);
  lv_anim_set_path_cb(&a, lv_anim_path_ease_out);
  lv_anim_start(&a);
}

// Indicateur de défilement : un segment qui tourne autour de l'anneau.
static void scrollExec(void *arc, int32_t v) {
  int start = ((v % 360) + 360) % 360;
  lv_arc_set_angles((lv_obj_t *)arc, start, (start + 42) % 360);
}

static void zoomExec(void *img, int32_t v) { lv_img_set_zoom((lv_obj_t *)img, v); }
static void sizeExec(void *o, int32_t v) {
  lv_obj_set_size((lv_obj_t *)o, v, v);
  lv_obj_align((lv_obj_t *)o, LV_ALIGN_CENTER, 0, -40);
}
static void opaExec(void *o, int32_t v) { lv_obj_set_style_opa((lv_obj_t *)o, v, 0); }

static void startAnim(void *var, lv_anim_exec_xcb_t cb, int from, int to, int ms, lv_anim_path_cb_t path,
                      int delay = 0, lv_anim_ready_cb_t ready = nullptr) {
  lv_anim_del(var, cb);
  lv_anim_t a;
  lv_anim_init(&a);
  lv_anim_set_var(&a, var);
  lv_anim_set_exec_cb(&a, cb);
  lv_anim_set_values(&a, from, to);
  lv_anim_set_time(&a, ms);
  lv_anim_set_delay(&a, delay);
  lv_anim_set_path_cb(&a, path);
  if (ready) lv_anim_set_ready_cb(&a, ready);
  lv_anim_start(&a);
}

static void goTile(Tile t, bool anim) {
  if (uiTile() != t) lv_obj_set_tile(tv, tiles[t], anim ? LV_ANIM_ON : LV_ANIM_OFF);
}

// ---------- Rendu de l'état

static void refreshDots() {
  Tile cur = uiTile();
  uint32_t accent = cur == TILE_APP ? appColor : cur == TILE_HUE ? hueColor : COL_MASTER;
  int widths[TILE_COUNT], total = 0;
  for (int i = 0; i < TILE_COUNT; i++) {
    widths[i] = i == cur ? 16 : 6;
    total += widths[i] + (i ? 5 : 0);
  }
  int x = -total / 2;
  for (int i = 0; i < TILE_COUNT; i++) {
    lv_obj_set_width(dots[i], widths[i]);
    lv_obj_set_style_bg_color(dots[i], lv_color_hex(i == cur ? accent : 0x3A3F4A), 0);
    lv_obj_align(dots[i], LV_ALIGN_BOTTOM_MID, x + widths[i] / 2, -12);
    x += widths[i] + 5;
  }
}

// Positions des textes : en mode MEDIA, titre et artiste se suivent et l'état
// de lecture passe en dessous.
static void applyLayout() {
  bool media = appMode == MODE_MEDIA;
  lv_obj_align(appName, LV_ALIGN_CENTER, 0, media ? 16 : 18);
  lv_obj_align(appHint, LV_ALIGN_CENTER, 0, media ? 42 : 80);
  lv_obj_align(appValue, LV_ALIGN_CENTER, 0, media ? 74 : 50);
  lv_label_set_long_mode(appName, media ? LV_LABEL_LONG_SCROLL_CIRCULAR : LV_LABEL_LONG_DOT);
  lv_obj_set_style_text_color(appHint, lv_color_hex(media ? 0xB8BFCC : COL_DIM), 0);
}

static void refreshApp() {
  bool muted = appMuted && appMode != MODE_SCROLL;
  uint32_t col = muted ? COL_MUTE : appColor;
  lv_obj_set_style_arc_color(appArc, lv_color_hex(col), LV_PART_INDICATOR);
  lv_obj_set_style_bg_color(halo, lv_color_hex(appColor), 0);
  lv_obj_set_style_shadow_color(halo, lv_color_hex(appColor), 0);
  lv_obj_set_style_text_color(appValue, lv_color_hex(col), 0);

  if (appMode == MODE_MEDIA || appMode == MODE_PROGRESS) {
    lv_obj_set_style_text_font(appValue, appMode == MODE_MEDIA ? &lv_font_montserrat_20 : &lv_font_montserrat_28, 0);
    lv_label_set_text(appValue, appValueText);
    animArcTo(appArc, 270 * appPermille / 1000);
    return;
  }
  if (appMode == MODE_SCROLL) {
    lv_obj_set_style_text_font(appValue, &lv_font_montserrat_20, 0);
    lv_label_set_text(appValue, LV_SYMBOL_UP "  " LV_SYMBOL_DOWN);
    return;
  }
  int v = appMode == MODE_MASTER ? masterVolume : appVolume;
  bool m = appMode == MODE_MASTER ? masterMuted : appMuted;
  lv_obj_set_style_arc_color(appArc, lv_color_hex(m ? COL_MUTE : appColor), LV_PART_INDICATOR);
  lv_obj_set_style_text_color(appValue, lv_color_hex(m ? COL_MUTE : appColor), 0);
  lv_obj_set_style_text_font(appValue, &lv_font_montserrat_28, 0);
  if (m)
    lv_label_set_text(appValue, "MUTE");
  else if (v < 0)
    lv_label_set_text(appValue, "--");
  else
    lv_label_set_text_fmt(appValue, "%d%%", v);
  animArcTo(appArc, v < 0 ? 0 : 270 * v / 100);
}

static void refreshVolume() {
  uint32_t col = masterMuted ? COL_MUTE : COL_MASTER;
  lv_obj_set_style_arc_color(volArc, lv_color_hex(col), LV_PART_INDICATOR);
  lv_obj_set_style_text_color(volNumber, lv_color_hex(masterMuted ? COL_DIM : COL_TEXT), 0);
  lv_label_set_text_fmt(volNumber, "%d", masterVolume);
  lv_label_set_text(volSymbol, masterMuted ? LV_SYMBOL_MUTE : LV_SYMBOL_VOLUME_MAX);
  lv_obj_set_style_text_color(volSymbol, lv_color_hex(col), 0);
  animArcTo(volArc, 270 * masterVolume / 100);
  if (appMode == MODE_MASTER) refreshApp();
}

static void onTileChanged(lv_event_t *) {
  refreshDots();
  ledFlash = 255;
  usbSerial.printf("Q%d\n", (int)uiTile());
}

// ---------- Construction

static void buildAppTile(lv_obj_t *t) {
  appArc = makeArc(t, 12);
  appContent = lv_obj_create(t);
  lv_obj_set_size(appContent, 200, 200);
  lv_obj_center(appContent);
  makeTransparent(appContent);
  lv_obj_clear_flag(appContent, LV_OBJ_FLAG_CLICKABLE);

  halo = makeCircle(appContent, 84);
  lv_obj_align(halo, LV_ALIGN_CENTER, 0, -40);
  lv_obj_set_style_bg_opa(halo, 46, 0);
  lv_obj_set_style_shadow_width(halo, 46, 0);
  lv_obj_set_style_shadow_spread(halo, 2, 0);
  lv_obj_set_style_shadow_opa(halo, 150, 0);

  haloSymbol = makeLabel(appContent, &lv_font_montserrat_28, COL_TEXT, -40);
  lv_label_set_text(haloSymbol, LV_SYMBOL_USB);

  appIcon = lv_img_create(appContent);
  lv_obj_align(appIcon, LV_ALIGN_CENTER, 0, -40);
  lv_img_set_antialias(appIcon, true);
  lv_obj_add_flag(appIcon, LV_OBJ_FLAG_HIDDEN);

  appName = makeLabel(appContent, &lv_font_montserrat_20, COL_TEXT, 18);
  limitWidth(appName, 170);
  appValue = makeLabel(appContent, &lv_font_montserrat_28, COL_MASTER, 50);
  appHint = makeLabel(appContent, &lv_font_montserrat_14, COL_DIM, 80);
  limitWidth(appHint, 150);
  lv_label_set_text(appName, "En attente du PC");
  lv_label_set_text(appHint, "lance knob_companion");

  // Caméra : disque découpé (clip_corner) à l'intérieur de l'anneau de progression.
  camBox = makeCircle(t, 196);
  lv_obj_center(camBox);
  lv_obj_set_style_bg_color(camBox, lv_color_hex(0x000000), 0);
  lv_obj_set_style_clip_corner(camBox, true, 0);
  camImg = lv_img_create(camBox);
  lv_obj_center(camImg);
  lv_img_set_zoom(camImg, 196 * 256 / 160);
  lv_obj_add_flag(camBox, LV_OBJ_FLAG_HIDDEN);
}

static void buildVolumeTile(lv_obj_t *t) {
  volArc = makeArc(t, 16);
  lv_obj_set_style_arc_color(volArc, lv_color_hex(COL_MASTER), LV_PART_INDICATOR);
  volTitle = makeLabel(t, &lv_font_montserrat_14, COL_DIM, -58);
  lv_obj_set_style_text_letter_space(volTitle, 4, 0);
  lv_label_set_text(volTitle, "VOLUME");
  volNumber = makeLabel(t, &lv_font_montserrat_48, COL_TEXT, -6);
  volSymbol = makeLabel(t, &lv_font_montserrat_28, COL_MASTER, 46);
  volDevice = makeLabel(t, &lv_font_montserrat_14, COL_DIM, 76);
  limitWidth(volDevice, 150);
}

static void buildSystemTile(lv_obj_t *t) {
  lv_obj_t *title = makeLabel(t, &lv_font_montserrat_14, COL_DIM, -92);
  lv_obj_set_style_text_letter_space(title, 4, 0);
  lv_label_set_text(title, "SYSTEME");
  static const char *captions[4] = {"CPU", "GPU", "RAM", "TEMP"};
  static const uint32_t colors[4] = {0x22D3EE, 0x76B900, 0xA78BFA, 0x3DDC84};
  static const int pos[4][2] = {{-46, -30}, {46, -30}, {-46, 52}, {46, 52}};
  for (int i = 0; i < 4; i++) {
    lv_obj_t *arc = makeArc(t, 7);
    lv_obj_set_size(arc, 82, 82);
    lv_obj_align(arc, LV_ALIGN_CENTER, pos[i][0], pos[i][1]);
    lv_obj_set_style_arc_color(arc, lv_color_hex(colors[i]), LV_PART_INDICATOR);
    sysArc[i] = arc;
    sysVal[i] = makeLabel(t, &lv_font_montserrat_20, COL_TEXT, 0);
    lv_obj_align(sysVal[i], LV_ALIGN_CENTER, pos[i][0], pos[i][1] - 6);
    lv_label_set_text(sysVal[i], "--");
    lv_obj_t *cap = makeLabel(t, &lv_font_montserrat_14, COL_DIM, 0);
    lv_obj_align(cap, LV_ALIGN_CENTER, pos[i][0], pos[i][1] + 15);
    lv_label_set_text(cap, captions[i]);
  }
}

static void launch(int index);

static void onSlotClicked(lv_event_t *e) { launch((int)(intptr_t)lv_event_get_user_data(e)); }
static void onRadialBackground(lv_event_t *) { uiLauncherClose(); }

static void buildLauncher() {
  radPanel = makeCircle(lv_layer_top(), 240);
  lv_obj_center(radPanel);
  lv_obj_set_style_bg_color(radPanel, lv_color_hex(0x05060A), 0);
  lv_obj_set_style_bg_opa(radPanel, 246, 0);
  lv_obj_add_flag(radPanel, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_add_event_cb(radPanel, onRadialBackground, LV_EVENT_CLICKED, NULL);
  for (int i = 0; i < RAD_MAX; i++) {
    lv_obj_t *s = makeCircle(radPanel, 44);
    lv_obj_set_style_bg_color(s, lv_color_hex(COL_TRACK), 0);
    lv_obj_set_style_border_width(s, 2, 0);
    lv_obj_add_flag(s, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_event_cb(s, onSlotClicked, LV_EVENT_CLICKED, (void *)(intptr_t)i);
    radSym[i] = makeLabel(s, &lv_font_montserrat_20, COL_TEXT, 0);
    radImg[i] = lv_img_create(s);
    lv_obj_center(radImg[i]);
    lv_obj_add_flag(radImg[i], LV_OBJ_FLAG_HIDDEN);
    radSlot[i] = s;
  }
  radName = makeLabel(radPanel, &lv_font_montserrat_20, COL_TEXT, -6);
  limitWidth(radName, 110);
  radHint = makeLabel(radPanel, &lv_font_montserrat_14, COL_DIM, 18);
  lv_label_set_text(radHint, "clic : lancer");
  lv_obj_add_flag(radPanel, LV_OBJ_FLAG_HIDDEN);
}

static void refreshLauncher() {
  for (int i = 0; i < RAD_MAX; i++) {
    lv_obj_t *s = radSlot[i];
    if (i >= radCount) {
      lv_obj_add_flag(s, LV_OBJ_FLAG_HIDDEN);
      continue;
    }
    lv_obj_clear_flag(s, LV_OBJ_FLAG_HIDDEN);
    bool sel = i == radIndex;
    int size = sel ? 56 : 44;
    float a = (-90.0f + 360.0f * i / radCount) * PI / 180.0f;
    lv_obj_set_size(s, size, size);
    lv_obj_align(s, LV_ALIGN_CENTER, (int)(RAD_RADIUS * cosf(a)), (int)(RAD_RADIUS * sinf(a)));
    lv_obj_set_style_border_color(s, lv_color_hex(sel ? radColors[i] : 0x2A2E38), 0);
    lv_obj_set_style_border_width(s, sel ? 3 : 2, 0);
    lv_obj_set_style_shadow_width(s, sel ? 22 : 0, 0);
    lv_obj_set_style_shadow_color(s, lv_color_hex(radColors[i]), 0);
    lv_obj_center(radSym[i]);
    lv_obj_center(radImg[i]);
  }
  if (radCount) {
    lv_label_set_text(radName, radLabels[radIndex]);
    lv_obj_set_style_text_color(radName, lv_color_hex(radColors[radIndex]), 0);
  }
}

static void launch(int index) {
  if (index < 0 || index >= radCount) return;
  usbSerial.printf("o%d\n", index);
  uiLauncherClose();
  uiFlash(LV_SYMBOL_OK);
}

static void onTileLongPress(lv_event_t *) {
  if (!radCount || uiAskVisible() || radOpen) return;
  radOpen = true;
  radLast = millis();
  refreshLauncher();
  lv_obj_clear_flag(radPanel, LV_OBJ_FLAG_HIDDEN);
  startAnim(radPanel, opaExec, 0, 255, 200, lv_anim_path_ease_out);
  uiWake();
}

static void buildDashTile(lv_obj_t *t) {
  // Anneau des secondes : balaie le tour en continu.
  secArc = makeArc(t, 4);
  lv_arc_set_rotation(secArc, 270);
  lv_arc_set_bg_angles(secArc, 0, 360);
  lv_obj_set_style_arc_color(secArc, lv_color_hex(0x10131A), LV_PART_MAIN);
  lv_obj_set_style_arc_color(secArc, lv_color_hex(COL_MASTER), LV_PART_INDICATOR);

  timeLabel = makeLabel(t, &lv_font_montserrat_48, COL_TEXT, -46);
  lv_label_set_text(timeLabel, "--:--");
  dateLabel = makeLabel(t, &lv_font_montserrat_14, COL_DIM, -12);
  limitWidth(dateLabel, 170);

  // Météo : température + petit rond pour le degré (absent de la police) + description.
  lv_obj_t *row = lv_obj_create(t);
  makeTransparent(row);
  lv_obj_set_size(row, 190, 30);
  lv_obj_align(row, LV_ALIGN_CENTER, 0, 18);
  lv_obj_set_flex_flow(row, LV_FLEX_FLOW_ROW);
  lv_obj_set_flex_align(row, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_START);
  lv_obj_set_style_pad_column(row, 3, 0);
  tempLabel = lv_label_create(row);
  lv_obj_set_style_text_font(tempLabel, &lv_font_montserrat_20, 0);
  lv_obj_set_style_text_color(tempLabel, lv_color_hex(COL_TEXT), 0);
  lv_label_set_text(tempLabel, "");
  degRing = makeCircle(row, 7);
  lv_obj_set_style_bg_opa(degRing, LV_OPA_TRANSP, 0);
  lv_obj_set_style_border_width(degRing, 2, 0);
  lv_obj_set_style_border_color(degRing, lv_color_hex(COL_TEXT), 0);
  lv_obj_add_flag(degRing, LV_OBJ_FLAG_HIDDEN);
  weatherDesc = lv_label_create(row);
  lv_obj_set_style_text_font(weatherDesc, &lv_font_montserrat_14, 0);
  lv_obj_set_style_text_color(weatherDesc, lv_color_hex(COL_DIM), 0);
  lv_obj_set_style_pad_left(weatherDesc, 6, 0);
  lv_label_set_text(weatherDesc, "");

  eventLabel = makeLabel(t, &lv_font_montserrat_14, COL_MASTER, 50);
  limitWidth(eventLabel, 180);
  dashUnread = makeLabel(t, &lv_font_montserrat_14, 0xFFB020, -88);  // « 3 alertes » non lues
  statusLabel = makeLabel(t, &lv_font_montserrat_14, COL_DIM, 72);
  limitWidth(statusLabel, 160);
}

static void buildNetTile(lv_obj_t *t) {
  // Deux anneaux concentriques : descendant à l'extérieur, montant à l'intérieur.
  netDownArc = makeArc(t, 10);
  lv_obj_set_style_arc_color(netDownArc, lv_color_hex(COL_DOWN), LV_PART_INDICATOR);
  netUpArc = makeArc(t, 10);
  lv_obj_set_size(netUpArc, ARC_SIZE - 28, ARC_SIZE - 28);
  lv_obj_center(netUpArc);
  lv_obj_set_style_arc_color(netUpArc, lv_color_hex(COL_UP), LV_PART_INDICATOR);

  lv_obj_t *title = makeLabel(t, &lv_font_montserrat_14, COL_DIM, -62);
  lv_obj_set_style_text_letter_space(title, 4, 0);
  lv_label_set_text(title, "RESEAU");
  netDown = makeLabel(t, &lv_font_montserrat_28, COL_DOWN, -30);
  lv_label_set_text(netDown, LV_SYMBOL_DOWN " --");
  netUp = makeLabel(t, &lv_font_montserrat_20, COL_UP, 2);
  lv_label_set_text(netUp, LV_SYMBOL_UP " --");

  // Historique : courbes sans points ni grille.
  netChart = lv_chart_create(t);
  lv_obj_set_size(netChart, 132, 40);
  lv_obj_align(netChart, LV_ALIGN_CENTER, 0, 46);
  lv_chart_set_type(netChart, LV_CHART_TYPE_LINE);
  lv_chart_set_point_count(netChart, NET_POINTS);
  lv_chart_set_range(netChart, LV_CHART_AXIS_PRIMARY_Y, 0, 1000);
  lv_chart_set_div_line_count(netChart, 0, 0);
  lv_chart_set_update_mode(netChart, LV_CHART_UPDATE_MODE_SHIFT);
  makeTransparent(netChart);
  lv_obj_clear_flag(netChart, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_set_style_size(netChart, 0, LV_PART_INDICATOR);
  lv_obj_set_style_line_width(netChart, 2, LV_PART_ITEMS);
  netDownSeries = lv_chart_add_series(netChart, lv_color_hex(COL_DOWN), LV_CHART_AXIS_PRIMARY_Y);
  netUpSeries = lv_chart_add_series(netChart, lv_color_hex(COL_UP), LV_CHART_AXIS_PRIMARY_Y);
  lv_chart_set_all_value(netChart, netDownSeries, 0);
  lv_chart_set_all_value(netChart, netUpSeries, 0);
}

static void buildHueTile(lv_obj_t *t) {
  hueArc = makeArc(t, 16);
  lv_obj_set_style_arc_color(hueArc, lv_color_hex(COL_HUE), LV_PART_INDICATOR);
  hueSym = makeLabel(t, &lv_font_montserrat_28, COL_HUE, -58);
  lv_label_set_text(hueSym, LV_SYMBOL_CHARGE);
  hueName = makeLabel(t, &lv_font_montserrat_20, COL_TEXT, -18);
  limitWidth(hueName, 170);
  lv_label_set_text(hueName, "Hue");
  hueValue = makeLabel(t, &lv_font_montserrat_28, COL_HUE, 20);
  hueHint = makeLabel(t, &lv_font_montserrat_14, COL_DIM, 58);
  limitWidth(hueHint, 160);
  lv_label_set_text(hueHint, "en attente du PC");
}

static void onNotifClicked(lv_event_t *) { uiNotifyDismiss(); }

static void buildNotifPanel() {
  notifPanel = makeCircle(lv_layer_top(), 240);
  lv_obj_center(notifPanel);
  lv_obj_set_style_bg_color(notifPanel, lv_color_hex(0x05060A), 0);
  lv_obj_set_style_bg_opa(notifPanel, 242, 0);
  lv_obj_add_flag(notifPanel, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_add_event_cb(notifPanel, onNotifClicked, LV_EVENT_CLICKED, NULL);

  notifRing = makeArc(notifPanel, 8);
  lv_arc_set_rotation(notifRing, 0);
  lv_arc_set_bg_angles(notifRing, 0, 360);
  lv_arc_set_angles(notifRing, 0, 360);
  notifSym = makeLabel(notifPanel, &lv_font_montserrat_48, COL_TEXT, -42);
  notifTitle = makeLabel(notifPanel, &lv_font_montserrat_20, COL_TEXT, 16);
  limitWidth(notifTitle, 180);
  notifSub = makeLabel(notifPanel, &lv_font_montserrat_14, COL_DIM, 46);
  limitWidth(notifSub, 170);
  lv_obj_add_flag(notifPanel, LV_OBJ_FLAG_HIDDEN);
}

static void buildAskPanel() {
  askPanel = makeCircle(lv_layer_top(), 240);
  lv_obj_center(askPanel);
  lv_obj_set_style_bg_color(askPanel, lv_color_hex(0x05060A), 0);
  lv_obj_set_style_bg_opa(askPanel, 250, 0);
  lv_obj_add_flag(askPanel, LV_OBJ_FLAG_CLICKABLE);  // bloque les gestes vers les tuiles

  askRing = makeArc(askPanel, 6);
  lv_arc_set_rotation(askRing, 0);
  lv_arc_set_bg_angles(askRing, 0, 360);
  lv_arc_set_angles(askRing, 0, 360);
  lv_obj_t *sym = makeLabel(askPanel, &lv_font_montserrat_28, 0xFFB020, -78);
  lv_label_set_text(sym, LV_SYMBOL_WARNING);
  askTitle = makeLabel(askPanel, &lv_font_montserrat_14, COL_DIM, -48);
  limitWidth(askTitle, 170);
  askDetail = makeLabel(askPanel, &lv_font_montserrat_14, COL_TEXT, -12);
  limitWidth(askDetail, 176, LV_LABEL_LONG_WRAP);
  lv_obj_set_height(askDetail, 52);  // 3 lignes max
  askChoice = makeLabel(askPanel, &lv_font_montserrat_28, COL_TEXT, 42);
  askHint = makeLabel(askPanel, &lv_font_montserrat_14, COL_DIM, 78);
  lv_label_set_text(askHint, "tourner  -  clic : valider");
  lv_obj_add_flag(askPanel, LV_OBJ_FLAG_HIDDEN);
}

static void refreshAsk() {
  uint32_t col = askColors[askIndex];
  // Libellés longs (noms de sorties audio) : police plus petite pour tenir dans le rond.
  lv_obj_set_style_text_font(askChoice, strlen(askLabels[askIndex]) > 8 ? &lv_font_montserrat_20
                                                                          : &lv_font_montserrat_28, 0);
  lv_label_set_text_fmt(askChoice, LV_SYMBOL_LEFT "  %s  " LV_SYMBOL_RIGHT, askLabels[askIndex]);
  lv_obj_set_style_text_color(askChoice, lv_color_hex(col), 0);
  lv_obj_set_style_arc_color(askRing, lv_color_hex(col), LV_PART_INDICATOR);
  startAnim(askChoice, opaExec, 90, 255, 160, lv_anim_path_ease_out);
}

// Dessin du spectre : chaque barre est une colonne de petits segments carrés (style égaliseur
// à LED). Des rectangles pleins sans arrondi, donc sans masque d'anticrénelage : beaucoup plus
// rapide que des traits épais en biais (mesuré : 115 ms -> voir ci-dessous).
#define SPEC_BARS (SPEC_BANDS * 2)
#define SEG_STEP 6   // pas entre segments (px)
#define SEG_SIZE 4   // côté d'un segment (px)
static float specCos[SPEC_BARS], specSin[SPEC_BARS];

static void drawSpectrum(lv_event_t *e) {
  lv_draw_ctx_t *ctx = lv_event_get_draw_ctx(e);
  lv_obj_t *obj = lv_event_get_target(e);
  lv_area_t a;
  lv_obj_get_coords(obj, &a);
  int cx = (a.x1 + a.x2) / 2, cy = (a.y1 + a.y2) / 2;
  const int maxSeg = SPEC_LEN / SEG_STEP + 1;
  lv_draw_rect_dsc_t d;
  lv_draw_rect_dsc_init(&d);
  d.radius = 0;
  d.bg_opa = LV_OPA_COVER;
  lv_color_t base = lv_color_hex(mediaColor);
  lv_color_t shades[8];
  for (int s = 0; s < 8; s++) shades[s] = lv_color_mix(lv_color_white(), base, s * 22);  // plus clair vers l'extérieur
  for (int i = 0; i < SPEC_BARS; i++) {
    int band = i < SPEC_BANDS ? i : SPEC_BARS - 1 - i;  // miroir gauche/droite, basses en haut
    int segs = 1 + specBands[band] * (maxSeg - 1) / 63;
    for (int s = 0; s < segs; s++) {
      float r = SPEC_INNER + 2 + s * SEG_STEP;
      int x = cx + (int)(r * specCos[i]), y = cy + (int)(r * specSin[i]);
      lv_area_t sq = {(lv_coord_t)(x - SEG_SIZE / 2), (lv_coord_t)(y - SEG_SIZE / 2),
                      (lv_coord_t)(x + SEG_SIZE / 2 - 1), (lv_coord_t)(y + SEG_SIZE / 2 - 1)};
      d.bg_color = shades[min(s, 7)];
      lv_draw_rect(ctx, &d, &sq);
    }
  }
}

// N'invalide que la couronne autour de la pochette (4 bandes), pas la pochette elle-même.
static void invalidateSpectrum() {
  lv_area_t a;
  lv_obj_get_coords(mediaBars, &a);
  int cx = (a.x1 + a.x2) / 2, cy = (a.y1 + a.y2) / 2, hole = SPEC_INNER - 4;
  lv_area_t parts[4] = {
      {a.x1, a.y1, a.x2, (lv_coord_t)(cy - hole)},                                  // haut
      {a.x1, (lv_coord_t)(cy + hole), a.x2, a.y2},                                  // bas
      {a.x1, (lv_coord_t)(cy - hole), (lv_coord_t)(cx - hole), (lv_coord_t)(cy + hole)},  // gauche
      {(lv_coord_t)(cx + hole), (lv_coord_t)(cy - hole), a.x2, (lv_coord_t)(cy + hole)},  // droite
  };
  for (auto &p : parts) lv_obj_invalidate_area(mediaBars, &p);
}

static void buildMediaPanel() {
  for (int i = 0; i < SPEC_BARS; i++) {
    float ang = (-90.0f + (i + 0.5f) * 360.0f / SPEC_BARS) * PI / 180.0f;
    specCos[i] = cosf(ang);
    specSin[i] = sinf(ang);
  }
  mediaPanel = makeCircle(lv_layer_top(), 240);
  // Carré et opaque (pas rond) : LVGL sait alors qu'il cache tout ce qui est dessous et ne
  // redessine plus la tuile cachée à chaque image. L'écran étant rond, les coins sont invisibles.
  lv_obj_set_style_radius(mediaPanel, 0, 0);
  lv_obj_center(mediaPanel);
  lv_obj_set_style_bg_color(mediaPanel, lv_color_hex(0x000000), 0);
  lv_obj_set_style_bg_opa(mediaPanel, LV_OPA_COVER, 0);
  lv_obj_add_flag(mediaPanel, LV_OBJ_FLAG_CLICKABLE);  // bloque les gestes vers les tuiles

  // Avancement du morceau : petite barre droite sous l'artiste. (Un anneau tout autour de
  // l'écran coûtait ~7 ms par image : ses masques d'arc sont recalculés à chaque rafraîchissement.)
  mediaProgress = lv_bar_create(mediaPanel);
  lv_obj_set_size(mediaProgress, 64, 4);
  lv_obj_align(mediaProgress, LV_ALIGN_CENTER, 0, 114);
  lv_bar_set_range(mediaProgress, 0, 1000);
  lv_obj_set_style_bg_color(mediaProgress, lv_color_hex(COL_TRACK), LV_PART_MAIN);
  lv_obj_set_style_bg_opa(mediaProgress, LV_OPA_COVER, LV_PART_MAIN);
  lv_obj_set_style_bg_color(mediaProgress, lv_color_hex(mediaColor), LV_PART_INDICATOR);
  lv_obj_clear_flag(mediaProgress, LV_OBJ_FLAG_CLICKABLE);

  int span = 2 * (SPEC_INNER + SPEC_LEN + 6);
  mediaBars = lv_obj_create(mediaPanel);
  lv_obj_set_size(mediaBars, span, span);
  lv_obj_align(mediaBars, LV_ALIGN_CENTER, 0, SPEC_CY);
  makeTransparent(mediaBars);
  lv_obj_clear_flag(mediaBars, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_add_event_cb(mediaBars, drawSpectrum, LV_EVENT_DRAW_MAIN, NULL);

  mediaCover = lv_img_create(mediaPanel);
  lv_obj_align(mediaCover, LV_ALIGN_CENTER, 0, SPEC_CY);
  lv_img_set_antialias(mediaCover, true);
  mediaPause = makeLabel(mediaPanel, &lv_font_montserrat_28, COL_TEXT, SPEC_CY);
  lv_label_set_text(mediaPause, LV_SYMBOL_PAUSE);
  lv_obj_add_flag(mediaPause, LV_OBJ_FLAG_HIDDEN);

  mediaTitle = makeLabel(mediaPanel, &lv_font_montserrat_20, COL_TEXT, 76);
  limitWidth(mediaTitle, 150, LV_LABEL_LONG_SCROLL_CIRCULAR);
  mediaArtist = makeLabel(mediaPanel, &lv_font_montserrat_14, 0xB8BFCC, 98);
  limitWidth(mediaArtist, 120);
  lv_obj_add_flag(mediaPanel, LV_OBJ_FLAG_HIDDEN);
}

// Définies plus bas (historique, gestes de la tuile volume).
static void buildHistoryPanel();
static void onVolumeGesture(lv_event_t *);
static void onVolumeTap(lv_event_t *);

// ---------- API

void uiBegin() {
  lv_obj_t *scr = lv_scr_act();
  lv_obj_set_style_bg_color(scr, lv_color_hex(COL_BG), 0);

  tv = lv_tileview_create(scr);
  lv_obj_set_style_bg_opa(tv, LV_OPA_TRANSP, 0);
  lv_obj_set_scrollbar_mode(tv, LV_SCROLLBAR_MODE_OFF);
  for (int i = 0; i < TILE_COUNT; i++) {
    lv_dir_t dir = i == 0 ? LV_DIR_RIGHT : i == TILE_COUNT - 1 ? LV_DIR_LEFT : LV_DIR_HOR;
    tiles[i] = lv_tileview_add_tile(tv, i, 0, dir);
  }
  lv_obj_add_event_cb(tv, onTileChanged, LV_EVENT_VALUE_CHANGED, NULL);

  buildAppTile(tiles[TILE_APP]);
  buildVolumeTile(tiles[TILE_VOL]);
  buildDashTile(tiles[TILE_DASH]);
  buildNetTile(tiles[TILE_NET]);
  buildSystemTile(tiles[TILE_SYS]);
  buildHueTile(tiles[TILE_HUE]);
  // Appui long sur n'importe quelle tuile : lanceur radial.
  for (int i = 0; i < TILE_COUNT; i++) lv_obj_add_event_cb(tiles[i], onTileLongPress, LV_EVENT_LONG_PRESSED, NULL);
  // Tuile volume : glisser haut/bas = piste suivante/précédente, double tap = lecture/pause.
  lv_obj_add_event_cb(tiles[TILE_VOL], onVolumeGesture, LV_EVENT_GESTURE, NULL);
  lv_obj_add_event_cb(tiles[TILE_VOL], onVolumeTap, LV_EVENT_SHORT_CLICKED, NULL);

  // --- Éléments fixes : indicateur de page, état USB
  for (int i = 0; i < TILE_COUNT; i++) {
    dots[i] = makeCircle(scr, 6);
    lv_obj_set_style_radius(dots[i], 3, 0);
  }
  usbIcon = makeLabel(scr, &lv_font_montserrat_14, COL_MUTE, 0);
  lv_label_set_text(usbIcon, LV_SYMBOL_USB);
  lv_obj_align(usbIcon, LV_ALIGN_TOP_MID, 0, 16);

  // Badge réunion en haut de l'écran, au-dessus de toutes les tuiles.
  meetBadge = lv_obj_create(scr);
  lv_obj_set_size(meetBadge, LV_SIZE_CONTENT, 22);
  lv_obj_align(meetBadge, LV_ALIGN_TOP_MID, 0, 8);
  lv_obj_set_style_radius(meetBadge, 11, 0);
  lv_obj_set_style_bg_color(meetBadge, lv_color_hex(0x1A1D24), 0);
  lv_obj_set_style_border_width(meetBadge, 0, 0);
  lv_obj_set_style_pad_hor(meetBadge, 10, 0);
  lv_obj_set_style_pad_ver(meetBadge, 0, 0);
  lv_obj_set_style_pad_column(meetBadge, 6, 0);
  lv_obj_set_flex_flow(meetBadge, LV_FLEX_FLOW_ROW);
  lv_obj_set_flex_align(meetBadge, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
  lv_obj_clear_flag(meetBadge, LV_OBJ_FLAG_CLICKABLE | LV_OBJ_FLAG_SCROLLABLE);
  meetDot = makeCircle(meetBadge, 8);
  meetLabel = lv_label_create(meetBadge);
  lv_obj_set_style_text_font(meetLabel, &lv_font_montserrat_14, 0);
  lv_obj_set_style_text_color(meetLabel, lv_color_hex(COL_TEXT), 0);
  lv_label_set_text(meetLabel, "");
  lv_obj_add_flag(meetBadge, LV_OBJ_FLAG_HIDDEN);

  buildMediaPanel();  // sous le symbole géant, les alertes et les questions

  // Symbole géant par-dessus tout (piste suivante, etc.)
  flashLabel = lv_label_create(lv_layer_top());
  lv_obj_set_style_text_font(flashLabel, &lv_font_montserrat_48, 0);
  lv_obj_set_style_text_opa(flashLabel, 0, 0);
  lv_obj_center(flashLabel);
  lv_label_set_text(flashLabel, "");

  buildNotifPanel();
  buildHistoryPanel();
  buildLauncher();
  buildAskPanel();  // au-dessus de tout : une permission passe devant le lanceur

  refreshDots();
  refreshVolume();
  refreshApp();
}

void uiSetSynced(bool s) {
  if (s == synced) return;
  synced = s;
  if (s)
    lv_obj_add_flag(usbIcon, LV_OBJ_FLAG_HIDDEN);
  else
    lv_obj_clear_flag(usbIcon, LV_OBJ_FLAG_HIDDEN);
}

void uiSetMaster(int volume, bool muted) {
  if (volume == masterVolume && muted == masterMuted) return;
  masterVolume = constrain(volume, 0, 100);
  masterMuted = muted;
  refreshVolume();
}

void uiSetApp(const char *name, AppMode mode, uint32_t rgb, const char *hint, const lv_img_dsc_t *icon) {
  appMode = mode;
  appColor = rgb;
  appVolume = -1;
  appMuted = false;
  appPermille = 0;
  appValueText[0] = 0;
  uiHideCamera();
  applyLayout();
  lv_label_set_text(appName, name);
  lv_label_set_text(appHint, hint);
  if (icon) {
    lv_img_cache_invalidate_src(icon);
    lv_img_set_src(appIcon, icon);
    lv_obj_clear_flag(appIcon, LV_OBJ_FLAG_HIDDEN);
    lv_obj_add_flag(haloSymbol, LV_OBJ_FLAG_HIDDEN);
  }

  if (mode == MODE_SCROLL) {
    lv_arc_set_rotation(appArc, 270);
    lv_arc_set_bg_angles(appArc, 0, 360);
    lv_anim_del(appArc, arcEndExec);
    scrollExec(appArc, scrollAngle);
  } else {
    lv_arc_set_rotation(appArc, 135);
    lv_arc_set_bg_angles(appArc, 0, 270);
    lv_anim_del(appArc, scrollExec);
    lv_arc_set_angles(appArc, 0, 0);
  }
  refreshApp();

  // Entrée en scène : le contenu apparaît en fondu, l'icône et le halo rebondissent.
  startAnim(appContent, opaExec, 0, 255, 260, lv_anim_path_ease_out);
  startAnim(appIcon, zoomExec, 110, 256, 420, lv_anim_path_overshoot);
  startAnim(halo, sizeExec, 40, 84, 460, lv_anim_path_overshoot);

  if (!sleepClock) {
    goTile(TILE_APP, true);
    lv_disp_trig_activity(NULL);  // le délai de retour au volume part d'ici
  }
  refreshDots();
  ledFlash = 255;
}

void uiSetAppValue(int volume, bool muted) {
  if (volume == appVolume && muted == appMuted) return;
  appVolume = volume;
  appMuted = muted;
  refreshApp();
}

void uiSetTexts(const char *line1, const char *line2) {
  if (strcmp(lv_label_get_text(appName), line1)) lv_label_set_text(appName, line1);
  if (strcmp(lv_label_get_text(appHint), line2)) lv_label_set_text(appHint, line2);
}

void uiSetProgress(int permille, const char *valueText) {
  permille = constrain(permille, 0, 1000);
  if (permille == appPermille && !strcmp(valueText, appValueText)) return;
  appPermille = permille;
  strlcpy(appValueText, valueText, sizeof appValueText);
  refreshApp();
}

void uiSetColor(uint32_t rgb) {
  if (rgb == appColor) return;
  appColor = rgb;
  refreshApp();
  refreshDots();
}

void uiUpdateIcon(const lv_img_dsc_t *icon) {
  lv_img_cache_invalidate_src(icon);
  lv_img_set_src(appIcon, icon);
  lv_obj_clear_flag(appIcon, LV_OBJ_FLAG_HIDDEN);
  lv_obj_add_flag(haloSymbol, LV_OBJ_FLAG_HIDDEN);
  startAnim(appIcon, zoomExec, 200, 256, 300, lv_anim_path_ease_out);
}

static void flashOpaExec(void *o, int32_t v) {
  lv_obj_set_style_text_opa((lv_obj_t *)o, v > 255 ? 255 : v, 0);
}

void uiFlash(const char *text) {
  lv_label_set_text(flashLabel, text);
  lv_obj_set_style_text_color(flashLabel, lv_color_hex(appColor), 0);
  // Monte à fond tout de suite puis s'efface : valeurs > 255 = plateau.
  startAnim(flashLabel, flashOpaExec, 420, 0, 650, lv_anim_path_ease_in);
}

// ---------- Alertes

static long currentSecOfDay() {
  if (clockBase < 0) return -1;
  return (long)(((millis() - clockBaseMs) / 1000 + (unsigned long)clockBase) % 86400);
}

static void refreshUnread() {
  if (histUnread > 0)
    lv_label_set_text_fmt(dashUnread, LV_SYMBOL_BELL " %d alerte%s", histUnread, histUnread > 1 ? "s" : "");
  else
    lv_label_set_text(dashUnread, "");
}

static void pushHistory(const char *symbol, const char *title, const char *subtitle, uint32_t rgb) {
  memmove(&hist[1], &hist[0], sizeof(HistEntry) * (HIST_MAX - 1));
  HistEntry &h = hist[0];
  strlcpy(h.sym, symbol, sizeof h.sym);
  strlcpy(h.title, title, sizeof h.title);
  strlcpy(h.sub, subtitle, sizeof h.sub);
  h.color = rgb;
  h.secOfDay = currentSecOfDay();
  histCount = min(histCount + 1, HIST_MAX);
  histUnread = min(histUnread + 1, HIST_MAX);
  refreshUnread();
}

void uiNotifySilent(const char *symbol, const char *title, const char *subtitle, uint32_t rgb) {
  pushHistory(symbol, title, subtitle, rgb);
}

void uiNotify(const char *symbol, const char *title, const char *subtitle, uint32_t rgb) {
  pushHistory(symbol, title, subtitle, rgb);
  histUnread = max(0, histUnread - 1);  // vue en direct : pas « non lue »
  refreshUnread();
  notifColor = rgb;
  lv_label_set_text(notifSym, symbol);
  lv_obj_set_style_text_color(notifSym, lv_color_hex(rgb), 0);
  lv_obj_set_style_arc_color(notifRing, lv_color_hex(rgb), LV_PART_INDICATOR);
  lv_label_set_text(notifTitle, title);
  lv_label_set_text(notifSub, subtitle);
  lv_obj_clear_flag(notifPanel, LV_OBJ_FLAG_HIDDEN);
  startAnim(notifPanel, opaExec, 0, 255, 220, lv_anim_path_ease_out);
  notifUntil = millis() + NOTIFY_MS;
  uiWake();
}

bool uiNotifyVisible() { return notifUntil != 0; }

static void notifHidden(lv_anim_t *) { lv_obj_add_flag(notifPanel, LV_OBJ_FLAG_HIDDEN); }

void uiNotifyDismiss() {
  if (!notifUntil) return;
  notifUntil = 0;
  startAnim(notifPanel, opaExec, 255, 0, 250, lv_anim_path_ease_in, 0, notifHidden);
}

// ---------- Historique des alertes

static void refreshHistory() {
  if (!histCount) {
    lv_label_set_text(histSym, LV_SYMBOL_BELL);
    lv_obj_set_style_text_color(histSym, lv_color_hex(COL_DIM), 0);
    lv_label_set_text(histTitle, "Aucune alerte");
    lv_label_set_text(histSub, "");
    lv_label_set_text(histWhen, "");
    lv_label_set_text(histCounter, "");
    return;
  }
  const HistEntry &h = hist[histIndex];
  lv_label_set_text(histSym, h.sym);
  lv_obj_set_style_text_color(histSym, lv_color_hex(h.color), 0);
  lv_label_set_text(histTitle, h.title);
  lv_label_set_text(histSub, h.sub);
  long now = currentSecOfDay();
  if (h.secOfDay < 0 || now < 0) {
    lv_label_set_text(histWhen, "");
  } else {
    long ago = (now - h.secOfDay + 86400) % 86400;
    if (ago < 60)
      lv_label_set_text(histWhen, "a l'instant");
    else if (ago < 3600)
      lv_label_set_text_fmt(histWhen, "il y a %ld min", ago / 60);
    else
      lv_label_set_text_fmt(histWhen, "%02ld:%02ld", h.secOfDay / 3600, h.secOfDay / 60 % 60);
  }
  lv_label_set_text_fmt(histCounter, "%d / %d", histIndex + 1, histCount);
  startAnim(histTitle, opaExec, 80, 255, 160, lv_anim_path_ease_out);
}

static void onHistoryClicked(lv_event_t *) { uiHistoryClose(); }

static void buildHistoryPanel() {
  histPanel = makeCircle(lv_layer_top(), 240);
  lv_obj_center(histPanel);
  lv_obj_set_style_bg_color(histPanel, lv_color_hex(0x05060A), 0);
  lv_obj_set_style_bg_opa(histPanel, 246, 0);
  lv_obj_add_flag(histPanel, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_add_event_cb(histPanel, onHistoryClicked, LV_EVENT_CLICKED, NULL);
  lv_obj_t *title = makeLabel(histPanel, &lv_font_montserrat_14, COL_DIM, -86);
  lv_obj_set_style_text_letter_space(title, 3, 0);
  lv_label_set_text(title, "HISTORIQUE");
  histSym = makeLabel(histPanel, &lv_font_montserrat_48, COL_TEXT, -38);
  histTitle = makeLabel(histPanel, &lv_font_montserrat_20, COL_TEXT, 12);
  limitWidth(histTitle, 186);
  histSub = makeLabel(histPanel, &lv_font_montserrat_14, COL_DIM, 38);
  limitWidth(histSub, 176);
  histWhen = makeLabel(histPanel, &lv_font_montserrat_14, COL_MASTER, 62);
  histCounter = makeLabel(histPanel, &lv_font_montserrat_14, COL_DIM, 88);
  lv_obj_add_flag(histPanel, LV_OBJ_FLAG_HIDDEN);
}

bool uiHistoryVisible() { return histOpen; }

void uiHistoryOpen() {
  histOpen = true;
  histIndex = 0;
  histUnread = 0;
  refreshUnread();
  refreshHistory();
  lv_obj_clear_flag(histPanel, LV_OBJ_FLAG_HIDDEN);
  startAnim(histPanel, opaExec, 0, 255, 200, lv_anim_path_ease_out);
  uiWake();
}

void uiHistoryRotate(int steps) {
  if (!histOpen || histCount < 2) return;
  int next = constrain(histIndex + (steps > 0 ? 1 : -1), 0, histCount - 1);
  if (next == histIndex) return;
  histIndex = next;
  refreshHistory();
}

static void historyHidden(lv_anim_t *) { lv_obj_add_flag(histPanel, LV_OBJ_FLAG_HIDDEN); }

void uiHistoryClose() {
  if (!histOpen) return;
  histOpen = false;
  startAnim(histPanel, opaExec, 255, 0, 180, lv_anim_path_ease_in, 0, historyHidden);
}

// ---------- Réunion

void uiSetMeeting(int state, const char *label) {
  if (state == meetState && !strcmp(lv_label_get_text(meetLabel), label)) return;
  meetState = state;
  if (!state) {
    lv_obj_add_flag(meetBadge, LV_OBJ_FLAG_HIDDEN);
    return;
  }
  lv_obj_set_style_bg_color(meetDot, lv_color_hex(state == 1 ? COL_MUTE : 0x3DDC84), 0);
  lv_label_set_text(meetLabel, label);
  lv_obj_clear_flag(meetBadge, LV_OBJ_FLAG_HIDDEN);
}

// ---------- Gestes sur la tuile volume (gérés localement, touches multimédia HID)

static void onVolumeGesture(lv_event_t *) {
  lv_dir_t dir = lv_indev_get_gesture_dir(lv_indev_get_act());
  if (dir == LV_DIR_TOP) {
    hwSendMediaKey(0x00B5);  // piste suivante
    uiFlash(LV_SYMBOL_NEXT);
  } else if (dir == LV_DIR_BOTTOM) {
    hwSendMediaKey(0x00B6);  // piste précédente
    uiFlash(LV_SYMBOL_PREV);
  } else {
    return;
  }
  lv_indev_wait_release(lv_indev_get_act());
}

static void onVolumeTap(lv_event_t *) {
  static unsigned long lastTap = 0;
  unsigned long now = millis();
  if (now - lastTap < 400) {
    hwSendMediaKey(0x00CD);  // lecture / pause
    uiFlash(LV_SYMBOL_PLAY);
    lastTap = 0;
  } else {
    lastTap = now;
  }
}

// ---------- Question à choix

void uiAsk(int id, const char *title, const char *detail, const char *options) {
  askCount = 0;
  const char *p = options;
  while (*p && askCount < ASK_MAX_OPTS) {
    const char *comma = strchr(p, ',');
    if (!comma) break;
    int n = min((int)(comma - p), (int)sizeof askLabels[0] - 1);
    memcpy(askLabels[askCount], p, n);
    askLabels[askCount][n] = 0;
    askColors[askCount] = strtoul(comma + 1, nullptr, 16);
    askCount++;
    p = strchr(comma, '|');
    if (!p) break;
    p++;
  }
  if (!askCount) return;
  askId = id;
  askIndex = 0;
  lv_label_set_text(askTitle, title);
  lv_label_set_text(askDetail, detail);
  refreshAsk();
  if (lv_obj_has_flag(askPanel, LV_OBJ_FLAG_HIDDEN)) {
    lv_obj_clear_flag(askPanel, LV_OBJ_FLAG_HIDDEN);
    startAnim(askPanel, opaExec, 0, 255, 220, lv_anim_path_ease_out);
  }
  uiWake();
}

bool uiAskVisible() { return askId >= 0; }
int uiAskId() { return askId; }
int uiAskIndex() { return askIndex; }

void uiAskRotate(int steps) {
  if (askId < 0) return;
  int next = constrain(askIndex + (steps > 0 ? 1 : -1), 0, askCount - 1);
  if (next == askIndex) return;
  askIndex = next;
  refreshAsk();
}

static void askHidden(lv_anim_t *) { lv_obj_add_flag(askPanel, LV_OBJ_FLAG_HIDDEN); }

void uiAskClose() {
  if (askId < 0) return;
  askId = -1;
  startAnim(askPanel, opaExec, 255, 0, 200, lv_anim_path_ease_in, 0, askHidden);
}

// ---------- Tableau de bord

void uiSetClock(long secondsOfDay, const char *date) {
  clockBase = secondsOfDay;
  clockBaseMs = millis();
  shownMinute = -1;
  if (strcmp(lv_label_get_text(dateLabel), date)) lv_label_set_text(dateLabel, date);
}

void uiSetWeather(const char *temp, const char *desc) {
  lv_label_set_text(tempLabel, temp);
  lv_label_set_text(weatherDesc, desc);
  if (temp[0])
    lv_obj_clear_flag(degRing, LV_OBJ_FLAG_HIDDEN);
  else
    lv_obj_add_flag(degRing, LV_OBJ_FLAG_HIDDEN);
}

void uiSetEvent(const char *text) {
  if (strcmp(lv_label_get_text(eventLabel), text)) lv_label_set_text(eventLabel, text);
}

void uiSetStatus(const char *text, uint32_t rgb) {
  if (strcmp(lv_label_get_text(statusLabel), text)) lv_label_set_text(statusLabel, text);
  lv_obj_set_style_text_color(statusLabel, lv_color_hex(rgb), 0);
}

static void tickClock() {
  if (clockBase < 0) return;
  unsigned long ms = (millis() - clockBaseMs) + (unsigned long)(clockBase % 86400) * 1000UL;
  long secs = (ms / 1000) % 86400;
  int minute = secs / 60;
  if (minute != shownMinute) {
    shownMinute = minute;
    lv_label_set_text_fmt(timeLabel, "%02d:%02d", minute / 60, minute % 60);
  }
  if (uiTile() == TILE_DASH) {
    // Balayage continu : l'anneau fait un tour par minute.
    int deg = (int)((ms % 60000UL) * 360UL / 60000UL);
    lv_arc_set_angles(secArc, 0, deg);
  }
}

// ---------- Veille

void uiSetSleep(uint8_t level, bool leds, bool showClock, uint8_t ledCap) {
  sleepBacklight = level;
  sleepLeds = leds;
  ledMax = ledCap;
  // Mode nuit : même réveillé, on ne dépasse pas la luminosité demandée par le PC.
  wakeBacklight = (!showClock && level < BACKLIGHT_MAX) ? level : BACKLIGHT_MAX;
  if (showClock && !sleepClock) goTile(TILE_DASH, false);
  if (!showClock && sleepClock) goTile(homeTile, true);
  sleepClock = showClock;
}

void uiSetHome(Tile home, uint32_t appMs, uint32_t otherMs) {
  homeTile = home;
  appReturnMs = appMs;
  otherReturnMs = otherMs;
}

void uiWake() { wakeUntil = millis() + WAKE_MS; }

static void tickBacklight() {
  uint8_t target = millis() < wakeUntil ? max(wakeBacklight, sleepBacklight) : sleepBacklight;
  if (fabsf(backlight - target) < 0.5f) return;
  backlight += (target - backlight) * 0.08f;  // fondu doux
  if (fabsf(backlight - target) < 1) backlight = target;
  hwSetBacklight((uint8_t)backlight);
}

// ---------- Caméra

void uiShowCamera(const lv_img_dsc_t *frame) {
  lv_img_cache_invalidate_src(frame);
  lv_img_set_src(camImg, frame);
  lv_obj_invalidate(camImg);
  if (lv_obj_has_flag(camBox, LV_OBJ_FLAG_HIDDEN)) {
    lv_obj_clear_flag(camBox, LV_OBJ_FLAG_HIDDEN);
    lv_obj_add_flag(appContent, LV_OBJ_FLAG_HIDDEN);
    startAnim(camBox, opaExec, 0, 255, 250, lv_anim_path_ease_out);
  }
}

void uiHideCamera() {
  if (lv_obj_has_flag(camBox, LV_OBJ_FLAG_HIDDEN)) return;
  lv_obj_add_flag(camBox, LV_OBJ_FLAG_HIDDEN);
  lv_obj_clear_flag(appContent, LV_OBJ_FLAG_HIDDEN);
}

// ---------- Réseau

void uiSetNet(int downPermille, const char *downText, int upPermille, const char *upText) {
  netDownPermille = constrain(downPermille, 0, 1000);
  upPermille = constrain(upPermille, 0, 1000);
  lv_label_set_text_fmt(netDown, LV_SYMBOL_DOWN " %s", downText);
  lv_label_set_text_fmt(netUp, LV_SYMBOL_UP " %s", upText);
  animArcTo(netDownArc, 270 * netDownPermille / 1000);
  animArcTo(netUpArc, 270 * upPermille / 1000);
  lv_chart_set_next_value(netChart, netDownSeries, netDownPermille);
  lv_chart_set_next_value(netChart, netUpSeries, upPermille);
}

// ---------- Système

static void setGauge(int i, int value, int lo, int hi, const char *text) {
  if (value < 0) {
    lv_label_set_text(sysVal[i], "--");
    animArcTo(sysArc[i], 0);
    return;
  }
  lv_label_set_text(sysVal[i], text);
  animArcTo(sysArc[i], 270 * constrain(value - lo, 0, hi - lo) / (hi - lo));
}

void uiSetSystem(int cpu, int gpu, int ram, int gpuTemp) {
  char buf[8];
  sysCpu = cpu;
  snprintf(buf, sizeof buf, "%d%%", cpu);
  setGauge(0, cpu, 0, 100, buf);
  snprintf(buf, sizeof buf, "%d%%", gpu);
  setGauge(1, gpu, 0, 100, buf);
  snprintf(buf, sizeof buf, "%d%%", ram);
  setGauge(2, ram, 0, 100, buf);
  snprintf(buf, sizeof buf, "%d", gpuTemp);
  setGauge(3, gpuTemp, 30, 95, buf);
  uint32_t tcol = gpuTemp >= 83 ? COL_MUTE : gpuTemp >= 70 ? 0xFFB020 : 0x3DDC84;
  lv_obj_set_style_arc_color(sysArc[3], lv_color_hex(tcol), LV_PART_INDICATOR);
}

void uiSetAudioDevice(const char *name) {
  if (strcmp(lv_label_get_text(volDevice), name)) lv_label_set_text(volDevice, name);
}

// ---------- Lanceur radial

void uiLauncherReset(int count) {
  radCount = constrain(count, 0, RAD_MAX);
  radIndex = 0;
  for (int i = 0; i < RAD_MAX; i++) {
    lv_obj_add_flag(radImg[i], LV_OBJ_FLAG_HIDDEN);
    lv_obj_clear_flag(radSym[i], LV_OBJ_FLAG_HIDDEN);
  }
}

void uiLauncherSet(int index, const char *label, uint32_t rgb, const char *symbol) {
  if (index < 0 || index >= RAD_MAX) return;
  strlcpy(radLabels[index], label, sizeof radLabels[index]);
  radColors[index] = rgb;
  lv_label_set_text(radSym[index], symbol);
  lv_obj_set_style_text_color(radSym[index], lv_color_hex(rgb), 0);
}

void uiLauncherIcon(int index, const lv_img_dsc_t *icon) {
  if (index < 0 || index >= RAD_MAX) return;
  lv_img_cache_invalidate_src(icon);
  lv_img_set_src(radImg[index], icon);
  lv_obj_clear_flag(radImg[index], LV_OBJ_FLAG_HIDDEN);
  lv_obj_add_flag(radSym[index], LV_OBJ_FLAG_HIDDEN);
}

bool uiLauncherVisible() { return radOpen; }
int uiLauncherIndex() { return radIndex; }

void uiLauncherRotate(int steps) {
  if (!radOpen || !radCount) return;
  radIndex = ((radIndex + (steps > 0 ? 1 : -1)) % radCount + radCount) % radCount;
  radLast = millis();
  refreshLauncher();
}

static void radialHidden(lv_anim_t *) { lv_obj_add_flag(radPanel, LV_OBJ_FLAG_HIDDEN); }

void uiLauncherClose() {
  if (!radOpen) return;
  radOpen = false;
  startAnim(radPanel, opaExec, 255, 0, 180, lv_anim_path_ease_in, 0, radialHidden);
}

// ---------- Mode dédié média

void uiMediaLock(bool on) {
  if (on == mediaLocked) return;
  mediaLocked = on;
  if (on) {
    memset(specBands, 0, sizeof specBands);
    lv_obj_clear_flag(mediaPanel, LV_OBJ_FLAG_HIDDEN);
    startAnim(mediaPanel, opaExec, 0, 255, 300, lv_anim_path_ease_out);
    startAnim(mediaCover, zoomExec, 120, 256, 450, lv_anim_path_overshoot);
    uiWake();
  } else {
    lv_obj_add_flag(mediaPanel, LV_OBJ_FLAG_HIDDEN);
  }
}

bool uiMediaLocked() { return mediaLocked; }

void uiMediaInfo(const char *title, const char *artist, uint32_t rgb, int permille, bool playing) {
  if (strcmp(lv_label_get_text(mediaTitle), title)) lv_label_set_text(mediaTitle, title);
  if (strcmp(lv_label_get_text(mediaArtist), artist)) lv_label_set_text(mediaArtist, artist);
  if (rgb != mediaColor) {
    mediaColor = rgb;
    lv_obj_set_style_bg_color(mediaProgress, lv_color_hex(rgb), LV_PART_INDICATOR);
  }
  lv_bar_set_value(mediaProgress, constrain(permille, 0, 1000), LV_ANIM_OFF);
  if (playing) {
    lv_obj_add_flag(mediaPause, LV_OBJ_FLAG_HIDDEN);
    lv_obj_set_style_img_opa(mediaCover, LV_OPA_COVER, 0);
  } else {
    lv_obj_clear_flag(mediaPause, LV_OBJ_FLAG_HIDDEN);
    lv_obj_set_style_img_opa(mediaCover, 110, 0);
  }
}

void uiMediaCover(const lv_img_dsc_t *cover) {
  lv_img_cache_invalidate_src(cover);
  lv_img_set_src(mediaCover, cover);
  startAnim(mediaCover, zoomExec, 180, 256, 320, lv_anim_path_ease_out);
}

void uiSetSpectrum(const uint8_t *bands, int count, int bass) {
  for (int i = 0; i < SPEC_BANDS && i < count; i++) specBands[i] = min<int>(bands[i], 63);
  specBass = min(bass, 63);
  if (!mediaLocked) return;
  invalidateSpectrum();
}

// ---------- Hue

void uiSetHue(const char *name, int permille, const char *valueText, uint32_t rgb, const char *hint) {
  lv_label_set_text(hueName, name);
  lv_label_set_text(hueValue, valueText);
  lv_label_set_text(hueHint, hint);
  if (rgb != hueColor) {
    hueColor = rgb;
    lv_obj_set_style_arc_color(hueArc, lv_color_hex(rgb), LV_PART_INDICATOR);
    lv_obj_set_style_text_color(hueSym, lv_color_hex(rgb), 0);
    lv_obj_set_style_text_color(hueValue, lv_color_hex(rgb), 0);
    refreshDots();
  }
  permille = constrain(permille, 0, 1000);
  if (permille != huePermille) {
    huePermille = permille;
    animArcTo(hueArc, 270 * permille / 1000);
  }
}

// ---------- Divers

Tile uiTile() {
  lv_obj_t *act = lv_tileview_get_tile_act(tv);
  for (int i = 0; i < TILE_COUNT; i++)
    if (tiles[i] == act) return (Tile)i;
  return TILE_APP;
}

bool uiOnVolumeTile() { return uiTile() == TILE_VOL; }
AppMode uiAppMode() { return appMode; }

void uiKnobFeedback(int steps) {
  lv_disp_trig_activity(NULL);
  uiWake();
  ledFlash = 255;
  if (uiTile() == TILE_APP && appMode == MODE_SCROLL) {
    int from = scrollAngle;
    scrollAngle += steps * 18;
    startAnim(appArc, scrollExec, from, scrollAngle, 140, lv_anim_path_ease_out);
  }
}

static void tickLeds() {
  static unsigned long lastLed = 0;
  static uint32_t lastKey = 0xFFFFFFFF;
  unsigned long now = millis();
  if (now - lastLed < 30) return;
  lastLed = now;

  uint32_t color = 0;
  uint8_t count = 5, bright = 0;
  Tile t = uiTile();
  if (mediaLocked && askId < 0 && !notifUntil) {
    // Mode dédié : les LEDs battent avec les basses, dans la couleur de la pochette.
    color = mediaColor;
    bright = 12 + specBass * 3;
  } else if (askId >= 0) {
    color = askColors[askIndex];  // pulsation rapide dans la couleur du choix courant
    bright = 40 + (uint8_t)(110 * (0.5f + 0.5f * sinf(now / 160.0f)));
  } else if (notifUntil) {
    color = notifColor;  // clignote, même la nuit : c'est une alerte
    bright = (now / 220) % 2 ? 170 : 15;
  } else if (!sleepLeds && now >= wakeUntil) {
    bright = 0;
  } else if (t == TILE_VOL) {
    color = masterMuted ? COL_MUTE : COL_MASTER;
    count = masterMuted ? 5 : (masterVolume * 5 + 99) / 100;
    bright = 70 + ledFlash / 3;
  } else if (t == TILE_NET) {
    color = COL_DOWN;
    count = max(1, (netDownPermille * 5 + 999) / 1000);
    bright = 50 + ledFlash / 3;
  } else if (t == TILE_SYS) {
    color = sysCpu >= 85 ? COL_MUTE : 0x22D3EE;
    count = max(1, (sysCpu * 5 + 99) / 100);
    bright = 50 + ledFlash / 3;
  } else if (t == TILE_HUE) {
    color = hueColor;
    count = (huePermille * 5 + 999) / 1000;
    bright = 70 + ledFlash / 3;
  } else {
    // Respiration lente dans la couleur de l'app, flash sur chaque cran.
    color = t == TILE_DASH ? COL_MASTER : appColor;
    float breath = 0.5f + 0.5f * sinf(now / 900.0f);
    bright = (t == TILE_DASH ? 6 : 18) + (uint8_t)((t == TILE_DASH ? 10 : 22) * breath) + ledFlash / 2;
  }
  ledFlash = ledFlash > 24 ? ledFlash - 24 : 0;
  if (meetState && !notifUntil && askId < 0) {
    // En réunion : anneau fixe rouge (micro ouvert) ou vert (coupé), discret.
    color = meetState == 1 ? COL_MUTE : 0x3DDC84;
    count = 5;
    bright = 35;
  }
  bright = (uint16_t)bright * ledMax / 255;

  uint32_t key = color ^ ((uint32_t)count << 24) ^ ((uint32_t)bright << 27) ^ bright;
  if (key != lastKey) {
    hwSetLeds(color, count, bright);
    lastKey = key;
  }
}

void uiTick() {
  unsigned long now = millis();
  Tile t = uiTile();
  // Retour à l'écran d'accueil sans interaction : depuis l'app (sauf caméra affichée) et
  // depuis les tuiles de passage (volume, Hue). Les tuiles d'affichage (horloge, réseau,
  // système) restent. Pas pendant la veille, le lanceur, une question ou l'historique.
  if (!sleepClock && !radOpen && askId < 0 && !histOpen && t != homeTile) {
    uint32_t idle = lv_disp_get_inactive_time(NULL);
    bool camOn = !lv_obj_has_flag(camBox, LV_OBJ_FLAG_HIDDEN);
    if (t == TILE_APP && !camOn && appReturnMs && idle > appReturnMs)
      goTile(homeTile, true);
    else if ((t == TILE_HUE || t == TILE_VOL) && otherReturnMs && idle > otherReturnMs)
      goTile(homeTile, true);
  }
  if (notifUntil && now > notifUntil) uiNotifyDismiss();
  if (radOpen && now - radLast > 12000) uiLauncherClose();
  if (lv_disp_get_inactive_time(NULL) < 200) uiWake();  // toucher l'écran réveille aussi
  tickClock();
  tickBacklight();
  tickLeds();
}
