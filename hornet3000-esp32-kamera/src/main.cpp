// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
// Hornet3000 ESP32-Kamera – Firmware.
// Liefert ein Bild (/jpg) und eine MJPEG-Übertragung (/stream, Port 81) für den Hornet3000-Wächter.
// Zugang nur mit Zugangsschlüssel (?t=…), Einrichtung über ein eigenes WLAN, Selbstheilung (Watchdog, WLAN, Kamera, Speicher).
#include <Arduino.h>
#include <ESPmDNS.h>
#include <Preferences.h>
#include <WiFi.h>
#include <atomic>
#include <esp_camera.h>
#include <esp_http_server.h>
#include <esp_system.h>
#include <esp_task_wdt.h>

#include "config.h"
#include "core.h"

using namespace h3k;

// ── Zustand ──────────────────────────────────────────────────────────────────────────────────────────
static Preferences prefs;
static char g_ssid[33], g_pass[64], g_token[65], g_host[33];
static bool g_configured = false;
static bool g_portal = false;
static httpd_handle_t g_ctrl = nullptr, g_stream = nullptr;
static std::atomic<bool> g_streaming{false};
static std::atomic<uint32_t> g_frames{0}, g_cam_errors{0};
static std::atomic<uint16_t> g_cam_consec{0};
static volatile uint32_t g_restart_at = 0;  // millis() + Verzögerung, 0 = kein Neustart geplant
static FailGate g_gate;
static uint16_t g_w = 0, g_h = 0;

RTC_DATA_ATTR static uint8_t rtc_wifi_fail_boots = 0;
RTC_DATA_ATTR static uint32_t rtc_bad_reboots = 0;

static void request_restart(uint32_t delay_ms) { g_restart_at = millis() + (delay_ms ? delay_ms : 1); }

// ── Hilfen ───────────────────────────────────────────────────────────────────────────────────────────
static void default_hostname(char *out, size_t n) {
  uint8_t mac[6];
  WiFi.macAddress(mac);
  snprintf(out, n, "hornet-cam-%02x%02x", mac[4], mac[5]);
}

static void load_config() {
  prefs.begin("h3kcam", true);
  String s = prefs.getString("ssid", ""), p = prefs.getString("pass", ""), t = prefs.getString("token", ""),
         h = prefs.getString("host", "");
  prefs.end();
  strlcpy(g_ssid, s.c_str(), sizeof g_ssid);
  strlcpy(g_pass, p.c_str(), sizeof g_pass);
  strlcpy(g_token, t.c_str(), sizeof g_token);
  strlcpy(g_host, h.c_str(), sizeof g_host);
  if (!valid_hostname(g_host)) default_hostname(g_host, sizeof g_host);
  g_configured = valid_ssid(g_ssid) && valid_wifi_pass(g_pass) && valid_token(g_token);
}

static bool save_config(const char *ssid, const char *pass, const char *token, const char *host) {
  if (!valid_ssid(ssid) || !valid_wifi_pass(pass) || !valid_token(token)) return false;
  if (host && host[0] && !valid_hostname(host)) return false;
  if (!prefs.begin("h3kcam", false)) return false;
  bool ok = prefs.putString("ssid", ssid) > 0 && prefs.putString("pass", pass) > 0 &&
            prefs.putString("token", token) > 0;
  prefs.putString("host", host ? host : "");
  prefs.end();
  return ok;
}

// Passwort des Einrichtungs-WLANs: einmal zufällig erzeugt und im Flash behalten (nicht aus der MAC ableitbar).
// Wird beim Start der Einrichtung auf der seriellen Schnittstelle angezeigt; Werkseinstellung erzeugt ein neues.
static void ap_password_load_or_create(char *out, size_t n) {  // n >= 13
  prefs.begin("h3kcam", false);
  String p = prefs.getString("appw", "");
  if (!valid_wifi_pass(p.c_str()) || p.length() != 12) {
    uint32_t r[12];
    esp_fill_random(r, sizeof r);
    char fresh[13];
    random_password(r, fresh);
    prefs.putString("appw", fresh);
    p = fresh;
  }
  prefs.end();
  strlcpy(out, p.c_str(), n);
}

