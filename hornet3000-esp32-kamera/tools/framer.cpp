// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
// Hilfsprogramm für die Prüfung: nutzt den ECHTEN Firmware-Code (core.cpp) für die Mehrteil-Rahmen der Übertragung.
// stdin: wiederholt [4 Byte Länge little-endian][JPEG]  →  stdout: Kopf (part_header) + JPEG, genau wie h_stream() es sendet.
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "../src/core.h"
int main() {
  uint32_t ts = 0;
  for (;;) {
    uint8_t lb[4];
    if (fread(lb, 1, 4, stdin) != 4) return 0;
    uint32_t n = lb[0] | (lb[1] << 8) | (lb[2] << 16) | ((uint32_t)lb[3] << 24);
    if (n == 0 || n > 4u * 1024 * 1024) return 2;
    uint8_t *buf = (uint8_t *)malloc(n);
    if (fread(buf, 1, n, stdin) != n) return 3;
    char head[160];
    int hl = h3k::part_header(head, sizeof head, n, ts);
    if (hl < 0) return 4;
    ts += 125;
    fwrite(head, 1, hl, stdout);
    fwrite(buf, 1, n, stdout);
    fflush(stdout);
    free(buf);
  }
}
