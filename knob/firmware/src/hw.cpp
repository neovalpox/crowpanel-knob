#include "hw.h"
#include <Wire.h>
#include <Arduino_GFX_Library.h>
#include <Adafruit_NeoPixel.h>
#include "USBHIDConsumerControl.h"

#define LCD_PWR_EN1 1
#define LCD_PWR_EN2 2
#define TFT_SCLK 10
#define TFT_MOSI 11
#define TFT_DC 3
#define TFT_CS 9
#define TFT_RST 14
#define TFT_BLK 46
#define TP_SDA 6
#define TP_SCL 7
#define TP_RST 13
#define TP_ADDR 0x15
#define LED_PIN 48
#define LED_NUM 5
#define ENC_A 45
#define ENC_B 42
#define ENC_SW 41

// Transitions de quadrature par cran (validé sur le spike).
#define STEPS_PER_DETENT 2
#define LONG_PRESS_MS 550

static Arduino_DataBus *bus = new Arduino_ESP32SPI(TFT_DC, TFT_CS, TFT_SCLK, TFT_MOSI, GFX_NOT_DEFINED);
static Arduino_GFX *gfx = new Arduino_GC9A01(bus, TFT_RST, 0, true);
static Adafruit_NeoPixel leds(LED_NUM, LED_PIN, NEO_GRB + NEO_KHZ800);
static USBHIDConsumerControl consumer;
USBCDC usbSerial;
volatile uint32_t hwRefrCount = 0, hwRefrPx = 0, hwRefrMs = 0;

// ---------- Molette (interruptions : le rendu LVGL ne doit pas faire rater de crans)
static const int8_t QDEC[16] = {0, -1, 1, 0, 1, 0, 0, -1, -1, 0, 0, 1, 0, 1, -1, 0};
static volatile uint8_t encAB = 0;
static volatile int encQuarter = 0;

static void IRAM_ATTR encoderIsr() {
  uint8_t ab = (digitalRead(ENC_A) << 1) | digitalRead(ENC_B);
  encQuarter += QDEC[(encAB << 2) | ab];
  encAB = ab;
}

int hwTakeEncoderSteps() {
  noInterrupts();
  int steps = encQuarter / STEPS_PER_DETENT;
  encQuarter -= steps * STEPS_PER_DETENT;
  interrupts();
  return steps;
}

#define MULTI_CLICK_MS 300

ButtonEvent hwPollButton() {
  static bool down = false, longFired = false;
  static unsigned long downAt = 0, lastEdge = 0, lastRelease = 0;
  static int clicks = 0;
  bool pressed = digitalRead(ENC_SW) == LOW;
  unsigned long now = millis();
  if (pressed != down && now - lastEdge > 25) {
    lastEdge = now;
    down = pressed;
    if (pressed) {
      downAt = now;
      longFired = false;
    } else if (!longFired) {
      clicks++;  // rendu plus tard, une fois la série de clics terminée
      lastRelease = now;
    }
  }
  if (down && !longFired && now - downAt > LONG_PRESS_MS) {
    longFired = true;
    clicks = 0;  // un appui long annule une série de clics en cours
    return BTN_LONG;
  }
  if (clicks && !down && now - lastRelease > MULTI_CLICK_MS) {
    int n = clicks;
    clicks = 0;
    return n >= 3 ? BTN_TRIPLE : n == 2 ? BTN_DOUBLE : BTN_CLICK;
  }
  return BTN_NONE;
}

// ---------- Tactile CST816D (I2C), lu en polling par LVGL
static bool touchRead(uint16_t &x, uint16_t &y) {
  Wire.beginTransmission(TP_ADDR);
  Wire.write(0x02);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(TP_ADDR, 5) != 5) return false;
  uint8_t fingers = Wire.read();
  uint8_t xh = Wire.read(), xl = Wire.read(), yh = Wire.read(), yl = Wire.read();
  if (fingers == 0) return false;
  x = ((xh & 0x0F) << 8) | xl;
  y = ((yh & 0x0F) << 8) | yl;
  return x < 240 && y < 240;
}