static void random_token(char *out, size_t n) {  // n >= 33: 32 Zeichen aus dem Hardware-Zufallsgenerator
  static const char a[] = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  for (size_t i = 0; i + 1 < n && i < 32; i++) out[i] = a[esp_random() % (sizeof(a) - 1)];
  out[n > 32 ? 32 : n - 1] = '\0';
}

static void html_escape(const char *in, char *out, size_t n) {
  size_t o = 0;
  for (; *in && o + 7 < n; in++) {
    switch (*in) {
      case '&': o += snprintf(out + o, n - o, "&amp;"); break;
      case '<': o += snprintf(out + o, n - o, "&lt;"); break;
      case '>': o += snprintf(out + o, n - o, "&gt;"); break;
      case '"': o += snprintf(out + o, n - o, "&quot;"); break;
      case '\'': o += snprintf(out + o, n - o, "&#39;"); break;
      default: out[o++] = *in;
    }
  }
  out[o] = '\0';
}

// ── Zugriffsschutz ───────────────────────────────────────────────────────────────────────────────────
static esp_err_t send_text(httpd_req_t *req, const char *status, const char *type, const char *body) {
  httpd_resp_set_status(req, status);
  httpd_resp_set_type(req, type);
  httpd_resp_set_hdr(req, "Cache-Control", "no-store");
  httpd_resp_set_hdr(req, "X-Content-Type-Options", "nosniff");
  return httpd_resp_sendstr(req, body);
}

// true = erlaubt. Sonst ist die Antwort schon gesendet.
static bool authorize(httpd_req_t *req) {
  uint32_t now = millis();
  if (gate_blocked(g_gate, now)) {
    httpd_resp_set_hdr(req, "Retry-After", "60");
    send_text(req, "429 Too Many Requests", "text/plain", "zu viele falsche Schluessel, bitte warten\n");
    return false;
  }
  char given[72] = "";
  char q[160];
  if (httpd_req_get_url_query_str(req, q, sizeof q) == ESP_OK && !query_get(q, "t", given, sizeof given)) given[0] = '\0';
  if (!given[0] && httpd_req_get_hdr_value_str(req, "X-Token", given, sizeof given) != ESP_OK) given[0] = '\0';
  if (g_configured && token_ok(g_token, given)) {
    gate_ok(g_gate);
    return true;
  }
  gate_fail(g_gate, now, AUTH_MAX_FAILS, AUTH_WINDOW_MS, AUTH_LOCK_MS);
  send_text(req, "401 Unauthorized", "text/plain", "Zugangsschluessel fehlt oder falsch\n");
  return false;
}

