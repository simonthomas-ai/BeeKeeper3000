// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
// Hornet3000 ESP32-Kamera – reine Logik OHNE Arduino/ESP-Abhängigkeiten.
// Diese Datei wird sowohl in die Firmware als auch in die Host-Tests (test/native) eingebunden und dort echt ausgeführt.
#pragma once
#include <stddef.h>
#include <stdint.h>

namespace h3k {

// Zeitkonstanter Vergleich (keine frühen Abbrüche); false bei unterschiedlicher Länge.
bool ct_equals(const char *a, size_t alen, const char *b, size_t blen);

// Zugangsschlüssel prüfen: false, wenn erwartet leer ist (nicht eingerichtet) oder nicht übereinstimmt.
bool token_ok(const char *expected, const char *given);

// Wert zu `key` aus einer Anfragezeichenfolge ("a=1&t=xyz") lesen, %XX/+ dekodieren. false, wenn fehlt oder zu lang.
bool query_get(const char *query, const char *key, char *out, size_t outlen);

// Eingabeprüfung der Einrichtung
bool valid_ssid(const char *s);        // 1..32 Byte, keine Steuerzeichen
bool valid_wifi_pass(const char *s);   // 8..63 Zeichen, druckbares ASCII (WPA2-PSK)
bool valid_token(const char *s);       // 16..64 Zeichen aus [A-Za-z0-9_-]
bool valid_hostname(const char *s);    // 1..32 Zeichen [a-z0-9-], nicht mit - beginnend/endend

// Anmeldepasswort des Einrichtungs-WLANs aus 12 Zufallszahlen (12 Zeichen, ohne verwechselbare Zeichen, ≈59 Bit).
// Die Zufallszahlen liefert der Hardware-Zufallsgenerator (nicht aus der MAC ableitbar); das Passwort wird im Flash gespeichert.
void random_password(const uint32_t r[12], char out[13]);

// Wartezeit vor dem n-ten Wiederverbindungsversuch: 1 s, 2 s, 4 s … höchstens 60 s
uint32_t backoff_ms(unsigned attempt);

// Begrenzung falscher Schlüssel: nach `max_fail` Fehlversuchen innerhalb `window_ms` für `lock_ms` gesperrt.
struct FailGate {
  uint32_t window_start = 0;
  uint32_t locked_until = 0;
  uint16_t fails = 0;
  bool locked = false;
};
bool gate_blocked(const FailGate &g, uint32_t now_ms);
void gate_fail(FailGate &g, uint32_t now_ms, uint16_t max_fail, uint32_t window_ms, uint32_t lock_ms);
void gate_ok(FailGate &g);

// Mindestabstand zwischen Bildern der Übertragung (ms) für gewünschte Bildrate; 0 = unbegrenzt
uint32_t frame_interval_ms(unsigned fps);

struct Status {
  const char *version;
  const char *hostname;
  uint32_t uptime_s;
  int rssi;
  uint32_t free_heap;
  uint32_t free_psram;
  uint32_t frames;
  uint32_t cam_errors;
  uint32_t reboots_bad;  // Neustarts aus Fehlerzustand seit Einschalten (RTC-Zähler)
  uint16_t width, height;
  bool streaming;
};
// Schreibt JSON; Rückgabe = Länge, oder -1 wenn der Puffer nicht reicht (dann ist `buf` leer).
int status_json(char *buf, size_t n, const Status &s);

// Kopf eines Teilbildes der Mehrteil-Übertragung; Rückgabe = Länge oder -1 bei zu kleinem Puffer.
int part_header(char *buf, size_t n, size_t jpg_len, uint32_t ts_ms);

}  // namespace h3k
