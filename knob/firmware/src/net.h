// Liaison Wi-Fi : le module se connecte au réseau configuré depuis l'USB, et le compagnon PC
// le rejoint en TCP. Même protocole texte que sur l'USB, après une authentification mutuelle
// (HMAC-SHA256 sur des nonces, clé partagée transmise par l'USB à la configuration).
//   Découverte : le PC diffuse "KNOB?" en UDP sur NET_DISCOVERY_PORT, le module répond "KNOB <nom>".
//   Poignée de main sur NET_TCP_PORT :
//     module -> PC : "h<nonce module>"
//     PC -> module : "h<nonce PC>\t<HMAC(clé, "pc" + nonce module)>"
//     module -> PC : "h<HMAC(clé, "knob" + nonce PC)>"   (sinon la connexion est fermée)
#pragma once
#include <Arduino.h>
#include <WiFi.h>

#define NET_TCP_PORT 47616
#define NET_DISCOVERY_PORT 47617

void netBegin();  // lit les identifiants enregistrés et se connecte s'il y en a
void netLoop();   // découverte, nouveaux clients, poignée de main

WiFiClient *netClient();  // client authentifié, ou nullptr
uint32_t netGeneration();  // change à chaque nouveau client authentifié
void netDrop();

bool netConfigured();
// Enregistre les identifiants et la clé (64 caractères hexadécimaux), puis se connecte.
bool netConfigure(const char *ssid, const char *pass, const char *keyHex);
void netForget();  // efface les identifiants et coupe le Wi-Fi

void netStatus(Print &out);  // "wi<état>\t<ssid>\t<ip>\t<rssi>" ; état 0 aucun, 1 connexion, 2 connecté, 3 échec
void netScan(Print &out);    // "ws<rssi>\t<ssid>" par réseau, puis "w."
