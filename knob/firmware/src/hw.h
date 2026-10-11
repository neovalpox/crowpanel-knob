// Matériel du CrowPanel 1.28" : écran GC9A01, tactile CST816D, molette, LEDs, USB.
#pragma once
#include <Arduino.h>
#include <lvgl.h>
#include "USB.h"

void hwBegin();            // alimentation, écran, LVGL, tactile, molette, LEDs, USB
int hwTakeEncoderSteps();  // crans tournés depuis le dernier appel (+ = horaire)

// Les clics sont regroupés : un clic n'est rendu qu'après 300 ms sans autre appui,
// pour distinguer simple, double et triple clic.
enum ButtonEvent { BTN_NONE, BTN_CLICK, BTN_LONG, BTN_DOUBLE, BTN_TRIPLE };
ButtonEvent hwPollButton();

void hwSendMediaKey(uint16_t usage);  // touche multimédia HID (volume, mute, play...)
// Si le crochet renvoie true, la touche est partie autrement (au PC par le Wi-Fi).
extern bool (*hwMediaKeyHook)(uint16_t usage);
void hwSetLeds(uint32_t rgb, uint8_t count, uint8_t brightness);
void hwSetBacklight(uint8_t level);  // 0 = éteint, 255 = max

extern USBCDC usbSerial;

// Miroir de l'écran (copie de chaque zone envoyée à l'écran) pour l'éditeur 3D du PC.
// Tampon 240x240 RGB565 alloué au premier appel ; zone modifiée depuis le dernier envoi.
void hwMirrorEnable(bool on);
extern uint16_t *hwMirror;
extern int16_t hwMirrorX1, hwMirrorY1, hwMirrorX2, hwMirrorY2;  // X1 > X2 : rien de neuf
// Diagnostic du rendu (rappel LVGL après chaque rafraîchissement) : nombre, pixels max, ms max.
extern volatile uint32_t hwRefrCount, hwRefrPx, hwRefrMs;
