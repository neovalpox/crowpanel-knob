#include "net.h"
#include <Preferences.h>
#include <WiFiUdp.h>
#include <mbedtls/md.h>

#define HANDSHAKE_MS 3000

static Preferences prefs;
static WiFiServer server(NET_TCP_PORT);
static WiFiUDP udp;
static WiFiClient client, pending;
static bool clientOk = false;
static uint32_t generation = 0;
static bool configured = false, started = false;
static String ssid;
static uint8_t key[32];
static char pendingNonce[33];
static char pendingLine[200];
static int pendingLen = 0;
static unsigned long pendingSince = 0;

static int hexVal(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

static void toHex(const uint8_t *b, int n, char *out) {
  static const char *d = "0123456789abcdef";
  for (int i = 0; i < n; i++) {
    out[2 * i] = d[b[i] >> 4];
    out[2 * i + 1] = d[b[i] & 15];
  }
  out[2 * n] = 0;
}

// HMAC-SHA256(clé, prefix + msg) en hexadécimal (65 octets avec le zéro final).
static void hmacHex(const char *prefix, const char *msg, char *out) {
  uint8_t mac[32];
  mbedtls_md_context_t ctx;
  mbedtls_md_init(&ctx);
  mbedtls_md_setup(&ctx, mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), 1);
  mbedtls_md_hmac_starts(&ctx, key, sizeof key);
  mbedtls_md_hmac_update(&ctx, (const uint8_t *)prefix, strlen(prefix));
  mbedtls_md_hmac_update(&ctx, (const uint8_t *)msg, strlen(msg));
  mbedtls_md_hmac_finish(&ctx, mac);
  mbedtls_md_free(&ctx);
  toHex(mac, 32, out);
}

// Comparaison en temps constant.
static bool sameHex(const char *a, const char *b) {
  size_t n = strlen(b);
  if (strlen(a) != n) return false;
  uint8_t diff = 0;
  for (size_t i = 0; i < n; i++) diff |= a[i] ^ b[i];
  return diff == 0;
}

static void startWifi() {
  String pass = prefs.getString("pass", "");
  WiFi.mode(WIFI_STA);
  WiFi.setHostname("crowpanel-knob");
  WiFi.setSleep(false);  // latence de la molette avant la consommation (le module est alimenté)
  WiFi.setAutoReconnect(true);
  WiFi.begin(ssid.c_str(), pass.c_str());
  if (!started) {
    server.begin();
    server.setNoDelay(true);
    udp.begin(NET_DISCOVERY_PORT);
    started = true;
  }
}

void netBegin() {
  prefs.begin("knob", false);
  ssid = prefs.getString("ssid", "");
  configured = ssid.length() > 0 && prefs.getBytes("key", key, sizeof key) == sizeof key;
  if (configured) startWifi();
}

bool netConfigured() { return configured; }

bool netConfigure(const char *newSsid, const char *pass, const char *keyHex) {
  if (!*newSsid || strlen(newSsid) > 32 || strlen(pass) > 63 || strlen(keyHex) != 64) return false;
  uint8_t k[32];
  for (int i = 0; i < 32; i++) {
    int hi = hexVal(keyHex[2 * i]), lo = hexVal(keyHex[2 * i + 1]);
    if (hi < 0 || lo < 0) return false;
    k[i] = hi << 4 | lo;
  }
  memcpy(key, k, sizeof key);
  prefs.putString("ssid", newSsid);
  prefs.putString("pass", pass);
  prefs.putBytes("key", key, sizeof key);
  ssid = newSsid;
  configured = true;
  netDrop();
  WiFi.disconnect();
  startWifi();
  return true;
}

void netForget() {
  prefs.remove("ssid");
  prefs.remove("pass");
  prefs.remove("key");
  ssid = "";
  configured = false;
  netDrop();
  pending.stop();
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
}

void netDrop() {
  if (clientOk) client.stop();
  clientOk = false;
}

WiFiClient *netClient() {
  if (clientOk && !client.connected()) {
    client.stop();
    clientOk = false;
  }
  return clientOk ? &client : nullptr;
}

uint32_t netGeneration() { return generation; }

static void answerDiscovery() {
  int n = udp.parsePacket();
  if (n <= 0) return;
  char buf[16];
  int len = udp.read(buf, sizeof buf - 1);
  buf[len > 0 ? len : 0] = 0;
  if (strncmp(buf, "KNOB?", 5) != 0) return;
  udp.beginPacket(udp.remoteIP(), udp.remotePort());
  udp.print("KNOB crowpanel-knob");
  udp.endPacket();
}

static void acceptClient() {
  WiFiClient c = server.available();
  if (!c) return;
  pending.stop();  // une seule poignée de main à la fois
  pending = c;
  pending.setNoDelay(true);
  uint8_t nonce[16];
  esp_fill_random(nonce, sizeof nonce);
  toHex(nonce, sizeof nonce, pendingNonce);
  pending.printf("h%s\n", pendingNonce);
  pendingLen = 0;
  pendingSince = millis();
}

// Lit la réponse du PC ; promeut le client s'il connaît la clé.
static void checkHandshake() {
  if (!pending) return;
  if (!pending.connected() || millis() - pendingSince > HANDSHAKE_MS) {
    pending.stop();
    return;
  }
  while (pending.available()) {
    char c = pending.read();
    if (c != '\n') {
      if (pendingLen < (int)sizeof pendingLine - 1) pendingLine[pendingLen++] = c;
      continue;
    }
    pendingLine[pendingLen] = 0;
    char *tab = strchr(pendingLine, '\t');
    char expected[65];
    hmacHex("pc", pendingNonce, expected);
    if (pendingLine[0] != 'h' || !tab || !sameHex(tab + 1, expected)) {
      pending.stop();
      return;
    }
    *tab = 0;
    char proof[65];
    hmacHex("knob", pendingLine + 1, proof);
    pending.printf("h%s\n", proof);
    netDrop();  // le nouveau client remplace l'ancien (ex. compagnon redémarré)
    client = pending;
    pending = WiFiClient();
    clientOk = true;
    generation++;
    return;
  }
}

void netLoop() {
  if (!configured || WiFi.status() != WL_CONNECTED) return;
  answerDiscovery();
  acceptClient();
  checkHandshake();
}

void netStatus(Print &out) {
  int state = 0;
  if (configured) {
    wl_status_t s = WiFi.status();
    state = s == WL_CONNECTED ? 2 : (s == WL_CONNECT_FAILED || s == WL_NO_SSID_AVAIL) ? 3 : 1;
  }
  out.printf("wi%d\t%s\t%s\t%d\n", state, ssid.c_str(), state == 2 ? WiFi.localIP().toString().c_str() : "",
             state == 2 ? (int)WiFi.RSSI() : 0);
}

void netScan(Print &out) {
  if (WiFi.getMode() == WIFI_OFF) WiFi.mode(WIFI_STA);
  int n = WiFi.scanNetworks();
  for (int i = 0; i < n; i++) {
    String name = WiFi.SSID(i);
    if (!name.length()) continue;
    bool dup = false;  // un même réseau sur plusieurs points d'accès : on garde le plus fort (premier)
    for (int j = 0; j < i && !dup; j++) dup = WiFi.SSID(j) == name;
    if (!dup) out.printf("ws%d\t%s\n", (int)WiFi.RSSI(i), name.c_str());
  }
  WiFi.scanDelete();
  out.print("w.\n");
  if (!configured) WiFi.mode(WIFI_OFF);
}
