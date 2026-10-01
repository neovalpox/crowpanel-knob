// Interface LVGL. Tuiles, de gauche à droite :
//   application (couleur/icône de la fenêtre active) | volume | tableau de bord | réseau | Hue
// On glisse vers la gauche pour passer à la tuile suivante.
#pragma once
#include <lvgl.h>

// MASTER/APPVOL : jauge de volume. SCROLL : segment qui tourne avec la molette.
// MEDIA : pochette + titre/artiste + avancement du morceau.
// PROGRESS : jauge pilotée par le PC (impression 3D, statut Claude...).
enum AppMode { MODE_MASTER, MODE_APPVOL, MODE_SCROLL, MODE_MEDIA, MODE_PROGRESS };
enum Tile { TILE_APP, TILE_VOL, TILE_DASH, TILE_NET, TILE_HUE };

void uiBegin();
void uiTick();  // LEDs, horloge, veille, alertes, retour auto sur la tuile application

void uiSetSynced(bool synced);
void uiSetMaster(int volume, bool muted);
// icon peut être nullptr : on garde l'icône précédente.
void uiSetApp(const char *name, AppMode mode, uint32_t rgb, const char *hint, const lv_img_dsc_t *icon);
void uiSetAppValue(int volume, bool muted);
void uiSetTexts(const char *line1, const char *line2);
void uiSetProgress(int permille, const char *valueText);
void uiSetColor(uint32_t rgb);
void uiUpdateIcon(const lv_img_dsc_t *icon);  // sans animation d'entrée (ex. nouvelle pochette)
void uiFlash(const char *text);               // symbole géant qui apparaît puis s'efface

// Alerte plein écran (bulle + LEDs qui clignotent), fermée par clic/tap ou après 8 s.
void uiNotify(const char *symbol, const char *title, const char *subtitle, uint32_t rgb);
bool uiNotifyVisible();
void uiNotifyDismiss();

// Tableau de bord
void uiSetClock(long secondsOfDay, const char *date);
void uiSetWeather(const char *temp, const char *desc);
void uiSetEvent(const char *text);
void uiSetStatus(const char *text, uint32_t rgb);

// Veille : luminosité cible, LEDs autorisées, bascule sur l'horloge.
void uiSetSleep(uint8_t backlight, bool leds, bool showClock);
void uiWake();  // interaction locale : plein écran quelques secondes

// Caméra (image RGB565 affichée en rond dans l'anneau de la tuile application)
void uiShowCamera(const lv_img_dsc_t *frame);
void uiHideCamera();

// Question à choix (permission Claude) : la molette choisit, le clic valide.
// options : "LIBELLE,RRGGBB|LIBELLE,RRGGBB|..."
void uiAsk(int id, const char *title, const char *detail, const char *options);
bool uiAskVisible();
int uiAskId();
int uiAskIndex();
void uiAskRotate(int steps);
void uiAskClose();

// Réseau : jauges (pour mille, échelle log calculée par le PC) + débits formatés.
void uiSetNet(int downPermille, const char *downText, int upPermille, const char *upText);

void uiSetHue(const char *name, int permille, const char *valueText, uint32_t rgb, const char *hint);

Tile uiTile();
bool uiOnVolumeTile();
AppMode uiAppMode();
void uiKnobFeedback(int steps);  // retour visuel immédiat sur un cran de molette
