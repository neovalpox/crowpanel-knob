// Interface LVGL : tuile « application » (couleur/icône de la fenêtre active)
// et tuile « volume » à droite (on glisse vers la gauche pour l'afficher).
#pragma once
#include <lvgl.h>

// MASTER/APPVOL : jauge de volume. SCROLL : segment qui tourne avec la molette.
// MEDIA : pochette + titre/artiste + avancement du morceau.
// PROGRESS : jauge pilotée par le PC (impression 3D, statut Claude...).
enum AppMode { MODE_MASTER, MODE_APPVOL, MODE_SCROLL, MODE_MEDIA, MODE_PROGRESS };

void uiBegin();
void uiTick();  // LEDs, retour auto sur la tuile application

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

bool uiOnVolumeTile();
AppMode uiAppMode();
void uiKnobFeedback(int steps);  // retour visuel immédiat sur un cran de molette