// ── Kamera ───────────────────────────────────────────────────────────────────────────────────────────
static bool camera_start() {
  camera_config_t c = {};
  c.ledc_channel = LEDC_CHANNEL_0;
  c.ledc_timer = LEDC_TIMER_0;
  c.pin_d0 = Y2_GPIO_NUM;
  c.pin_d1 = Y3_GPIO_NUM;
  c.pin_d2 = Y4_GPIO_NUM;
  c.pin_d3 = Y5_GPIO_NUM;
  c.pin_d4 = Y6_GPIO_NUM;
  c.pin_d5 = Y7_GPIO_NUM;
  c.pin_d6 = Y8_GPIO_NUM;
  c.pin_d7 = Y9_GPIO_NUM;
  c.pin_xclk = XCLK_GPIO_NUM;
  c.pin_pclk = PCLK_GPIO_NUM;
  c.pin_vsync = VSYNC_GPIO_NUM;
  c.pin_href = HREF_GPIO_NUM;
  c.pin_sccb_sda = SIOD_GPIO_NUM;
  c.pin_sccb_scl = SIOC_GPIO_NUM;
  c.pin_pwdn = PWDN_GPIO_NUM;
  c.pin_reset = RESET_GPIO_NUM;
  c.xclk_freq_hz = 20000000;
  c.pixel_format = PIXFORMAT_JPEG;
  c.frame_size = CAM_FRAME_SIZE;
  c.jpeg_quality = CAM_JPEG_QUALITY;
  bool ps = psramFound();
  c.fb_count = ps ? 2 : 1;
  c.fb_location = ps ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;
  c.grab_mode = ps ? CAMERA_GRAB_LATEST : CAMERA_GRAB_WHEN_EMPTY;
  if (!ps) c.frame_size = FRAMESIZE_QVGA;  // ohne PSRAM nur kleines Bild
  if (esp_camera_init(&c) != ESP_OK) return false;
  sensor_t *s = esp_camera_sensor_get();
  if (!s) return false;
  s->set_vflip(s, CAM_VFLIP);
  s->set_hmirror(s, CAM_HMIRROR);
  s->set_whitebal(s, 1);
  s->set_gain_ctrl(s, 1);
  s->set_exposure_ctrl(s, 1);
  s->set_aec2(s, 1);
  s->set_lenc(s, 1);
  s->set_dcw(s, 1);
  camera_fb_t *fb = esp_camera_fb_get();  // Probebild
  if (!fb) {
    esp_camera_deinit();
    return false;
  }
  g_w = fb->width;
  g_h = fb->height;
  esp_camera_fb_return(fb);
  return true;
}

static bool camera_note_result(bool ok) {  // true = Kamera ist zu oft ausgefallen
  if (ok) {
    g_cam_consec = 0;
    return false;
  }
  g_cam_errors++;
  return ++g_cam_consec >= CAM_ERRORS_BEFORE_REINIT;
}

// ── Handler: Steuerung (Port 80) ─────────────────────────────────────────────────────────────────────
static esp_err_t h_root(httpd_req_t *req) {
  return send_text(req, "200 OK", "text/plain; charset=utf-8", "Hornet3000 ESP32-Kamera " FW_VERSION "\n");
}

static esp_err_t h_status(httpd_req_t *req) {
  if (!authorize(req)) return ESP_OK;
  Status s{};
  s.version = FW_VERSION;
  s.hostname = g_host;
  s.uptime_s = millis() / 1000;
  s.rssi = WiFi.RSSI();
  s.free_heap = ESP.getFreeHeap();
  s.free_psram = ESP.getFreePsram();
  s.frames = g_frames;
  s.cam_errors = g_cam_errors;
  s.reboots_bad = rtc_bad_reboots;
  s.width = g_w;
  s.height = g_h;
  s.streaming = g_streaming;
  char buf[384];
  if (status_json(buf, sizeof buf, s) < 0) return send_text(req, "500 Internal Server Error", "text/plain", "intern\n");
  return send_text(req, "200 OK", "application/json", buf);
}

static esp_err_t h_jpg(httpd_req_t *req) {
  if (!authorize(req)) return ESP_OK;
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    if (camera_note_result(false)) request_restart(200);
    return send_text(req, "503 Service Unavailable", "text/plain", "Kamera liefert kein Bild\n");
  }
  camera_note_result(true);
  httpd_resp_set_type(req, "image/jpeg");
  httpd_resp_set_hdr(req, "Cache-Control", "no-store");
  esp_err_t r = httpd_resp_send(req, (const char *)fb->buf, fb->len);
  esp_camera_fb_return(fb);
  return r;
}

static esp_err_t h_reboot(httpd_req_t *req) {
  if (!authorize(req)) return ESP_OK;
  send_text(req, "200 OK", "text/plain", "Neustart\n");
  request_restart(500);
  return ESP_OK;
}

static esp_err_t h_factory_reset(httpd_req_t *req) {
  if (!authorize(req)) return ESP_OK;
  prefs.begin("h3kcam", false);
  prefs.clear();
  prefs.end();
  send_text(req, "200 OK", "text/plain", "Werkseinstellung, Einrichtungs-WLAN startet\n");
  request_restart(800);
  return ESP_OK;
}

