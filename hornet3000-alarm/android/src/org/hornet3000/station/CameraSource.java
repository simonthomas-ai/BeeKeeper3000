// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
package org.hornet3000.station;

import android.graphics.ImageFormat;
import android.graphics.Rect;
import android.graphics.YuvImage;
import android.hardware.Camera;

import java.io.ByteArrayOutputStream;

/**
 * Bildquelle der Station auf dem Gerät: nimmt die Vorschaubilder der Kamera (NV21) entgegen, hält nur das neueste und
 * macht daraus erst auf Anfrage ein JPEG – so bleibt die Last auf alten Geräten klein.
 */
final class CameraSource implements StationLoop.Source, Camera.PreviewCallback {
    private final Object lock = new Object();
    private byte[] latest;
    private int w, h;
    private long seq, taken;

    void setSize(int w, int h) {
        synchronized (lock) {
            this.w = w;
            this.h = h;
            latest = null;
        }
    }

    public void onPreviewFrame(byte[] data, Camera camera) {
        synchronized (lock) {
            latest = data;
            seq++;
            lock.notifyAll();
        }
    }

    public byte[] next(int quality, int maxBytes, long waitMs) throws InterruptedException {
        byte[] d;
        int ww, hh;
        synchronized (lock) {
            if (seq == taken) {
                lock.wait(waitMs);
            }
            if (seq == taken || latest == null) {
                return null;
            }
            d = latest;
            ww = w;
            hh = h;
            taken = seq;
        }
        if (!Logic.nv21Fits(d.length, ww, hh)) {
            return null;
        }
        YuvImage img = new YuvImage(d, ImageFormat.NV21, ww, hh, null);
        ByteArrayOutputStream bo = new ByteArrayOutputStream(64 * 1024);
        int q = quality;
        for (;;) {
            bo.reset();
            if (!img.compressToJpeg(new Rect(0, 0, ww, hh), q, bo)) {
                return null;
            }
            if (bo.size() <= maxBytes || q <= 25) {
                break;
            }
            q -= 15;
        }
        return bo.toByteArray();
    }
}
