// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
package org.hornet3000.station;

/** Kleine reine Rechenhilfen für die Kamera (in der JVM prüfbar). */
public final class Logic {
    private Logic() {
    }

    /**
     * Wählt aus den Vorschaugrößen der Kamera die größte, deren Breite höchstens maxWidth beträgt und die mindestens
     * minWidth breit ist; gibt es keine, die kleinste mit mindestens minWidth … sonst die kleinste überhaupt.
     * Rückgabe: Index in die Felder, -1 bei leerer Liste.
     */
    public static int chooseSize(int[] w, int[] h, int maxWidth, int minWidth) {
        if (w == null || h == null || w.length == 0 || w.length != h.length) {
            return -1;
        }
        int best = -1;
        for (int i = 0; i < w.length; i++) {
            if (w[i] <= 0 || h[i] <= 0 || w[i] > maxWidth || w[i] < minWidth) {
                continue;
            }
            if (best < 0 || (long) w[i] * h[i] > (long) w[best] * h[best]) {
                best = i;
            }
        }
        if (best >= 0) {
            return best;
        }
        for (int i = 0; i < w.length; i++) {                         // nichts im Bereich: die kleinste über minWidth …
            if (w[i] <= 0 || h[i] <= 0 || w[i] < minWidth) {
                continue;
            }
            if (best < 0 || (long) w[i] * h[i] < (long) w[best] * h[best]) {
                best = i;
            }
        }
        if (best >= 0) {
            return best;
        }
        for (int i = 0; i < w.length; i++) {                         // … sonst die größte unter minWidth
            if (w[i] <= 0 || h[i] <= 0) {
                continue;
            }
            if (best < 0 || (long) w[i] * h[i] > (long) w[best] * h[best]) {
                best = i;
            }
        }
        return best;
    }

    /** Kleinste Bildrate der Kamera, die für das gewünschte Intervall reicht (mindestens 1); -1 = keine Angabe. */
    public static int chooseFrameRate(int[] rates, int intervalMs) {
        if (rates == null || rates.length == 0) {
            return -1;
        }
        int need = Math.max(1, (int) Math.ceil(1000.0 / Math.max(200, intervalMs)));
        int best = -1;
        int max = -1;
        for (int i = 0; i < rates.length; i++) {
            if (rates[i] <= 0) {
                continue;
            }
            max = Math.max(max, rates[i]);
            if (rates[i] >= need && (best < 0 || rates[i] < best)) {
                best = rates[i];
            }
        }
        return best >= 0 ? best : max;
    }

    /** NV21-Bild hat Breite·Höhe·3/2 Bytes. */
    public static boolean nv21Fits(int length, int w, int h) {
        return w > 0 && h > 0 && (long) length >= (long) w * h * 3 / 2;
    }
}