// ── Handler: MJPEG-Übertragung (Port 81) ─────────────────────────────────────────────────────────────
static esp_err_t h_stream(httpd_req_t *req) {
  if (!authorize(req)) return ESP_OK;
  bool expected = false;
  if (!g_streaming.compare_exchange_strong(expected, true)) {  // nur ein Zuschauer; schützt den kleinen Chip
    httpd_resp_set_hdr(req, "Retry-After", "5");
    return send_text(req, "503 Service Unavailable", "text/plain", "es laeuft schon eine Uebertragung\n");
  }
  httpd_resp_set_type(req, "multipart/x-mixed-replace;boundary=h3kframe");
  httpd_resp_set_hdr(req, "Cache-Control", "no-store");
  httpd_resp_set_hdr(req, "X-Content-Type-Options", "nosniff");
  esp_err_t res = ESP_OK;
  uint32_t last = 0, interval = frame_interval_ms(STREAM_MAX_FPS);
  char head[160];
  while (res == ESP_OK && g_restart_at == 0) {
    uint32_t now = millis();
    if (interval && (uint32_t)(now - last) < interval) {
      vTaskDelay(pdMS_TO_TICKS(interval - (now - last)));
      continue;
    }
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
      if (camera_note_result(false)) {
        request_restart(200);
        res = ESP_FAIL;
        break;
      }
      vTaskDelay(pdMS_TO_TICKS(50));
      continue;
    }
    camera_note_result(true);
    last = millis();
    int hl = part_header(head, sizeof head, fb->len, last);
    if (hl < 0) {
      res = ESP_FAIL;
    } else {
      res = httpd_resp_send_chunk(req, head, hl);
      if (res == ESP_OK) res = httpd_resp_send_chunk(req, (const char *)fb->buf, fb->len);
    }
    esp_camera_fb_return(fb);
    if (res == ESP_OK) g_frames++;
  }
  g_streaming = false;
  httpd_resp_send_chunk(req, nullptr, 0);
  return res;
}

// ── Handler: Einrichtungs-WLAN (nur im Portalbetrieb) ───────────────────────────────────────────────
static esp_err_t h_portal_form(httpd_req_t *req) {
  char tok[40], esc[140], page[1800];
  random_token(tok, sizeof tok);
  html_escape(g_ssid, esc, sizeof esc);
  snprintf(page, sizeof page,
           "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
           "<title>Hornet3000-Kamera einrichten</title><body style='font-family:sans-serif;max-width:30em;margin:1em auto'>"
           "<h2>Hornet3000-Kamera einrichten</h2>"
           "<form method=post action=/save>"
           "<p>WLAN-Name (SSID)<br><input name=ssid maxlength=32 value=\"%s\" required style='width:100%%'></p>"
           "<p>WLAN-Passwort (8–63 Zeichen)<br><input name=pass type=password minlength=8 maxlength=63 required style='width:100%%'></p>"
           "<p>Zugangsschl&uuml;ssel (16–64 Zeichen, nur Buchstaben/Ziffern/-/_). Diesen Schl&uuml;ssel brauchst du gleich im Hornet3000-W&auml;chter.<br>"
           "<input name=token minlength=16 maxlength=64 required value=\"%s\" style='width:100%%'></p>"
           "<p>Name im Netz (optional, a–z, 0–9, -)<br><input name=host maxlength=32 value=\"%s\" style='width:100%%'></p>"
           "<p><button>Speichern und neu starten</button></p></form>",
           esc, tok, g_host);
  return send_text(req, "200 OK", "text/html; charset=utf-8", page);
}

