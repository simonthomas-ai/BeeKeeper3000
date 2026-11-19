// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
package org.hornet3000.station;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Build;

/** Einstellungen der App (nur für diese App lesbar; Datensicherung in der Cloud ist im Manifest abgeschaltet). */
final class Prefs {
    private static final String FILE = "hornet3000_station";
    private final SharedPreferences p;

    Prefs(Context c) {
        p = c.getSharedPreferences(FILE, Context.MODE_PRIVATE);
    }

    String server() {
        return p.getString("server", "");
    }

    String token() {
        return p.getString("token", "");
    }

    String station() {
        String d = Client.headerStation(Build.MODEL == null ? "Station" : Build.MODEL);
        return p.getString("station", d);
    }

    String pin() {
        return p.getString("pin", "");
    }

    int camera() {
        return p.getInt("camera", 0);
    }

    void save(String server, String token, String station, String pin) {
        p.edit().putString("server", server.trim()).putString("token", token.trim())
                .putString("station", station.trim()).putString("pin", pin.trim()).commit();
    }

    void saveCamera(int index) {
        p.edit().putInt("camera", index).commit();
    }

    /** Baut den Client aus den gespeicherten Werten; wirft IllegalArgumentException mit verständlichem Text. */
    Client client() {
        return new Client(server(), token(), station(), pin());
    }
}
