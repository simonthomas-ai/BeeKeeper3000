// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
#include "core.h"

#include <stdio.h>
#include <string.h>

namespace h3k {

bool ct_equals(const char *a, size_t alen, const char *b, size_t blen) {
  uint8_t diff = (alen != blen);
  size_t n = alen > blen ? alen : blen;
  for (size_t i = 0; i < n; i++) {
    uint8_t ca = i < alen ? (uint8_t)a[i] : 0;
    uint8_t cb = i < blen ? (uint8_t)b[i] : 0;
    diff |= ca ^ cb;
  }
  return diff == 0;
}

bool token_ok(const char *expected, const char *given) {
  if (!expected || !given || expected[0] == '\0') return false;
  return ct_equals(expected, strlen(expected), given, strlen(given));
}

static int hexv(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

bool query_get(const char *query, const char *key, char *out, size_t outlen) {
  if (!query || !key || !out || outlen == 0) return false;
  out[0] = '\0';
  size_t klen = strlen(key);
  const char *p = query;
  while (*p) {
    const char *amp = strchr(p, '&');
    size_t seglen = amp ? (size_t)(amp - p) : strlen(p);
    if (seglen > klen && strncmp(p, key, klen) == 0 && p[klen] == '=') {
      const char *v = p + klen + 1;
      const char *end = p + seglen;
      size_t o = 0;
      while (v < end) {
        char c = *v;
        if (c == '+') {
          c = ' ';
          v++;
        } else if (c == '%') {
          if (end - v < 3) goto fail;
          int h = hexv(v[1]), l = hexv(v[2]);
          if (h < 0 || l < 0) goto fail;
          c = (char)((h << 4) | l);
          v += 3;
        } else {
          v++;
        }
        if (c == '\0') goto fail;  // %00 einschleusen verboten
        if (o + 1 >= outlen) goto fail;
        out[o++] = c;
      }
      out[o] = '\0';
      return true;
    }
    if (!amp) break;
    p = amp + 1;
  }
  return false;
fail:
  out[0] = '\0';  // nie einen halb entschlüsselten Wert zurückgeben
  return false;
}

bool valid_ssid(const char *s) {
  if (!s) return false;
  size_t n = strlen(s);
  if (n < 1 || n > 32) return false;
  for (size_t i = 0; i < n; i++)
    if ((uint8_t)s[i] < 0x20 || (uint8_t)s[i] == 0x7f) return false;
  return true;
}

bool valid_wifi_pass(const char *s) {
  if (!s) return false;
  size_t n = strlen(s);
  if (n < 8 || n > 63) return false;
  for (size_t i = 0; i < n; i++)
    if ((uint8_t)s[i] < 0x20 || (uint8_t)s[i] > 0x7e) return false;
  return true;
}

bool valid_token(const char *s) {
  if (!s) return false;
  size_t n = strlen(s);
  if (n < 16 || n > 64) return false;
  for (size_t i = 0; i < n; i++) {
    char c = s[i];
    bool ok = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '-' || c == '_';
    if (!ok) return false;
  }
  return true;
}

bool valid_hostname(const char *s) {
  if (!s) return false;
  size_t n = strlen(s);
  if (n < 1 || n > 32 || s[0] == '-' || s[n - 1] == '-') return false;
  for (size_t i = 0; i < n; i++) {
    char c = s[i];
    if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-')) return false;
  }
  return true;
}

void random_password(const uint32_t r[12], char out[13]) {
  static const char alphabet[] = "23456789abcdefghjkmnpqrstuvwxyz";  // 31 Zeichen, ohne 0/O/1/l/I
  for (int i = 0; i < 12; i++) out[i] = alphabet[r[i] % 31u];
  out[12] = '\0';
}

uint32_t backoff_ms(unsigned attempt) {
  if (attempt >= 6) return 60000u;
  uint32_t v = 1000u << attempt;
  return v > 60000u ? 60000u : v;
}

bool gate_blocked(const FailGate &g, uint32_t now_ms) {
  return g.locked && (int32_t)(g.locked_until - now_ms) > 0;
}

void gate_fail(FailGate &g, uint32_t now_ms, uint16_t max_fail, uint32_t window_ms, uint32_t lock_ms) {
  if (g.locked && (int32_t)(g.locked_until - now_ms) <= 0) {
    g.locked = false;
    g.fails = 0;
  }
  if (g.fails == 0 || (uint32_t)(now_ms - g.window_start) > window_ms) {
    g.window_start = now_ms;
    g.fails = 0;
  }
  if (g.fails < 0xFFFF) g.fails++;
  if (g.fails >= max_fail) {
    g.locked = true;
    g.locked_until = now_ms + lock_ms;
  }
}

void gate_ok(FailGate &g) {
  g.fails = 0;
  g.locked = false;
}

uint32_t frame_interval_ms(unsigned fps) {
  if (fps == 0) return 0;
  return 1000u / fps;
}

int status_json(char *buf, size_t n, const Status &s) {
  if (!buf || n == 0) return -1;
  int w = snprintf(buf, n,
                   "{\"version\":\"%s\",\"hostname\":\"%s\",\"uptime_s\":%lu,\"rssi\":%d,\"free_heap\":%lu,"
                   "\"free_psram\":%lu,\"frames\":%lu,\"cam_errors\":%lu,\"reboots_bad\":%lu,\"width\":%u,"
                   "\"height\":%u,\"streaming\":%s}",
                   s.version ? s.version : "", s.hostname ? s.hostname : "", (unsigned long)s.uptime_s, s.rssi,
                   (unsigned long)s.free_heap, (unsigned long)s.free_psram, (unsigned long)s.frames,
                   (unsigned long)s.cam_errors, (unsigned long)s.reboots_bad, (unsigned)s.width, (unsigned)s.height,
                   s.streaming ? "true" : "false");
  if (w < 0 || (size_t)w >= n) {
    buf[0] = '\0';
    return -1;
  }
  return w;
}

int part_header(char *buf, size_t n, size_t jpg_len, uint32_t ts_ms) {
  if (!buf || n == 0) return -1;
  int w = snprintf(buf, n,
                   "\r\n--h3kframe\r\nContent-Type: image/jpeg\r\nContent-Length: %lu\r\nX-Timestamp: %lu\r\n\r\n",
                   (unsigned long)jpg_len, (unsigned long)ts_ms);
  if (w < 0 || (size_t)w >= n) {
    buf[0] = '\0';
    return -1;
  }
  return w;
}

}  // namespace h3k