static esp_err_t h_portal_save(httpd_req_t *req) {
  if (req->content_len == 0 || req->content_len > 600)
    return send_text(req, "400 Bad Request", "text/plain", "Anfrage ungueltig\n");
  char body[640];
  size_t got = 0;
  while (got < req->content_len) {
    int r = httpd_req_recv(req, body + got, req->content_len - got);
    if (r <= 0) return send_text(req, "400 Bad Request", "text/plain", "Anfrage unvollstaendig\n");
    got += r;
  }
  body[got] = '\0';
  char ssid[40] = "", pass[72] = "", token[72] = "", host[40] = "";
  query_get(body, "ssid", ssid, sizeof ssid);
  query_get(body, "pass", pass, sizeof pass);
  query_get(body, "token", token, sizeof token);
  query_get(body, "host", host, sizeof host);
  if (!save_config(ssid, pass, token, host))
    return send_text(req, "400 Bad Request", "text/plain; charset=utf-8",
                     "Eingaben ungueltig (SSID 1-32 Zeichen, Passwort 8-63, Schluessel 16-64 aus A-Za-z0-9-_, Name a-z0-9-).\n");
  rtc_wifi_fail_boots = 0;
  send_text(req, "200 OK", "text/plain; charset=utf-8", "Gespeichert. Die Kamera startet neu und verbindet sich mit deinem WLAN.\n");
  request_restart(2000);
  return ESP_OK;
}

// ── Server starten ───────────────────────────────────────────────────────────────────────────────────
static void reg(httpd_handle_t h, const char *uri, httpd_method_t m, esp_err_t (*fn)(httpd_req_t *)) {
  httpd_uri_t u = {};
  u.uri = uri;
  u.method = m;
  u.handler = fn;
  httpd_register_uri_handler(h, &u);
}

static bool start_servers() {
  httpd_config_t c = HTTPD_DEFAULT_CONFIG();
  c.server_port = 80;
  c.max_open_sockets = 4;
  c.lru_purge_enable = true;
  c.recv_wait_timeout = 5;
  c.send_wait_timeout = 5;
  c.stack_size = 6144;
  c.max_uri_handlers = 8;
  if (httpd_start(&g_ctrl, &c) != ESP_OK) return false;
  if (g_portal) {
    reg(g_ctrl, "/", HTTP_GET, h_portal_form);
    reg(g_ctrl, "/save", HTTP_POST, h_portal_save);
    return true;
  }
  reg(g_ctrl, "/", HTTP_GET, h_root);
  reg(g_ctrl, "/status", HTTP_GET, h_status);
  reg(g_ctrl, "/jpg", HTTP_GET, h_jpg);
  reg(g_ctrl, "/reboot", HTTP_POST, h_reboot);
  reg(g_ctrl, "/factory-reset", HTTP_POST, h_factory_reset);
  httpd_config_t s = HTTPD_DEFAULT_CONFIG();
  s.server_port = STREAM_PORT;
  s.ctrl_port = c.ctrl_port + 1;
  s.max_open_sockets = 3;
  s.lru_purge_enable = true;
  s.recv_wait_timeout = 5;
  s.send_wait_timeout = 5;
  s.stack_size = 8192;
  if (httpd_start(&g_stream, &s) != ESP_OK) return false;
  reg(g_stream, "/stream", HTTP_GET, h_stream);
  return true;
}

// ── Start ────────────────────────────────────────────────────────────────────────────────────────────
static bool connect_sta() {
  WiFi.mode(WIFI_STA);
  WiFi.persistent(false);
  WiFi.setAutoReconnect(true);
  WiFi.setSleep(false);
  WiFi.setHostname(g_host);
  WiFi.begin(g_ssid, g_pass);
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < WIFI_CONNECT_TIMEOUT_S * 1000UL) {
    delay(250);
    esp_task_wdt_reset();
  }
  return WiFi.status() == WL_CONNECTED;
}

static void start_portal() {
  g_portal = true;
  uint8_t mac[6];
  WiFi.macAddress(mac);
  char ap_pw[64], ssid[32];
  WiFi.mode(WIFI_AP);  // erst Funk an: dann liefert der Zufallsgenerator echte Zufallszahlen
  if (strlen(AP_PASSWORD) >= 8 && strlen(AP_PASSWORD) <= 63) {
    strlcpy(ap_pw, AP_PASSWORD, sizeof ap_pw);
  } else {
    ap_password_load_or_create(ap_pw, sizeof ap_pw);
  }
  snprintf(ssid, sizeof ssid, "Hornet3000-Cam-%02X%02X", mac[4], mac[5]);
  WiFi.softAP(ssid, ap_pw, 1, 0, 2);
  Serial.printf("\n=== EINRICHTUNG ===\nWLAN: %s\nPasswort: %s\nSeite: http://192.168.4.1/\n", ssid, ap_pw);
}

