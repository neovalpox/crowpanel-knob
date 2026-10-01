#include "ui.h"
#include <Arduino.h>
#include "hw.h"

#define COL_BG 0x000000
#define COL_TRACK 0x1A1D24
#define COL_TEXT 0xF2F4F8
#define COL_DIM 0x7C8494
#define COL_MUTE 0xFF4D5E
#define COL_MASTER 0x22D3EE
#define ARC_SIZE 228
#define AUTO_RETURN_MS 8000

static lv_obj_t *tv, *tileApp, *tileVol;
static lv_obj_t *dots[2], *usbIcon;

// Tuile application
static lv_obj_t *appContent, *halo, *appIcon, *haloSymbol, *appArc, *appName, *appValue, *appHint;
static AppMode appMode = MODE_MASTER;
static uint32_t appColor = COL_MASTER;
static int appVolume = -1;
static bool appMuted = false;
static int scrollAngle = 0;
static int appPermille = 0;           // MEDIA / PROGRESS
static char appValueText[32] = "";
static lv_obj_t *flashLabel;

// Tuile volume
static lv_obj_t *volArc, *volNumber, *volSymbol, *volTitle;
static int masterVolume = 0;
static bool masterMuted = false;

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
  return l;
}

static void makeTransparent(lv_obj_t *o) {
  lv_obj_set_style_bg_opa(o, LV_OPA_TRANSP, 0);
  lv_obj_set_style_border_width(o, 0, 0);
  lv_obj_set_style_pad_all(o, 0, 0);
  lv_obj_clear_flag(o, LV_OBJ_FLAG_SCROLLABLE);
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

static void startAnim(void *var, lv_anim_exec_xcb_t cb, int from, int to, int ms, lv_anim_path_cb_t path, int delay = 0) {
  lv_anim_del(var, cb);
  lv_anim_t a;
  lv_anim_init(&a);
  lv_anim_set_var(&a, var);
  lv_anim_set_exec_cb(&a, cb);
  lv_anim_set_values(&a, from, to);
  lv_anim_set_time(&a, ms);
  lv_anim_set_delay(&a, delay);
  lv_anim_set_path_cb(&a, path);
  lv_anim_start(&a);
}

// ---------- Rendu de l'état

static void refreshDots() {
  bool vol = uiOnVolumeTile();
  uint32_t accent = vol ? COL_MASTER : appColor;
  for (int i = 0; i < 2; i++) {
    bool active = (i == 1) == vol;
    lv_obj_set_width(dots[i], active ? 16 : 6);
    lv_obj_set_style_bg_color(dots[i], lv_color_hex(active ? accent : 0x3A3F4A), 0);
  }
  lv_obj_align(dots[0], LV_ALIGN_BOTTOM_MID, vol ? -8 : -5, -12);
  lv_obj_align(dots[1], LV_ALIGN_BOTTOM_MID, vol ? 5 : 8, -12);
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
}

// ---------- API

void uiBegin() {
  lv_obj_t *scr = lv_scr_act();
  lv_obj_set_style_bg_color(scr, lv_color_hex(COL_BG), 0);

  tv = lv_tileview_create(scr);
  lv_obj_set_style_bg_opa(tv, LV_OPA_TRANSP, 0);
  lv_obj_set_scrollbar_mode(tv, LV_SCROLLBAR_MODE_OFF);
  tileApp = lv_tileview_add_tile(tv, 0, 0, LV_DIR_RIGHT);
  tileVol = lv_tileview_add_tile(tv, 1, 0, LV_DIR_LEFT);
  lv_obj_add_event_cb(tv, onTileChanged, LV_EVENT_VALUE_CHANGED, NULL);

  // --- Tuile application
  appArc = makeArc(tileApp, 12);
  appContent = lv_obj_create(tileApp);
  lv_obj_set_size(appContent, 200, 200);
  lv_obj_center(appContent);
  makeTransparent(appContent);
  lv_obj_clear_flag(appContent, LV_OBJ_FLAG_CLICKABLE);

  halo = lv_obj_create(appContent);
  lv_obj_set_size(halo, 84, 84);
  lv_obj_align(halo, LV_ALIGN_CENTER, 0, -40);
  lv_obj_set_style_radius(halo, LV_RADIUS_CIRCLE, 0);
  lv_obj_set_style_border_width(halo, 0, 0);
  lv_obj_set_style_bg_opa(halo, 46, 0);
  lv_obj_set_style_shadow_width(halo, 46, 0);
  lv_obj_set_style_shadow_spread(halo, 2, 0);
  lv_obj_set_style_shadow_opa(halo, 150, 0);
  lv_obj_clear_flag(halo, LV_OBJ_FLAG_SCROLLABLE | LV_OBJ_FLAG_CLICKABLE);

  haloSymbol = lv_label_create(appContent);
  lv_obj_set_style_text_font(haloSymbol, &lv_font_montserrat_28, 0);
  lv_obj_set_style_text_color(haloSymbol, lv_color_hex(COL_TEXT), 0);
  lv_label_set_text(haloSymbol, LV_SYMBOL_USB);
  lv_obj_align(haloSymbol, LV_ALIGN_CENTER, 0, -40);

  appIcon = lv_img_create(appContent);
  lv_obj_align(appIcon, LV_ALIGN_CENTER, 0, -40);
  lv_img_set_antialias(appIcon, true);
  lv_obj_add_flag(appIcon, LV_OBJ_FLAG_HIDDEN);

  appName = makeLabel(appContent, &lv_font_montserrat_20, COL_TEXT, 18);
  lv_label_set_long_mode(appName, LV_LABEL_LONG_DOT);
  lv_obj_set_width(appName, 170);
  appValue = makeLabel(appContent, &lv_font_montserrat_28, COL_MASTER, 50);
  appHint = makeLabel(appContent, &lv_font_montserrat_14, COL_DIM, 80);
  lv_label_set_long_mode(appHint, LV_LABEL_LONG_DOT);
  lv_obj_set_width(appHint, 150);
  lv_label_set_text(appName, "En attente du PC");
  lv_label_set_text(appHint, "lance knob_companion");

  // --- Tuile volume
  volArc = makeArc(tileVol, 16);
  lv_obj_set_style_arc_color(volArc, lv_color_hex(COL_MASTER), LV_PART_INDICATOR);
  volTitle = makeLabel(tileVol, &lv_font_montserrat_14, COL_DIM, -58);
  lv_obj_set_style_text_letter_space(volTitle, 4, 0);
  lv_label_set_text(volTitle, "VOLUME");
  volNumber = makeLabel(tileVol, &lv_font_montserrat_48, COL_TEXT, -6);
  volSymbol = makeLabel(tileVol, &lv_font_montserrat_28, COL_MASTER, 46);

  // --- Éléments fixes : indicateur de page, état USB
  for (int i = 0; i < 2; i++) {
    dots[i] = lv_obj_create(scr);
    lv_obj_set_size(dots[i], 6, 6);
    lv_obj_set_style_radius(dots[i], 3, 0);
    lv_obj_set_style_border_width(dots[i], 0, 0);
    lv_obj_clear_flag(dots[i], LV_OBJ_FLAG_CLICKABLE | LV_OBJ_FLAG_SCROLLABLE);
  }
  usbIcon = makeLabel(scr, &lv_font_montserrat_14, COL_MUTE, 0);
  lv_label_set_text(usbIcon, LV_SYMBOL_USB);
  lv_obj_align(usbIcon, LV_ALIGN_TOP_MID, 0, 16);

  // Symbole géant par-dessus tout (piste suivante, etc.)
  flashLabel = lv_label_create(lv_layer_top());
  lv_obj_set_style_text_font(flashLabel, &lv_font_montserrat_48, 0);
  lv_obj_set_style_text_opa(flashLabel, 0, 0);
  lv_obj_set_style_bg_color(flashLabel, lv_color_hex(0x000000), 0);
  lv_obj_center(flashLabel);
  lv_label_set_text(flashLabel, "");

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

  if (uiOnVolumeTile()) lv_obj_set_tile(tv, tileApp, LV_ANIM_ON);
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

bool uiOnVolumeTile() { return lv_tileview_get_tile_act(tv) == tileVol; }
AppMode uiAppMode() { return appMode; }

void uiKnobFeedback(int steps) {
  lv_disp_trig_activity(NULL);
  ledFlash = 255;
  if (!uiOnVolumeTile() && appMode == MODE_SCROLL) {
    int from = scrollAngle;
    scrollAngle += steps * 18;
    startAnim(appArc, scrollExec, from, scrollAngle, 140, lv_anim_path_ease_out);
  }
}

void uiTick() {
  static unsigned long lastLed = 0;
  static uint32_t lastKey = 0xFFFFFFFF;
  unsigned long now = millis();

  if (uiOnVolumeTile() && lv_disp_get_inactive_time(NULL) > AUTO_RETURN_MS)
    lv_obj_set_tile(tv, tileApp, LV_ANIM_ON);

  if (now - lastLed < 30) return;
  lastLed = now;

  uint32_t color;
  uint8_t count, bright;
  if (uiOnVolumeTile()) {
    color = masterMuted ? COL_MUTE : COL_MASTER;
    count = masterMuted ? 5 : (masterVolume * 5 + 99) / 100;
    bright = 70 + ledFlash / 3;
  } else {
    // Respiration lente dans la couleur de l'app, flash sur chaque cran.
    color = appColor;
    count = 5;
    float breath = 0.5f + 0.5f * sinf(now / 900.0f);
    bright = 18 + (uint8_t)(22 * breath) + ledFlash / 2;
  }
  ledFlash = ledFlash > 24 ? ledFlash - 24 : 0;

  uint32_t key = color ^ (count << 24) ^ (bright << 27) ^ bright;
  if (key != lastKey) {
    hwSetLeds(color, count, bright);
    lastKey = key;
  }
}
