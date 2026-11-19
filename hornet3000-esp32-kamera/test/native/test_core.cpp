// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
// Host-Tests der Firmware-Logik (core.cpp) – echter Firmware-Code, übersetzt mit g++ und Sanitizern.
// Aufruf: siehe test/native/run.sh
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <string>

#include "../../src/core.h"

using namespace h3k;
static int g_fail = 0, g_n = 0;
#define CHECK(cond)                                                                \
  do {                                                                             \
    g_n++;                                                                         \
    if (!(cond)) {                                                                 \
      g_fail++;                                                                    \
      printf("FEHLER %s:%d  %s\n", __FILE__, __LINE__, #cond);                     \
    }                                                                              \
  } while (0)

static void t_ct() {
  CHECK(ct_equals("abc", 3, "abc", 3));
  CHECK(!ct_equals("abc", 3, "abd", 3));
  CHECK(!ct_equals("abc", 3, "abcd", 4));
  CHECK(!ct_equals("abcd", 4, "abc", 3));
  CHECK(ct_equals("", 0, "", 0));
  CHECK(!ct_equals("", 0, "a", 1));
  const char z1[] = {'a', 0, 'b'}, z2[] = {'a', 0, 'c'};
  CHECK(!ct_equals(z1, 3, z2, 3));  // eingebettetes NUL wird mitverglichen
  CHECK(token_ok("geheim-geheim-1234", "geheim-geheim-1234"));
  CHECK(!token_ok("geheim-geheim-1234", "geheim-geheim-1235"));
  CHECK(!token_ok("", ""));          // nicht eingerichtet → nie offen
  CHECK(!token_ok("", "x"));
  CHECK(!token_ok(nullptr, "x"));
  CHECK(!token_ok("x", nullptr));
  CHECK(!token_ok("geheim-geheim-1234", ""));
  CHECK(!token_ok("geheim-geheim-1234", "geheim-geheim-1234 "));
}

static void t_query() {
  char o[16];
  CHECK(query_get("t=abc", "t", o, sizeof o) && !strcmp(o, "abc"));
  CHECK(query_get("a=1&t=xyz&b=2", "t", o, sizeof o) && !strcmp(o, "xyz"));
  CHECK(query_get("a=1&t=xyz", "t", o, sizeof o) && !strcmp(o, "xyz"));
  CHECK(!query_get("tt=abc", "t", o, sizeof o));            // Schlüsselpräfix zählt nicht
  CHECK(!query_get("xt=abc", "t", o, sizeof o));
  CHECK(!query_get("a=1&b=2", "t", o, sizeof o));
  CHECK(!query_get("t", "t", o, sizeof o));                  // ohne =
  CHECK(query_get("t=", "t", o, sizeof o) && o[0] == 0);
  CHECK(query_get("t=a%20b+c", "t", o, sizeof o) && !strcmp(o, "a b c"));
  CHECK(query_get("t=%41%62%63", "t", o, sizeof o) && !strcmp(o, "Abc"));
  CHECK(!query_get("t=%00x", "t", o, sizeof o));             // NUL einschleusen
  CHECK(!query_get("t=%zz", "t", o, sizeof o));
  CHECK(!query_get("t=%4", "t", o, sizeof o));
  CHECK(!query_get("t=%", "t", o, sizeof o));
  CHECK(query_get("t=123456789012345", "t", o, sizeof o));   // 15 Zeichen passen (16 mit NUL)
  CHECK(!query_get("t=1234567890123456", "t", o, sizeof o) && o[0] == 0);  // 16 passen nicht, Ausgabe leer
  CHECK(!query_get(nullptr, "t", o, sizeof o));
  CHECK(!query_get("t=a", nullptr, o, sizeof o));
  CHECK(!query_get("t=a", "t", nullptr, 4));
  CHECK(!query_get("t=a", "t", o, 0));
  CHECK(query_get("t=1&t=2", "t", o, sizeof o) && !strcmp(o, "1"));  // erster gewinnt
  CHECK(!query_get("&&&", "t", o, sizeof o));
  // Regression: gültiger Schlüssel gefolgt von kaputter Escape-Folge darf KEINEN Teilwert hinterlassen
  strcpy(o, "SECRET");
  CHECK(!query_get("t=SECRET%zz", "t", o, sizeof o) && o[0] == 0);
  strcpy(o, "SECRET");
  CHECK(!query_get("t=SECRET%4", "t", o, sizeof o) && o[0] == 0);
  strcpy(o, "SECRET");
  CHECK(!query_get("t=SECRET%00", "t", o, sizeof o) && o[0] == 0);
  CHECK(!token_ok("SECRET-SECRET-1234", o));
}

static void t_valid() {
  CHECK(valid_ssid("Heimnetz") && valid_ssid("a") && valid_ssid(std::string(32, 'x').c_str()));
  CHECK(!valid_ssid("") && !valid_ssid(std::string(33, 'x').c_str()) && !valid_ssid("a\nb") && !valid_ssid("a\x7f") &&
        !valid_ssid(nullptr));
  CHECK(valid_wifi_pass("12345678") && valid_wifi_pass(std::string(63, 'p').c_str()));
  CHECK(!valid_wifi_pass("1234567") && !valid_wifi_pass(std::string(64, 'p').c_str()) && !valid_wifi_pass("passwort\n") &&
        !valid_wifi_pass("pässwort1") && !valid_wifi_pass(nullptr));
  CHECK(valid_token("abcdefghijklmnop") && valid_token("A-b_C-d_E-f_G-h_1234") && valid_token(std::string(64, 'a').c_str()));
  CHECK(!valid_token("abcdefghijklmno") && !valid_token(std::string(65, 'a').c_str()) && !valid_token("abcdefghijklmnop&x") &&
        !valid_token("abcdefghijklmno p") && !valid_token("abcdefghijklmnop%20") && !valid_token(nullptr));
  CHECK(valid_hostname("hornet-cam-1a2b") && valid_hostname("a") && !valid_hostname("-a") && !valid_hostname("a-") &&
        !valid_hostname("A") && !valid_hostname("a_b") && !valid_hostname("") && !valid_hostname(std::string(33, 'a').c_str()) &&
        !valid_hostname("a.b") && !valid_hostname(nullptr));
}

static void t_ap() {
  uint32_t r[12];
  char a[13], b[13];
  for (int i = 0; i < 12; i++) r[i] = 1000u + i;
  random_password(r, a);
  random_password(r, b);
  CHECK(strlen(a) == 12 && !strcmp(a, b));                 // gleiche Zufallszahlen → gleiches Passwort (reine Funktion)
  r[5] += 1;
  random_password(r, b);
  CHECK(strcmp(a, b) != 0);
  CHECK(valid_wifi_pass(a));
  // 20000 Zufallsdurchläufe (auch Extremwerte): immer 12 gültige Zeichen, nie '0','1','l','o','i', Verteilung ohne Ausreißer
  srand(7);
  int hist[256] = {0};
  for (int n = 0; n < 20000; n++) {
    for (int i = 0; i < 12; i++) r[i] = (n % 97 == 0) ? 0xFFFFFFFFu : (n % 89 == 0 ? 0u : ((uint32_t)rand() << 16) ^ (uint32_t)rand());
    char p[13];
    random_password(r, p);
    CHECK(strlen(p) == 12 && valid_wifi_pass(p) && !strpbrk(p, "01loiOIL"));
    for (int i = 0; i < 12; i++) {
      CHECK(strchr("23456789abcdefghjkmnpqrstuvwxyz", p[i]) != nullptr);
      hist[(uint8_t)p[i]]++;
    }
  }
  int mn = 1 << 30, mx = 0, used = 0;
  for (int c = 0; c < 256; c++)
    if (hist[c]) {
      used++;
      mn = hist[c] < mn ? hist[c] : mn;
      mx = hist[c] > mx ? hist[c] : mx;
    }
  CHECK(used == 31 && mx < mn * 2);                        // alle 31 Zeichen kommen vor, grob gleichverteilt
}

static void t_backoff() {
  CHECK(backoff_ms(0) == 1000 && backoff_ms(1) == 2000 && backoff_ms(2) == 4000 && backoff_ms(5) == 32000);
  CHECK(backoff_ms(6) == 60000 && backoff_ms(7) == 60000 && backoff_ms(100000) == 60000);
  for (unsigned i = 0; i < 100; i++) CHECK(backoff_ms(i) >= 1000 && backoff_ms(i) <= 60000);
}

static void t_gate() {
  FailGate g;
  uint32_t t = 1000;
  CHECK(!gate_blocked(g, t));
  for (int i = 0; i < 4; i++) {
    gate_fail(g, t, 5, 60000, 60000);
    t += 100;
    CHECK(!gate_blocked(g, t));
  }
  gate_fail(g, t, 5, 60000, 60000);  // 5. Fehlversuch
  CHECK(gate_blocked(g, t + 1));
  CHECK(gate_blocked(g, t + 59999));
  CHECK(!gate_blocked(g, t + 60001));       // Sperre vorbei
  gate_fail(g, t + 60001, 5, 60000, 60000);  // wieder von vorn zählen
  CHECK(!gate_blocked(g, t + 60002));
  // Fenster läuft ab: vier Fehlversuche, lange Pause, einer → nicht gesperrt
  FailGate h;
  for (int i = 0; i < 4; i++) gate_fail(h, 1000 + i, 5, 60000, 60000);
  gate_fail(h, 1000 + 120000, 5, 60000, 60000);
  CHECK(!gate_blocked(h, 1000 + 120001));
  // Erfolg setzt zurück
  FailGate k;
  for (int i = 0; i < 4; i++) gate_fail(k, 10 + i, 5, 60000, 60000);
  gate_ok(k);
  gate_fail(k, 20, 5, 60000, 60000);
  CHECK(!gate_blocked(k, 21));
  // Überlauf des 32-Bit-Zählers (nach ~49 Tagen)
  FailGate w;
  uint32_t near = 0xFFFFFFFFu - 100;
  for (int i = 0; i < 5; i++) gate_fail(w, near + i, 5, 60000, 60000);
  CHECK(gate_blocked(w, near + 10));
  CHECK(gate_blocked(w, near + 30000));  // zählt über den Überlauf hinweg
  CHECK(!gate_blocked(w, near + 70000));
}

static void t_frames() {
  CHECK(frame_interval_ms(0) == 0 && frame_interval_ms(8) == 125 && frame_interval_ms(1) == 1000 && frame_interval_ms(1000) == 1);
}

static void t_status() {
  Status s{};
  s.version = "1.0.0";
  s.hostname = "hornet-cam-1a2b";
  s.uptime_s = 3600;
  s.rssi = -61;
  s.free_heap = 123456;
  s.free_psram = 3000000;
  s.frames = 99;
  s.cam_errors = 2;
  s.reboots_bad = 1;
  s.width = 640;
  s.height = 480;
  s.streaming = true;
  char buf[384];
  int n = status_json(buf, sizeof buf, s);
  CHECK(n > 0 && (size_t)n == strlen(buf));
  CHECK(strstr(buf, "\"rssi\":-61") && strstr(buf, "\"streaming\":true") && strstr(buf, "\"width\":640"));
  if (getenv("DUMP_STATUS")) printf("%s\n", buf);
  char small[20];
  CHECK(status_json(small, sizeof small, s) == -1 && small[0] == 0);   // zu klein → leer, nie überlaufen
  for (size_t sz = 1; sz < 300; sz++) {                                // jede Puffergröße: nie Überlauf (ASAN), Ergebnis konsistent
    char *p = (char *)malloc(sz);
    int r = status_json(p, sz, s);
    CHECK((r == -1 && p[0] == 0) || (r > 0 && (size_t)r == strlen(p)));
    free(p);
  }
  CHECK(status_json(nullptr, 10, s) == -1);
}

static void t_part() {
  char b[160];
  int n = part_header(b, sizeof b, 12345, 777);
  CHECK(n > 0);
  CHECK(!strcmp(b, "\r\n--h3kframe\r\nContent-Type: image/jpeg\r\nContent-Length: 12345\r\nX-Timestamp: 777\r\n\r\n"));
  char tiny[10];
  CHECK(part_header(tiny, sizeof tiny, 1, 1) == -1 && tiny[0] == 0);
  CHECK(part_header(b, sizeof b, 4000000000u, 4294967295u) > 0);
}

// Zufallstest (Fuzz) der Eingabeverarbeitung unter AddressSanitizer: nie abstürzen, nie über den Puffer schreiben
static void t_fuzz() {
  srand(12345);
  const char alpha[] = "tT=&%0123456789abcdefABCDEF+ -_xyz";
  for (int it = 0; it < 300000; it++) {
    char q[80];
    int len = rand() % 70;
    for (int i = 0; i < len; i++) q[i] = alpha[rand() % (sizeof(alpha) - 1)];
    q[len] = 0;
    size_t osz = 1 + rand() % 24;
    char *o = (char *)malloc(osz);
    memset(o, 'X', osz);
    bool ok = query_get(q, "t", o, osz);
    if (ok) {
      CHECK(strlen(o) < osz);
    } else {
      CHECK(o[0] == 0);  // bei Fehlschlag nie ein (halber) Wert
    }
    free(o);
  }
  for (int it = 0; it < 100000; it++) {  // Vergleich mit zufälligen Längen
    char a[40], b[40];
    int la = rand() % 39, lb = rand() % 39;
    for (int i = 0; i < la; i++) a[i] = 'a' + rand() % 3;
    for (int i = 0; i < lb; i++) b[i] = 'a' + rand() % 3;
    a[la] = b[lb] = 0;
    CHECK(ct_equals(a, la, b, lb) == (la == lb && memcmp(a, b, la) == 0));
  }
}

int main() {
  t_ct(); t_query(); t_valid(); t_ap(); t_backoff(); t_gate(); t_frames(); t_status(); t_part(); t_fuzz();
  printf("%d Prüfungen, %d Fehler\n", g_n, g_fail);
  return g_fail ? 1 : 0;
}