void setup() {
  Serial.begin(115200);
  delay(200);
  esp_reset_reason_t rr = esp_reset_reason();
  Serial.printf("\nHornet3000 ESP32-Kamera %s, Reset-Grund %d\n", FW_VERSION, (int)rr);
  if (rr == ESP_RST_PANIC || rr == ESP_RST_TASK_WDT || rr == ESP_RST_INT_WDT || rr == ESP_RST_WDT || rr == ESP_RST_BROWNOUT)
    rtc_bad_reboots++;
  pinMode(FLASH_LED_GPIO_NUM, OUTPUT);
  digitalWrite(FLASH_LED_GPIO_NUM, LOW);

  esp_task_wdt_config_t wc = {.timeout_ms = WDT_TIMEOUT_S * 1000, .idle_core_mask = 0, .trigger_panic = true};
  if (esp_task_wdt_reconfigure(&wc) != ESP_OK) esp_task_wdt_init(&wc);
  esp_task_wdt_add(nullptr);

  load_config();
  if (!g_configured) {
    start_portal();
  } else if (!connect_sta()) {
    rtc_wifi_fail_boots++;
    Serial.printf("WLAN nicht erreichbar (%u/%u)\n", rtc_wifi_fail_boots, WIFI_BOOTS_BEFORE_PORTAL);
    if (rtc_wifi_fail_boots >= WIFI_BOOTS_BEFORE_PORTAL) {
      rtc_wifi_fail_boots = 0;
      start_portal();
    } else {
      delay(backoff_ms(rtc_wifi_fail_boots));
      ESP.restart();
    }
  } else {
    rtc_wifi_fail_boots = 0;
    MDNS.begin(g_host);
    Serial.printf("WLAN verbunden, IP %s, Name %s\n", WiFi.localIP().toString().c_str(), g_host);
  }
  if (!g_portal) {
    bool ok = false;
    for (int i = 0; i < 3 && !ok; i++) {
      ok = camera_start();
      if (!ok) {
        Serial.println("Kamera-Start fehlgeschlagen");
        esp_camera_deinit();
        delay(500);
      }
      esp_task_wdt_reset();
    }
    if (!ok) {
      rtc_bad_reboots++;
      delay(5000);
      ESP.restart();
    }
    Serial.printf("Kamera bereit: %ux%u\n", g_w, g_h);
  }
  if (!start_servers()) {
    Serial.println("HTTP-Server konnte nicht starten");
    delay(2000);
    ESP.restart();
  }
}

void loop() {
  esp_task_wdt_reset();
  uint32_t now = millis();
  if (g_restart_at && (int32_t)(now - g_restart_at) >= 0) {
    Serial.println("Neustart");
    delay(100);
    ESP.restart();
  }
  if (g_portal) {
    if (now > PORTAL_TIMEOUT_S * 1000UL) request_restart(100);
    delay(200);
    return;
  }
  static uint32_t down_since = 0, next_try = 0;
  static unsigned attempt = 0;
  if (WiFi.status() != WL_CONNECTED) {
    if (!down_since) down_since = now ? now : 1;
    if (now - down_since > WIFI_DOWN_REBOOT_S * 1000UL) request_restart(100);
    if ((int32_t)(now - next_try) >= 0) {
      WiFi.reconnect();
      next_try = now + backoff_ms(attempt++);
    }
  } else {
    down_since = 0;
    attempt = 0;
  }
  if (ESP.getFreeHeap() < MIN_FREE_HEAP) {
    Serial.println("Zu wenig Speicher");
    rtc_bad_reboots++;
    request_restart(100);
  }
  if (AUTO_REBOOT_HOURS && now > AUTO_REBOOT_HOURS * 3600UL * 1000UL && !g_streaming) request_restart(100);
  delay(500);
}
