// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
package org.hornet3000.station;

/**
 * Schleife der Kamera-Station: holt in passendem Takt ein Bild von der Quelle (auf dem Gerät: die Kamera-Vorschau) und
 * liefert es beim Wächter ab. Reines Java – die ganze Wiederholungs- und Wartelogik wird in der JVM gegen den echten
 * Server geprüft; nur die Bildquelle ist auf dem Gerät etwas anderes (Kamera) als im Test (Bilddatei).
 *
 * Verhalten bei Fehlern:
 *   keine Verbindung      → Wartezeit 1, 2, 4, 8, 15 s, dann alle 15 s; meldet „getrennt“, macht aber immer weiter
 *   429 (zu schnell)      → wartet die vom Server genannte Zeit
 *   409 (andere Station)  → wartet 5 s und versucht es wieder (die andere Station kann ausfallen)
 *   401/403 (Schlüssel)   → bricht ab (nochmal senden würde nur die Sperre des Servers auslösen)
 *   400/413/415           → Bild abgelehnt: 5 s warten; nach 6 Ablehnungen in Folge Abbruch mit Erklärung
 *   alles andere (5xx …)  → 5 s warten, weiter
 */
public final class StationLoop implements Runnable {
    public static final int OK = 0;       // Bilder kommen an
    public static final int WAIT = 1;     // läuft, aber gerade kein Erfolg (Wartezeit)
    public static final int ERROR = 2;    // Problem, es wird weiter versucht
    public static final int FATAL = 3;    // Schleife ist beendet

    /** Bildquelle. */
    public interface Source {
        /** Nächstes Bild als JPEG (höchstens maxBytes, möglichst quality), wartet höchstens waitMs; null = gerade keins. */
        byte[] next(int quality, int maxBytes, long waitMs) throws InterruptedException;
    }

    public interface Listener {
        void onState(int kind, String text);

        void onSent(long total, int bytes);
    }

    private final Client client;
    private final Source source;
    private final Listener listener;
    private volatile boolean stop;
    private volatile Thread thread;

    private long sent;
    private int failures;
    private int rejects;
    private long downSince;

    public StationLoop(Client client, Source source, Listener listener) {
        this.client = client;
        this.source = source;
        this.listener = listener;
    }

    public void stop() {
        stop = true;
        Thread t = thread;
        if (t != null) {
            t.interrupt();
        }
    }

    public long sent() {
        return sent;
    }

    private void sleep(long ms) throws InterruptedException {
        long end = System.currentTimeMillis() + ms;
        while (!stop) {
            long left = end - System.currentTimeMillis();
            if (left <= 0) {
                return;
            }
            Thread.sleep(Math.min(left, 500));
        }
        throw new InterruptedException();
    }

    static long backoffMs(int failures) {
        if (failures <= 1) {
            return 1000;
        }
        if (failures == 2) {
            return 2000;
        }
        if (failures == 3) {
            return 4000;
        }
        if (failures == 4) {
            return 8000;
        }
        return 15000;
    }

    public void run() {
        thread = Thread.currentThread();
        try {
            loop();
        } catch (InterruptedException e) {
            // beendet
        } finally {
            thread = null;
        }
    }

    private void loop() throws InterruptedException {
        Model.Config cfg = new Model.Config();
        boolean haveCfg = false;
        int interval = cfg.intervalMs;
        long lastSend = 0;
        int quality = cfg.quality;
        while (!stop) {
            if (!haveCfg) {
                try {
                    cfg = client.config();
                    interval = cfg.intervalMs;
                    quality = cfg.quality;
                    haveCfg = true;
                } catch (ApiException e) {
                    if (e.isAuth()) {
                        listener.onState(FATAL, "Zugangsschlüssel abgelehnt – bitte in den Einstellungen prüfen");
                        return;
                    }
                    if (e.status == 409) {              // Quelle am Wächter ist nicht „push“
                        listener.onState(ERROR, e.getMessage());
                        sleep(10000);
                        continue;
                    }
                    if (e.isNetwork()) {
                        fail(e);
                        continue;
                    }
                    // anderer Fehler: mit Vorgaben weitermachen
                    haveCfg = true;
                }
            }
            long wait = interval - (System.currentTimeMillis() - lastSend);
            if (wait > 0) {
                sleep(wait);
            }
            byte[] jpeg = source.next(quality, cfg.maxBytes, 1000);
            if (jpeg == null) {
                continue;
            }
            try {
                Model.FrameReply r = client.sendFrame(jpeg);
                lastSend = System.currentTimeMillis();
                sent++;
                failures = 0;
                rejects = 0;
                quality = Math.min(cfg.quality, quality + 5);      // nach Erfolg langsam wieder Richtung Wunschqualität
                downSince = 0;
                interval = Math.max(cfg.minIntervalMs, Math.max(r.intervalMs, 200));
                listener.onSent(sent, jpeg.length);
                listener.onState(OK, "Sendet Bilder an den Wächter");
            } catch (ApiException e) {
                lastSend = System.currentTimeMillis();
                if (e.isAuth()) {
                    listener.onState(FATAL, "Zugangsschlüssel abgelehnt – bitte in den Einstellungen prüfen");
                    return;
                }
                if (e.isNetwork()) {
                    fail(e);
                } else if (e.status == 429) {
                    listener.onState(WAIT, "Wächter bremst (zu viele Bilder) – kurze Pause");
                    sleep(Math.max(300, e.retryMs));
                } else if (e.status == 409) {
                    listener.onState(WAIT, e.getMessage());
                    sleep(Math.max(5000, e.retryMs));
                } else if (e.status == 400 || e.status == 413 || e.status == 415) {
                    rejects++;
                    if (e.status == 413) {
                        quality = Math.max(25, quality - 15);         // zu groß: nächstes Bild stärker komprimieren
                    }
                    if (rejects >= 6) {
                        listener.onState(FATAL, "Der Wächter lehnt die Bilder dieses Geräts ab: " + e.getMessage());
                        return;
                    }
                    listener.onState(ERROR, "Bild abgelehnt: " + e.getMessage());
                    sleep(5000);
                } else {
                    listener.onState(ERROR, "Wächter meldet: " + e.getMessage());
                    sleep(Math.max(5000, e.retryMs));
                }
            }
        }
    }

    private void fail(ApiException e) throws InterruptedException {
        failures++;
        if (downSince == 0) {
            downSince = System.currentTimeMillis();
        }
        long secs = (System.currentTimeMillis() - downSince) / 1000;
        listener.onState(ERROR, e.getMessage() + (secs > 2 ? " (seit " + secs + " s)" : "") + " – es wird weiter versucht");
        sleep(backoffMs(failures));
    }
}
