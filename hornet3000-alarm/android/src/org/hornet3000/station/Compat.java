// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
package org.hornet3000.station;

import android.app.Activity;
import android.hardware.Camera;
import android.os.Build;

import java.lang.reflect.Method;

/**
 * Alles, was es erst auf neueren Android-Versionen gibt, kommt hier per Reflexion – so wird der übrige Code gegen die
 * Systembibliothek von Android 2.2 (API 8) übersetzt und der Compiler lehnt jede zu neue Funktion ab.
 */
final class Compat {
    private Compat() {
    }

    static int sdk() {
        return Build.VERSION.SDK_INT;
    }

    /** Anzahl der Kameras (ab Android 2.3; davor genau eine). */
    static int cameraCount() {
        try {
            Method m = Camera.class.getMethod("getNumberOfCameras");
            int n = ((Integer) m.invoke(null)).intValue();
            return Math.max(1, n);
        } catch (Throwable t) {
            return 1;
        }
    }

    /** Öffnet die Kamera mit dieser Nummer; ohne Nummern-Unterstützung (Android 2.2) die einzige. */
    static Camera openCamera(int index) {
        if (index > 0 || cameraCount() > 1) {
            try {
                Method m = Camera.class.getMethod("open", int.class);
                return (Camera) m.invoke(null, Integer.valueOf(index));
            } catch (Throwable t) {
                // fällt zurück auf open()
            }
        }
        return Camera.open();
    }

    /** „hinten“, „vorne“ oder „“ (unbekannt). */
    static String facing(int index) {
        try {
            Class<?> ci = Class.forName("android.hardware.Camera$CameraInfo");
            Object info = ci.newInstance();
            Camera.class.getMethod("getCameraInfo", int.class, ci).invoke(null, Integer.valueOf(index), info);
            int f = ci.getField("facing").getInt(info);
            return f == 1 ? "vorne" : "hinten";
        } catch (Throwable t) {
            return "";
        }
    }

    /** Hat die App die Kamera-Erlaubnis? Vor Android 6 wird sie bei der Installation erteilt. */
    static boolean hasCameraPermission(Activity a) {
        return a.checkPermission("android.permission.CAMERA", android.os.Process.myPid(), android.os.Process.myUid())
                == android.content.pm.PackageManager.PERMISSION_GRANTED;
    }

    /** Fragt ab Android 6 nach der Kamera-Erlaubnis (vorher gibt es nichts zu fragen). */
    static void requestCameraPermission(Activity a, int code) {
        if (sdk() < 23) {
            return;
        }
        try {
            Method m = Activity.class.getMethod("requestPermissions", String[].class, int.class);
            m.invoke(a, new Object[] {new String[] {"android.permission.CAMERA"}, Integer.valueOf(code)});
        } catch (Throwable t) {
            // ohne Abfrage bleibt nur der Hinweistext in der Oberfläche
        }
    }
}
