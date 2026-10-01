// Matériel du CrowPanel 1.28" : écran GC9A01, tactile CST816D, molette, LEDs, USB.
#pragma once
#include <Arduino.h>
#include <lvgl.h>
#include "USB.h"

void hwBegin();            // alimentation, écran, LVGL, tactile, molette, LEDs, USB
int hwTakeEncoderSteps();  // crans tournés depuis le dernier appel (+ = horaire)

enum ButtonEvent { BTN_NONE, BTN_CLICK, BTN_LONG };
ButtonEvent hwPollButton();

void hwSendMediaKey(uint16_t usage);  // touche multimédia HID (volume, mute, play...)
void hwSetLeds(uint32_t rgb, uint8_t count, uint8_t brightness);

extern USBCDC usbSerial;
