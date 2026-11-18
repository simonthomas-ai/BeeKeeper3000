// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
package org.hornet3000.station;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/** Antworten des Wächters als einfache Datenobjekte (alle Werte werden begrenzt/bereinigt, bevor die Oberfläche sie sieht). */
public final class Model {
    private Model() {
    }

    private static int clamp(long v, int lo, int hi) {
        return (int) Math.max(lo, Math.min(hi, v));
    }

    /** Empfehlung des Servers für die Station (GET /api/station/config). */
    public static final class Config {
        public int intervalMs = 1000;
        public int width = 640;
        public int quality = 70;
        public int maxBytes = 1 << 20;
        public int minIntervalMs = 200;

        public static Config from(Map<String, Object> m) {
            Config c = new Config();
            c.minIntervalMs = clamp(Json.lng(m, "min_interval_ms", 200), 100, 10000);
            c.intervalMs = clamp(Json.lng(m, "interval_ms", 1000), Math.max(200, c.minIntervalMs), 60000);
            c.width = clamp(Json.lng(m, "width", 640), 160, 1280);
            c.quality = clamp(Json.lng(m, "quality", 70), 30, 95);
            c.maxBytes = clamp(Json.lng(m, "max_bytes", 1 << 20), 20000, 1 << 20);
            return c;
        }
    }

    /** Antwort auf ein gesendetes Bild. */
    public static final class FrameReply {
        public int intervalMs;
    }

    public static final class Alert {
        public long id;
        public double ts;
        public String kind = "";
        public String species = "";
        public String label = "";
        public int count;
        public double conf;
        public boolean muted;
        public String snapshotUrl = "";
        public String clipUrl = "";

        public static Alert from(Map<String, Object> m) {
            Alert a = new Alert();
            a.id = Json.lng(m, "id", 0);
            a.ts = Json.num(m, "ts", 0);
            a.kind = limit(Json.str(m, "kind", ""), 20);
            a.species = limit(Json.str(m, "species", ""), 80);
            a.label = limit(Json.str(m, "label", ""), 80);
            a.count = clamp(Json.lng(m, "count", 0), 0, 1000000);
            a.conf = Json.num(m, "conf", 0);
            a.muted = Json.bool(m, "muted", false);
            a.snapshotUrl = Json.str(m, "snapshot_url", "");
            a.clipUrl = Json.str(m, "clip_url", "");
            return a;
        }

        /** Gleiche Beschreibung wie auf der Handy-Webseite: „Art · n Tiere · 87 %“. */
        public String text() {
            String t = label.length() > 0 ? label : species.length() > 0 ? species : "Hornisse";
            if (count > 0) {
                t += " · " + count + (count == 1 ? " Tier" : " Tiere");
            }
            if (conf > 0) {
                t += " · " + Math.round(conf * 100) + " %";
            }
            return t;
        }

        public static String kindName(String k) {
            if ("new".equals(k)) {
                return "Neue Sichtung";
            }
            if ("update".equals(k)) {
                return "Weitere Sichtung";
            }
            if ("test".equals(k)) {
                return "Testalarm";
            }
            if ("reminder".equals(k)) {
                return "Erinnerung";
            }
            return k.length() > 0 ? k : "Meldung";
        }
    }

    /** Antwort von GET /api/mobile/poll. */
    public static final class Poll {
        public String version = "";
        public String cameraName = "";
        public String cameraState = "";
        public boolean cameraOnline;
        public String station = "";
        public double fps;
        public boolean muted;
        public double muteUntil;
        public int alarms24h;
        public int detectionsNow;
        public long newestId;
        public List<Alert> alerts = new ArrayList<Alert>();

        public static Poll from(Map<String, Object> m) {
            Poll p = new Poll();
            p.version = limit(Json.str(m, "version", ""), 20);
            Map<String, Object> c = Json.obj(m.get("camera"));
            p.cameraName = limit(Json.str(c, "name", ""), 60);
            p.cameraState = limit(Json.str(c, "state", ""), 20);
            p.cameraOnline = Json.bool(c, "online", false);
            p.station = limit(Json.str(c, "station", ""), 60);
            p.fps = Json.num(c, "fps", 0);
            p.muted = Json.bool(m, "muted", false);
            p.muteUntil = Json.num(m, "mute_until", 0);
            p.alarms24h = clamp(Json.lng(m, "alarms_24h", 0), 0, 100000000);
            p.detectionsNow = clamp(Json.lng(m, "detections_now", 0), 0, 100000);
            p.newestId = Json.lng(m, "newest_id", 0);
            List<Object> l = Json.list(m.get("alerts"));
            for (int i = 0; i < l.size() && i < 50; i++) {
                p.alerts.add(Alert.from(Json.obj(l.get(i))));
            }
            return p;
        }

        public String cameraText() {
            String st = "online".equals(cameraState) ? "online"
                    : "waiting".equals(cameraState) ? "wartet auf Bild"
                    : "offline".equals(cameraState) ? "OFFLINE" : (cameraState.length() > 0 ? cameraState : "?");
            String t = (cameraName.length() > 0 ? cameraName + " – " : "") + st;
            if (station.length() > 0) {
                t += " (Station " + station + (fps > 0 ? ", " + fps + " Bilder/s" : "") + ")";
            }
            return t;
        }
    }

    static String limit(String s, int max) {
        return s.length() > max ? s.substring(0, max) : s;
    }
}
