// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
package org.hornet3000.station;

import java.util.List;

/**
 * Abfrageschleife der Alarm-Anzeige: fragt den Wächter regelmäßig ab und meldet neue Alarme. Reines Java (JVM-geprüft).
 * Bei Verbindungsfehlern wird weiter versucht (nach 3 Fehlern seltener); bei abgelehntem Schlüssel endet die Schleife.
 */
public final class PollLoop implements Runnable {
    public interface Listener {
        /** fresh = neue Meldungen seit der letzten Abfrage (älteste zuerst, leer bei der allerersten Abfrage). */
        void onPoll(Model.Poll poll, List<Model.Alert> fresh);

        void onError(int failures, String text, boolean fatal);
    }

    private final Client client;
    private final Listener listener;
    private final long periodMs;
    private final AlertTracker tracker = new AlertTracker();
    private final Object lock = new Object();
    private volatile boolean stop;
    private boolean nudge;
    private int failures;

    public PollLoop(Client client, Listener listener, long periodMs) {
        this.client = client;
        this.listener = listener;
        this.periodMs = Math.max(1000, periodMs);
    }

    public void stop() {
        stop = true;
        synchronized (lock) {
            lock.notifyAll();
        }
    }

    /** Sofort abfragen (z. B. nach „Stumm schalten“). */
    public void pollNow() {
        synchronized (lock) {
            nudge = true;
            lock.notifyAll();
        }
    }

    private void pause(long ms) throws InterruptedException {
        long end = System.currentTimeMillis() + ms;
        synchronized (lock) {
            while (!stop && !nudge) {
                long left = end - System.currentTimeMillis();
                if (left <= 0) {
                    break;
                }
                lock.wait(left);
            }
            nudge = false;
        }
    }

    public void run() {
        try {
            while (!stop) {
                try {
                    Model.Poll p = client.poll(tracker.since());
                    List<Model.Alert> fresh = tracker.update(p);
                    failures = 0;
                    listener.onPoll(p, fresh);
                } catch (ApiException e) {
                    if (e.isAuth()) {
                        listener.onError(++failures, "Zugangsschlüssel abgelehnt – bitte in den Einstellungen prüfen", true);
                        return;
                    }
                    failures++;
                    listener.onError(failures, e.getMessage(), false);
                }
                pause(failures > 3 ? 15000 : periodMs);
            }
        } catch (InterruptedException e) {
            // beendet
        }
    }
}