static void lvTouchRead(lv_indev_drv_t *, lv_indev_data_t *data) {
  static uint16_t lx = 120, ly = 120;
  uint16_t x, y;
  if (touchRead(x, y)) {
    lx = x;
    ly = y;
    data->state = LV_INDEV_STATE_PR;
  } else {
    data->state = LV_INDEV_STATE_REL;
  }
  data->point.x = lx;
  data->point.y = ly;
}

// ---------- Écran
static void lvFlush(lv_disp_drv_t *drv, const lv_area_t *a, lv_color_t *px) {
  gfx->draw16bitRGBBitmap(a->x1, a->y1, (uint16_t *)px, a->x2 - a->x1 + 1, a->y2 - a->y1 + 1);
  lv_disp_flush_ready(drv);
}

void hwSendMediaKey(uint16_t usage) {
  consumer.press(usage);
  delay(6);
  consumer.release();
}

void hwSetLeds(uint32_t rgb, uint8_t count, uint8_t brightness) {
  uint8_t r = (rgb >> 16) & 0xFF, g = (rgb >> 8) & 0xFF, b = rgb & 0xFF;
  for (int i = 0; i < LED_NUM; i++) {
    if (i < count)
      leds.setPixelColor(i, r * brightness / 255, g * brightness / 255, b * brightness / 255);
    else
      leds.setPixelColor(i, 0);
  }
  leds.show();
}

void hwSetBacklight(uint8_t level) { analogWrite(TFT_BLK, level); }

void hwBegin() {
  pinMode(LCD_PWR_EN1, OUTPUT);
  pinMode(LCD_PWR_EN2, OUTPUT);
  digitalWrite(LCD_PWR_EN1, HIGH);
  digitalWrite(LCD_PWR_EN2, HIGH);

  // PID propre au firmware, pour que le script PC ne confonde pas avec le
  // port USB-JTAG du bootloader (303A:1001).
  USB.PID(0x4C4B);
  USB.productName("CrowPanel Knob");
  usbSerial.setRxBufferSize(16384);
  usbSerial.begin(115200);
  consumer.begin();
  USB.begin();

  pinMode(ENC_A, INPUT_PULLUP);
  pinMode(ENC_B, INPUT_PULLUP);
  pinMode(ENC_SW, INPUT_PULLUP);
  encAB = (digitalRead(ENC_A) << 1) | digitalRead(ENC_B);
  attachInterrupt(ENC_A, encoderIsr, CHANGE);
  attachInterrupt(ENC_B, encoderIsr, CHANGE);

  pinMode(TP_RST, OUTPUT);
  digitalWrite(TP_RST, LOW);
  delay(10);
  digitalWrite(TP_RST, HIGH);
  delay(60);
  Wire.begin(TP_SDA, TP_SCL, 400000);
  Wire.beginTransmission(TP_ADDR);  // pas de mise en veille auto : lecture fiable
  Wire.write(0xFE);
  Wire.write(0x01);
  Wire.endTransmission();

  gfx->begin(80000000);
  gfx->fillScreen(0x0000);
  pinMode(TFT_BLK, OUTPUT);
  analogWrite(TFT_BLK, 220);

  leds.begin();
  hwSetLeds(0, 0, 0);

  lv_init();
  static lv_color_t buf1[240 * 40], buf2[240 * 40];
  static lv_disp_draw_buf_t drawBuf;
  lv_disp_draw_buf_init(&drawBuf, buf1, buf2, 240 * 40);
  static lv_disp_drv_t disp;
  lv_disp_drv_init(&disp);
  disp.hor_res = 240;
  disp.ver_res = 240;
  disp.flush_cb = lvFlush;
  disp.draw_buf = &drawBuf;
  disp.monitor_cb = [](lv_disp_drv_t *, uint32_t ms, uint32_t px) {
    hwRefrCount++;
    if (px > hwRefrPx) hwRefrPx = px;
    if (ms > hwRefrMs) hwRefrMs = ms;
  };
  lv_disp_drv_register(&disp);

  static lv_indev_drv_t touch;
  lv_indev_drv_init(&touch);
  touch.type = LV_INDEV_TYPE_POINTER;
  touch.read_cb = lvTouchRead;
  lv_indev_drv_register(&touch);
}
