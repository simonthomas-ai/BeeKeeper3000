#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
# Übersetzt die Firmware-Logik für den Rechner (mit AddressSanitizer + UndefinedBehaviorSanitizer) und führt die Tests aus.
set -e
cd "$(dirname "$0")"
OUT="${TMPDIR:-/tmp}/h3k-native-test"
g++ -std=c++17 -O1 -g -Wall -Wextra -Werror -fsanitize=address,undefined -fno-sanitize-recover=all \
    -o "$OUT" test_core.cpp ../../src/core.cpp
DUMP_STATUS=1 "$OUT" | tee "$OUT.log"
# das ausgegebene Status-JSON muss gültiges JSON sein
grep '^{' "$OUT.log" | python3 -c 'import sys,json; d=json.loads(sys.stdin.read()); assert d["width"]==640 and d["streaming"] is True; print("Status-JSON gültig")'
