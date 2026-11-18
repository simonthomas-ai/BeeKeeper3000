// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
package org.hornet3000.station;

import java.util.ArrayList;
import java.util.List;

/**
 * Merkt sich, welche Meldungen schon gesehen sind (wie die Handy-Webseite): Die allererste Abfrage setzt nur den Stand,
 * damit beim Start kein alter Alarm läuft. Danach gilt jede Meldung mit höherer Nummer als neu.
 */
public final class AlertTracker {
    private long since = -1;

    /** Wert für ?since= der nächsten Abfrage. */
    public long since() {
        return since < 0 ? 0 : since;
    }

    /** Neue Meldungen, älteste zuerst. */
    public List<Model.Alert> update(Model.Poll p) {
        List<Model.Alert> fresh = new ArrayList<Model.Alert>();
        if (since < 0 || p.newestId < since) {          // erste Abfrage – oder Datenbank des Wächters wurde zurückgesetzt
            since = p.newestId;
            return fresh;
        }
        for (int i = p.alerts.size() - 1; i >= 0; i--) {
            Model.Alert a = p.alerts.get(i);
            if (a.id > since) {
                fresh.add(a);
            }
        }
        // Reihenfolge sicherstellen, egal wie der Server sortiert
        for (int a = 1; a < fresh.size(); a++) {
            Model.Alert x = fresh.get(a);
            int b = a - 1;
            while (b >= 0 && fresh.get(b).id > x.id) {
                fresh.set(b + 1, fresh.get(b));
                b--;
            }
            fresh.set(b + 1, x);
        }
        if (p.newestId > since) {
            since = p.newestId;
        }
        return fresh;
    }

    /** Welche von mehreren neuen Meldungen angezeigt wird: die neueste „Neue Sichtung“, sonst die neueste überhaupt. */
    public static Model.Alert pickTop(List<Model.Alert> fresh) {
        if (fresh.isEmpty()) {
            return null;
        }
        Model.Alert top = fresh.get(fresh.size() - 1);
        for (int i = 0; i < fresh.size(); i++) {
            if ("new".equals(fresh.get(i).kind)) {
                top = fresh.get(i);
            }
        }
        return top;
    }
}
