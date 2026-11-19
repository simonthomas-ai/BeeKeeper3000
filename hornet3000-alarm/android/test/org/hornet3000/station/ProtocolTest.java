// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
package org.hornet3000.station;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;

/**
 * Prüfung des Netzwerk- und Ablaufteils der Android-App in der JVM (dieselben Quelldateien wie in der APK).
 * ECHT: Client, StationLoop, PollLoop, Json, AlertTracker laufen unverändert gegen den ECHTEN Hornet3000-Wächter
 *       (eigener Prozess, echte Datenbank, echtes Erkennungsmodell, Anmeldung, Begrenzungen), auch per HTTPS mit Fingerabdruck.
 * TESTSTAND (kein Teil der App): (1) Bildquelle FileSource liefert Bilddateien statt Kamera-Vorschau;
 *       (2) TcpProxy zwischen App-Code und echtem Wächter, um Ausfall und Wiederkehr zu erzeugen;
 *       (3) ein kleiner HTTP-Server, der absichtlich schlechtes Verhalten zeigt (Weiterleitung, riesige oder kaputte Antwort).
 * NICHT geprüft: Android-Teile (Kamera, Oberfläche, Ton) – sie lassen sich ohne Gerät nicht ausführen.
 * Aufruf: ProtocolTest HTTP-BASIS TOKEN BILDORDNER [HTTPS-BASIS PIN-RICHTIG]
 */
public class ProtocolTest {
    static int checks = 0;
    static final List<String> problems = new ArrayList<String>();
    static String base, token, imgDir, httpsBase, pinGood;

    static void check(boolean ok, String what) {
        checks++;
        if (ok) {
            System.out.println("  \u2713 " + what);
        } else {
            problems.add(what);
            System.out.println("  \u2717 " + what);
        }
    }

    static void section(String s) {
        System.out.println("\n== " + s);
    }

    static byte[] file(String name) throws IOException {
        return Files.readAllBytes(new File(imgDir, name).toPath());
    }

    static void pause(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException e) {
            throw new RuntimeException(e);
        }
    }

    interface Call {
        void run() throws Exception;
    }

    static ApiException expectApi(Call c) {
        try {
            c.run();
        } catch (ApiException e) {
            return e;
        } catch (Exception e) {
            throw new RuntimeException("falsche Ausnahme: " + e, e);
        }
        return null;
    }

    static IllegalArgumentException expectIae(Call c) {
        try {
            c.run();
        } catch (IllegalArgumentException e) {
            return e;
        } catch (Exception e) {
            throw new RuntimeException("falsche Ausnahme: " + e, e);
        }
        return null;
    }

    // ================================================================================================================
    public static void main(String[] a) throws Exception {
        base = a[0];
        token = a[1];
        imgDir = a[2];
        httpsBase = a.length > 4 ? a[3] : null;
        pinGood = a.length > 4 ? a[4] : null;
        long t0 = System.currentTimeMillis();

        unitJson();
        unitClientInput();
        unitModelAndTracker();
        unitLogic();
        hostileServer();
        realServerCalls();
        loopsAgainstRealServer();
        pollLoopAgainstRealServer();
        if (httpsBase != null) {
            httpsPinning();
        }
        takeover();

        System.out.println("\n" + checks + " Pr\u00fcfungen, " + problems.size() + " Verst\u00f6\u00dfe, "
                + (System.currentTimeMillis() - t0) / 1000 + " s");
        if (!problems.isEmpty()) {
            System.out.println("ANDROID-PROTOKOLL: DURCHGEFALLEN");
            for (String p : problems) {
                System.out.println(" - " + p);
            }
            System.exit(1);
        }
        System.out.println("ANDROID-PROTOKOLL: BESTANDEN");
    }

    // ---- Einheiten ---------------------------------------------------------------------------------------------------
    static void unitJson() {
        section("Json");
        java.util.Map<String, Object> m = Json.obj(Json.parse("{\"a\":1,\"b\":[true,false,null,\"x\\u00e4\\n\\\"\"],\"c\":{\"d\":-2.5e1}}"));
        check(Json.lng(m, "a", 0) == 1, "Zahl gelesen");
        List<Object> l = Json.list(m.get("b"));
        check(l.size() == 4 && Boolean.TRUE.equals(l.get(0)) && Boolean.FALSE.equals(l.get(1)) && l.get(2) == null, "Liste mit true/false/null");
        check("x\u00e4\n\"".equals(l.get(3)), "Escape-Folgen und \\u00e4");
        check(Json.num(Json.obj(m.get("c")), "d", 0) == -25.0, "Exponent-Schreibweise");
        check(Json.lng(m, "fehlt", 7) == 7 && Json.str(m, "a", "def").equals("def"), "falscher Typ/fehlender Schl\u00fcssel ergibt Vorgabe");
        String[] bad = {"", "{", "{\"a\":}", "[1,]", "{\"a\" 1}", "nul", "01", "1.", "-", "\"abc", "\"\\x\"", "\"\\u12\"", "[1] x", "{'a':1}",
                "\"\u0001\"", "tru", "[1 2]", "{\"a\":1,}", "1e", "\"\\u00zz\""};
        int rejected = 0;
        for (String s : bad) {
            try {
                Json.parse(s);
            } catch (IllegalArgumentException e) {
                rejected++;
            }
        }
        check(rejected == bad.length, "alle " + bad.length + " ung\u00fcltigen JSON-Texte abgelehnt (" + rejected + ")");
        StringBuilder deep = new StringBuilder();
        for (int i = 0; i < 100; i++) {
            deep.append('[');
        }
        check(expectIae(() -> Json.parse(deep.toString())) != null, "zu tiefe Schachtelung abgelehnt");
        StringBuilder big = new StringBuilder("\"");
        for (int i = 0; i < Json.MAX_CHARS + 10; i++) {
            big.append('a');
        }
        check(expectIae(() -> Json.parse(big.toString())) != null, "\u00fcbergro\u00dfer Text abgelehnt");
        check(Json.parse("  [ ]  ") instanceof List && Json.parse("null") == null, "leere Liste, null");
        check(Json.num(Json.obj(Json.parse("{\"x\":1e999}")), "x", 0) > 1e300 && Json.lng(Json.obj(Json.parse("{\"x\":1e999}")), "x", 5) == 5,
                "unendliche Zahl wird als Zahl ohne Absturz behandelt");
    }

    static void unitClientInput() {
        section("Client: Eingaben pr\u00fcfen");
        check(Client.normalizeBase("192.168.1.20:8000").equals("http://192.168.1.20:8000"), "Adresse ohne http:// wird erg\u00e4nzt");
        check(Client.normalizeBase("  HTTPS://Haus.example/hornet/  ").equals("https://Haus.example/hornet"), "https, Gro\u00df/Klein, Pfad ohne Schr\u00e4gstrich am Ende");
        check(Client.normalizeBase("http://[::1]:8000/").equals("http://[::1]:8000"), "IPv6-Adresse");
        String[] badUrls = {"", "   ", "ftp://x", "file:///etc/passwd", "javascript:alert(1)", "http://", "http://user:pw@host", "http://h/?a=1", "http://h/#x",
                "http://h/../x", "http://a b", "http://h/a b"};
        int rej = 0;
        for (String u : badUrls) {
            if (expectIae(() -> Client.normalizeBase(u)) != null) {
                rej++;
            }
        }
        check(rej == badUrls.length, "ung\u00fcltige Adressen abgelehnt (" + rej + "/" + badUrls.length + ")");
        check(expectIae(() -> Client.normalizeBase(new String(new char[300]).replace('\0', 'a'))) != null, "zu lange Adresse abgelehnt");
        String[] badTok = {"", "kurz", "abc def ghi", "abc\r\nX-Evil: 1", "abcdefgh\n", "\u00e4\u00f6\u00fcabcdefg", "abcdefgh;x", "abcdefgh\"x"};
        int tr = 0;
        for (String t : badTok) {
            // „abcdefgh\n“ wird getrimmt und ist dann gültig – deshalb dort kein Fehler erwartet
            if (t.equals("abcdefgh\n")) {
                tr++;
                continue;
            }
            if (expectIae(() -> Client.checkToken(t)) != null) {
                tr++;
            }
        }
        check(tr == badTok.length, "Schl\u00fcssel mit Leerzeichen/Zeilenumbruch/Sonderzeichen abgelehnt (" + tr + "/" + badTok.length + ")");
        check(Client.checkToken("  abcDEF123-_.~+/=  ").equals("abcDEF123-_.~+/="), "g\u00fcltiger Schl\u00fcssel wird getrimmt");
        check(Client.headerStation("Tablet K\u00fcche").equals("Tablet Kueche"), "Umlaut im Stationsnamen wird umgeschrieben");
        check(Client.headerStation("\u00c4\u00d6\u00dc\u00e4\u00f6\u00fc\u00df").equals("AeOeUeaeoeuess"), "alle Umlaute und \u00df");
        check(Client.headerStation("a\r\nX-Evil: 1").equals("aX-Evil 1"), "Zeilenumbruch und Doppelpunkt fliegen raus");
        check(Client.headerStation("").equals("Station") && Client.headerStation("\u20ac\u20ac").equals("Station"), "leerer Name wird \u201eStation\u201c");
        check(Client.headerStation("x").length() == 1 && Client.headerStation(new String(new char[80]).replace('\0', 'b')).length() == 40, "Name h\u00f6chstens 40 Zeichen");
        check(Client.parsePin("") == null && Client.parsePin("  ") == null, "leerer Fingerabdruck = keiner");
        String hex = "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff";
        byte[] p1 = Client.parsePin(hex);
        byte[] p2 = Client.parsePin(Client.hex(p1));
        check(p1.length == 32 && java.util.Arrays.equals(p1, p2) && (p1[10] & 255) == 0xaa, "Fingerabdruck: Hex mit/ohne Doppelpunkte, klein/gro\u00df");
        check(expectIae(() -> Client.parsePin("abc")) != null && expectIae(() -> Client.parsePin(hex.substring(1) + "g")) != null,
                "Fingerabdruck: falsche L\u00e4nge/Zeichen abgelehnt");
        Client c = new Client("127.0.0.1:1", "geheimer-schluessel-123", "x", "");
        check(!c.toString().contains("geheimer"), "toString verr\u00e4t den Schl\u00fcssel nicht");
    }

    static void unitModelAndTracker() {
        section("Model und AlertTracker");
        Model.Config c = Model.Config.from(Json.obj(Json.parse("{\"interval_ms\":5,\"width\":99999,\"quality\":1,\"max_bytes\":5,\"min_interval_ms\":1}")));
        check(c.intervalMs >= 200 && c.width == 1280 && c.quality == 30 && c.maxBytes == 20000 && c.minIntervalMs == 100, "Konfiguration wird begrenzt");
        c = Model.Config.from(Json.obj(Json.parse("{\"interval_ms\":\"x\"}")));
        check(c.intervalMs == 1000 && c.width == 640, "Konfiguration mit Unsinn: Vorgaben");
        Model.Poll p = Model.Poll.from(Json.obj(Json.parse("{\"version\":\"1.2.3\",\"camera\":{\"name\":\"K\",\"online\":true,\"state\":\"online\",\"station\":\"S\",\"fps\":2.5},"
                + "\"muted\":true,\"mute_until\":5,\"alarms_24h\":3,\"detections_now\":1,\"newest_id\":9,"
                + "\"alerts\":[{\"id\":9,\"ts\":1.5,\"kind\":\"new\",\"label\":\"Asiatische Hornisse\",\"count\":2,\"conf\":0.87},{\"id\":8,\"kind\":\"test\"}]}")));
        check(p.alerts.size() == 2 && p.alerts.get(0).text().equals("Asiatische Hornisse \u00b7 2 Tiere \u00b7 87 %"), "Meldungstext wie auf der Handy-Seite");
        check(p.cameraText().equals("K \u2013 online (Station S, 2.5 Bilder/s)") && p.muted && p.newestId == 9, "Kameratext und Felder");
        Model.Poll junk = Model.Poll.from(Json.obj(Json.parse("{\"alerts\":\"x\",\"camera\":5,\"newest_id\":\"a\"}")));
        check(junk.alerts.isEmpty() && junk.newestId == 0 && junk.cameraText().length() > 0, "Poll mit Unsinn st\u00fcrzt nicht ab");
        Model.Alert one = Model.Alert.from(Json.obj(Json.parse("{\"id\":1,\"kind\":\"update\",\"count\":1}")));
        check(one.text().equals("Hornisse \u00b7 1 Tier") && Model.Alert.kindName("update").equals("Weitere Sichtung")
                && Model.Alert.kindName("").equals("Meldung"), "Alert-Text Einzahl, Namen der Arten");

        AlertTracker t = new AlertTracker();
        Model.Poll p1 = poll(5, alert(5, "new"), alert(4, "test"));
        check(t.update(p1).isEmpty() && t.since() == 5, "erste Abfrage setzt nur den Stand (kein alter Alarm)");
        check(t.update(poll(5)).isEmpty(), "nichts Neues");
        List<Model.Alert> f = t.update(poll(8, alert(8, "update"), alert(7, "new"), alert(6, "test")));
        check(f.size() == 3 && f.get(0).id == 6 && f.get(2).id == 8 && t.since() == 8, "neue Meldungen, \u00e4lteste zuerst");
        check(AlertTracker.pickTop(f).id == 7, "pickTop: die neueste \u201eNeue Sichtung\u201c hat Vorrang");
        check(AlertTracker.pickTop(Collections.singletonList(alert(9, "test"))).id == 9 && AlertTracker.pickTop(new ArrayList<Model.Alert>()) == null, "pickTop: einzelne/keine");
        List<Model.Alert> f2 = t.update(poll(3));
        check(f2.isEmpty() && t.since() == 3, "Datenbank beim W\u00e4chter zur\u00fcckgesetzt: kein falscher Alarm, Stand folgt");
        check(t.update(poll(4, alert(4, "new"))).size() == 1, "danach wieder normale Erkennung");
        AlertTracker t2 = new AlertTracker();
        t2.update(poll(1));
        List<Model.Alert> unordered = t2.update(poll(4, alert(2, "new"), alert(4, "new"), alert(3, "new")));
        check(unordered.get(0).id == 2 && unordered.get(1).id == 3 && unordered.get(2).id == 4, "Reihenfolge unabh\u00e4ngig von der Server-Sortierung");
    }

    static Model.Alert alert(long id, String kind) {
        Model.Alert a = new Model.Alert();
        a.id = id;
        a.kind = kind;
        return a;
    }

    static Model.Poll poll(long newest, Model.Alert... al) {
        Model.Poll p = new Model.Poll();
        p.newestId = newest;
        for (Model.Alert x : al) {
            p.alerts.add(x);
        }
        return p;
    }

    static void unitLogic() {
        section("Logic (Kamera-Rechnungen)");
        int[] w = {176, 320, 640, 720, 800, 1280, 1920};
        int[] h = {144, 240, 480, 480, 480, 720, 1080};
        check(w[Logic.chooseSize(w, h, 800, 320)] == 800, "gr\u00f6\u00dfte Vorschau bis 800 Pixel Breite");
        check(w[Logic.chooseSize(w, h, 640, 320)] == 640, "Grenze 640");
        int[] bigW = {1920, 1280};
        int[] bigH = {1080, 720};
        check(bigW[Logic.chooseSize(bigW, bigH, 800, 320)] == 1280, "nur zu gro\u00dfe: die kleinste dar\u00fcber");
        int[] smallW = {176, 240};
        int[] smallH = {144, 160};
        check(smallW[Logic.chooseSize(smallW, smallH, 800, 320)] == 240, "nur zu kleine: die gr\u00f6\u00dfte davon");
        check(Logic.chooseSize(new int[0], new int[0], 800, 320) == -1 && Logic.chooseSize(null, null, 800, 320) == -1
                && Logic.chooseSize(new int[] {1}, new int[] {1, 2}, 800, 320) == -1, "leere/kaputte Liste ergibt -1");
        check(Logic.chooseSize(new int[] {-5, 0, 640}, new int[] {10, 10, 480}, 800, 320) == 2, "ung\u00fcltige Eintr\u00e4ge werden \u00fcbersprungen");
        check(Logic.chooseFrameRate(new int[] {5, 10, 15, 30}, 1000) == 5 && Logic.chooseFrameRate(new int[] {15, 30}, 1000) == 15
                && Logic.chooseFrameRate(new int[] {5, 10}, 200) == 5, "niedrigste ausreichende Bildrate");
        check(Logic.chooseFrameRate(new int[] {5}, 200) == 5 && Logic.chooseFrameRate(new int[] {}, 1000) == -1 && Logic.chooseFrameRate(null, 1000) == -1,
                "Bildrate: zu langsam -> h\u00f6chste vorhandene; keine Angabe -> -1");
        check(Logic.nv21Fits(640 * 480 * 3 / 2, 640, 480) && !Logic.nv21Fits(100, 640, 480) && !Logic.nv21Fits(100, 0, 480), "NV21-Gr\u00f6\u00dfenpr\u00fcfung");
        check(StationLoop.backoffMs(1) == 1000 && StationLoop.backoffMs(2) == 2000 && StationLoop.backoffMs(4) == 8000 && StationLoop.backoffMs(50) == 15000,
                "Wartezeiten bei Verbindungsfehlern 1/2/4/8/15 s");
    }

    // ---- TESTSTAND: absichtlich schlechter Server --------------------------------------------------------------------
    static void hostileServer() throws Exception {
        section("Client gegen absichtlich schlechten Server (TESTSTAND)");
        final AtomicInteger evilHits = new AtomicInteger();
        final List<String> authSeen = new CopyOnWriteArrayList<String>();
        HttpServer evil = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        evil.createContext("/target", new HttpHandler() {
            public void handle(HttpExchange x) throws IOException {
                evilHits.incrementAndGet();
                authSeen.add(String.valueOf(x.getRequestHeaders().getFirst("Authorization")));
                x.sendResponseHeaders(200, -1);
                x.close();
            }
        });
        evil.createContext("/api/mobile/poll", new HttpHandler() {
            public void handle(HttpExchange x) throws IOException {
                x.getResponseHeaders().add("Location", "http://127.0.0.1:" + evil.getAddress().getPort() + "/target");
                x.sendResponseHeaders(302, -1);
                x.close();
            }
        });
        evil.createContext("/api/station/config", new HttpHandler() {
            public void handle(HttpExchange x) throws IOException {
                byte[] b = new byte[Client.MAX_JSON + 5000];
                java.util.Arrays.fill(b, (byte) ' ');
                x.sendResponseHeaders(200, b.length);
                OutputStream o = x.getResponseBody();
                o.write(b);
                o.close();
            }
        });
        evil.createContext("/api/station/frame", new HttpHandler() {
            public void handle(HttpExchange x) throws IOException {
                x.getRequestBody().close();
                byte[] b = "<html>kein JSON</html>".getBytes("UTF-8");
                x.sendResponseHeaders(200, b.length);
                x.getResponseBody().write(b);
                x.close();
            }
        });
        evil.createContext("/api/mute", new HttpHandler() {
            public void handle(HttpExchange x) throws IOException {
                x.getRequestBody().close();
                x.getResponseHeaders().add("Retry-After", "3");
                byte[] b = "{\"detail\":\"Zu viele Anfragen\"}".getBytes("UTF-8");
                x.sendResponseHeaders(429, b.length);
                x.getResponseBody().write(b);
                x.close();
            }
        });
        evil.createContext("/api/unmute", new HttpHandler() {
            public void handle(HttpExchange x) throws IOException {
                x.getRequestBody().close();
                byte[] b = "Internal Server Error".getBytes("UTF-8");
                x.sendResponseHeaders(500, b.length);
                x.getResponseBody().write(b);
                x.close();
            }
        });
        evil.start();
        try {
            Client c = new Client("127.0.0.1:" + evil.getAddress().getPort(), "irgendein-schluessel-1", "T", "");
            ApiException e = expectApi(() -> c.poll(0));
            check(e != null && e.status == 302 && evilHits.get() == 0, "Weiterleitung wird nicht befolgt (Schl\u00fcssel geht nicht an Dritte)");
            e = expectApi(() -> c.config());
            check(e != null && e.isNetwork(), "\u00fcbergro\u00dfe Antwort wird abgebrochen (Speicherschutz)");
            e = expectApi(() -> c.sendFrame(new byte[400]));
            check(e != null && e.status == 502, "200 mit Nicht-JSON: sauberer Fehler statt Absturz");
            e = expectApi(() -> c.mute(5));
            check(e != null && e.status == 429 && e.retryMs == 3000 && e.getMessage().equals("Zu viele Anfragen"), "429: Retry-After und Text \u00fcbernommen");
            e = expectApi(() -> c.unmute());
            check(e != null && e.status == 500 && e.getMessage().equals("HTTP-Fehler 500"), "500 ohne JSON: Standardtext");
            e = expectApi(() -> c.fetchMedia("/api/mobile/poll"));
            check(e != null && e.status == 400, "fetchMedia: Pfad au\u00dferhalb /media/ abgelehnt");
            int bad = 0;
            for (String p : new String[] {"/media/../x", "/media//x", "/media/a?b", "/media/a#b", "/media/a b", "http://evil/media/x", null, "/media\\x"}) {
                ApiException x = expectApi(() -> c.fetchMedia(p));
                if (x != null && x.status == 400) {
                    bad++;
                }
            }
            check(bad == 8, "fetchMedia: 8 \u00fcbelwollende Pfade abgelehnt");
        } finally {
            evil.stop(0);
        }
        Client dead = new Client("127.0.0.1:" + freePort(), "irgendein-schluessel-1", "T", "");
        ApiException e = expectApi(() -> dead.poll(0));
        check(e != null && e.isNetwork() && e.getMessage().contains("Keine Verbindung"), "geschlossener Port: \u201eKeine Verbindung\u201c");
    }

    static int freePort() throws IOException {
        ServerSocket s = new ServerSocket(0);
        int p = s.getLocalPort();
        s.close();
        return p;
    }

    // ---- echter Server -----------------------------------------------------------------------------------------------
    static void realServerCalls() throws Exception {
        section("Echter W\u00e4chter: Aufrufe");
        Client c = new Client(base, token, "Tablet K\u00fcche", "");
        Model.Poll p0 = c.poll(0);
        check(p0.version.length() > 0 && !p0.cameraOnline && "waiting".equals(p0.cameraState), "poll: Version und Kamera wartet auf die erste Station (" + p0.version + ")");
        Client wrong = new Client(base, "falscher-schluessel-9999", "Tablet K\u00fcche", "");
        ApiException e = expectApi(() -> wrong.poll(0));
        check(e != null && e.isAuth() && !e.getMessage().contains("falscher-schluessel"), "falscher Schl\u00fcssel: 401, Schl\u00fcssel steht nicht in der Meldung");
        Model.Config cfg = c.config();
        check(cfg.intervalMs >= 250 && cfg.minIntervalMs == 200 && cfg.width >= 160 && cfg.width <= 960 && cfg.maxBytes == (1 << 20), "config: " + cfg.intervalMs + " ms, "
                + cfg.width + " px, Qualit\u00e4t " + cfg.quality);

        byte[] ok = file("ok.jpg");
        pause(300);
        Model.FrameReply r = c.sendFrame(ok);
        check(r.intervalMs >= 250, "Bild angenommen, Server nennt Takt " + r.intervalMs + " ms");
        Model.Poll p1 = c.poll(0);
        check(p1.cameraOnline && "online".equals(p1.cameraState) && "Tablet Kueche".equals(p1.station), "poll: Kamera online, Station \u201eTablet Kueche\u201c (Umlaut umgeschrieben)");
        e = expectApi(() -> c.sendFrame(ok));
        check(e != null && e.status == 429 && e.retryMs >= 1000, "zweites Bild sofort danach: 429 mit Wartezeit (" + (e == null ? "-" : e.retryMs) + " ms)");
        Client other = new Client(base, token, "Anderes Geraet", "");
        pause(300);
        e = expectApi(() -> other.sendFrame(ok));
        check(e != null && e.status == 409 && e.getMessage().contains("Tablet Kueche"), "zweite Station: 409 und nennt die aktive Station");
        pause(300);
        e = expectApi(() -> c.sendFrame("das ist kein Bild".getBytes("UTF-8")));
        check(e != null && e.status == 400, "zu kleine Datei: 400");
        pause(300);
        byte[] png = file("fake.jpg");
        e = expectApi(() -> c.sendFrame(png));
        check(e != null && e.status == 415, "PNG als JPEG ausgegeben: 415");
        e = expectApi(() -> c.sendFrame(file("wide.jpg")));
        check(e != null && e.status == 413, "Bild mit 4100 Pixeln Breite: 413 (Maße nicht erlaubt)");
        e = expectApi(() -> c.sendFrame(file("big.jpg")));
        check(e != null && e.status == 413, "Bild \u00fcber 1 MiB: 413 (die App sendet es gar nicht erst)");
        pause(300);
        e = expectApi(() -> c.sendFrame(file("truncated.jpg")));
        System.out.println("    (abgeschnittenes JPEG: " + (e == null ? "angenommen" : "abgewiesen mit " + e.status) + ")");
        check(e == null || (e.status >= 400 && e.status < 500), "abgeschnittenes JPEG bringt den W\u00e4chter nicht aus dem Tritt");
        pause(300);
        r = c.sendFrame(ok);
        check(r.intervalMs >= 250, "nach den Fehlern nimmt die Station weiter Bilder an");

        c.mute(5);
        Model.Poll pm = c.poll(0);
        check(pm.muted && pm.muteUntil > System.currentTimeMillis() / 1000.0, "stumm schalten");
        c.unmute();
        check(!c.poll(0).muted, "Stummschaltung aufheben");
        long before = c.poll(0).newestId;
        c.testAlert();
        Model.Poll pt = null;
        for (int i = 0; i < 30 && (pt == null || pt.alerts.isEmpty()); i++) {
            pause(300);
            pt = c.poll(before);
        }
        check(pt != null && !pt.alerts.isEmpty() && "test".equals(pt.alerts.get(0).kind) && pt.newestId > before, "Testalarm kommt in der Abfrage an (kind=test, Nr. " + (pt == null ? "-" : pt.newestId) + ")");
        if (pt != null && !pt.alerts.isEmpty() && pt.alerts.get(0).snapshotUrl.length() > 0) {
            byte[] snap = c.fetchMedia(pt.alerts.get(0).snapshotUrl);
            check(snap.length > 500 && (snap[0] & 255) == 0xFF && (snap[1] & 255) == 0xD8, "Bild der Meldung geladen (" + snap.length + " Bytes, JPEG)");
        } else {
            check(false, "Testalarm hat kein Bild der Station (snapshot_url leer)");
        }
        ApiException nf = expectApi(() -> c.fetchMedia("/media/99999999/snapshot.jpg"));
        check(nf != null && nf.status == 404, "unbekanntes Medium: 404");
        Client badBase = new Client(base + "/nicht-da", token, "x", "");
        ApiException nb = expectApi(() -> badBase.poll(0));
        check(nb != null && nb.status == 404, "falscher Pfad-Vorsatz: 404 statt Absturz");
    }

    // ---- TESTSTAND: Bildquelle und Proxy ------------------------------------------------------------------------------
    static final class FileSource implements StationLoop.Source {
        private final byte[] jpeg;

        FileSource(byte[] jpeg) {
            this.jpeg = jpeg;
        }

        public byte[] next(int quality, int maxBytes, long waitMs) throws InterruptedException {
            Thread.sleep(20);
            return jpeg;
        }
    }

    static final class Rec implements StationLoop.Listener {
        final List<String> states = new CopyOnWriteArrayList<String>();
        volatile long sent;
        volatile int fatal;
        volatile String last = "";

        public void onState(int kind, String text) {
            states.add(kind + ":" + text);
            last = kind + ":" + text;
            if (kind == StationLoop.FATAL) {
                fatal++;
            }
        }

        public void onSent(long total, int bytes) {
            sent = total;
        }

        boolean has(int kind, String part) {
            for (String s : states) {
                if (s.startsWith(kind + ":") && s.contains(part)) {
                    return true;
                }
            }
            return false;
        }
    }

    static final class TcpProxy {
        final int listenPort, targetPort;
        ServerSocket ss;
        final List<Socket> socks = new CopyOnWriteArrayList<Socket>();

        TcpProxy(int listenPort, int targetPort) {
            this.listenPort = listenPort;
            this.targetPort = targetPort;
        }

        void start() throws IOException {
            ss = new ServerSocket();
            ss.setReuseAddress(true);
            ss.bind(new InetSocketAddress("127.0.0.1", listenPort));
            final ServerSocket mine = ss;
            Thread t = new Thread(new Runnable() {
                public void run() {
                    while (!mine.isClosed()) {
                        try {
                            final Socket in = mine.accept();
                            final Socket out = new Socket("127.0.0.1", targetPort);
                            socks.add(in);
                            socks.add(out);
                            pipe(in, out);
                            pipe(out, in);
                        } catch (IOException e) {
                            // Proxy wird beendet oder Ziel nicht erreichbar
                        }
                    }
                }
            });
            t.setDaemon(true);
            t.start();
        }

        void pipe(final Socket from, final Socket to) {
            Thread t = new Thread(new Runnable() {
                public void run() {
                    byte[] buf = new byte[8192];
                    try {
                        InputStream i = from.getInputStream();
                        OutputStream o = to.getOutputStream();
                        int n;
                        while ((n = i.read(buf)) > 0) {
                            o.write(buf, 0, n);
                            o.flush();
                        }
                    } catch (IOException e) {
                        // Verbindung zu
                    } finally {
                        try {
                            from.close();
                            to.close();
                        } catch (IOException e) {
                            // egal
                        }
                    }
                }
            });
            t.setDaemon(true);
            t.start();
        }

        void stop() throws IOException {
            ss.close();
            for (Socket s : socks) {
                try {
                    s.close();
                } catch (IOException e) {
                    // egal
                }
            }
            socks.clear();
        }
    }

    static int portOf(String url) {
        return Integer.parseInt(url.substring(url.lastIndexOf(':') + 1).replaceAll("[^0-9]", ""));
    }

    static void loopsAgainstRealServer() throws Exception {
        section("StationLoop gegen echten W\u00e4chter");
        byte[] ok = file("ok.jpg");
        pause(500);
        Client c = new Client(base, token, "Tablet K\u00fcche", "");
        Rec rec = new Rec();
        StationLoop loop = new StationLoop(c, new FileSource(ok), rec);
        Thread t = new Thread(loop);
        long start = System.currentTimeMillis();
        t.start();
        pause(8000);
        long el = System.currentTimeMillis() - start;
        check(rec.sent >= 6, "Schleife liefert Bilder ab: " + rec.sent + " in " + el / 1000 + " s");
        check(rec.sent * 200L <= el + 400, "h\u00e4lt den Takt ein (h\u00f6chstens 5 Bilder/s): " + String.format("%.1f", rec.sent * 1000.0 / el) + " Bilder/s");
        check(!rec.has(StationLoop.ERROR, "") && !rec.has(StationLoop.FATAL, ""), "keine Fehlerzust\u00e4nde im Normalbetrieb");
        Model.Poll p = c.poll(0);
        check(p.cameraOnline && p.fps > 0, "W\u00e4chter sieht die Station online mit " + p.fps + " Bildern/s");

        // Ausfall: Proxy dazwischen, dann abschalten und wieder einschalten (TESTSTAND)
        loop.stop();
        t.join(5000);
        check(!t.isAlive(), "Schleife l\u00e4sst sich sauber beenden");
        int pp = freePort();
        TcpProxy proxy = new TcpProxy(pp, portOf(base));
        proxy.start();
        Client viaProxy = new Client("127.0.0.1:" + pp, token, "Tablet K\u00fcche", "");
        Rec r2 = new Rec();
        StationLoop l2 = new StationLoop(viaProxy, new FileSource(ok), r2);
        Thread t2 = new Thread(l2);
        t2.start();
        pause(3000);
        long s1 = r2.sent;
        check(s1 >= 2, "\u00fcber den Proxy kommen Bilder an (" + s1 + ")");
        proxy.stop();
        long down = System.currentTimeMillis();
        pause(7000);
        check(r2.has(StationLoop.ERROR, "Keine Verbindung") || r2.has(StationLoop.ERROR, "Netzwerkfehler"), "Ausfall wird als Fehler gemeldet, nicht als Absturz");
        check(r2.sent <= s1 + 1, "w\u00e4hrend des Ausfalls werden keine Bilder gez\u00e4hlt");
        check(t2.isAlive() && r2.fatal == 0, "Schleife gibt bei Ausfall nicht auf");
        proxy.start();
        long up = System.currentTimeMillis();
        long deadline = up + 30000;
        while (System.currentTimeMillis() < deadline && r2.sent <= s1 + 1) {
            pause(250);
        }
        check(r2.sent > s1 + 1, "nach Wiederkehr geht es von selbst weiter (nach " + (System.currentTimeMillis() - up) / 1000.0 + " s, Ausfall dauerte " + (up - down) / 1000 + " s)");
        check("0:Sendet Bilder an den W\u00e4chter".equals(r2.last) || r2.last.startsWith("0:"), "Zustand wieder \u201eOK\u201c");
        l2.stop();
        t2.join(5000);
        proxy.stop();

        // falscher Schlüssel
        Client wrong = new Client(base, "falscher-schluessel-9999", "Tablet K\u00fcche", "");
        Rec r3 = new Rec();
        StationLoop l3 = new StationLoop(wrong, new FileSource(ok), r3);
        Thread t3 = new Thread(l3);
        t3.start();
        t3.join(10000);
        check(!t3.isAlive() && r3.fatal == 1 && r3.sent == 0, "falscher Schl\u00fcssel: Schleife endet mit Meldung, sendet nichts");
    }

    static void pollLoopAgainstRealServer() throws Exception {
        section("PollLoop gegen echten W\u00e4chter");
        Client c = new Client(base, token, "Tablet K\u00fcche", "");
        final List<Model.Poll> polls = new CopyOnWriteArrayList<Model.Poll>();
        final List<Model.Alert> alerts = new CopyOnWriteArrayList<Model.Alert>();
        final List<String> errors = new CopyOnWriteArrayList<String>();
        PollLoop loop = new PollLoop(c, new PollLoop.Listener() {
            public void onPoll(Model.Poll p, List<Model.Alert> fresh) {
                polls.add(p);
                alerts.addAll(fresh);
            }

            public void onError(int failures, String text, boolean fatal) {
                errors.add(text);
            }
        }, 1000);
        Thread t = new Thread(loop);
        t.start();
        pause(2500);
        check(polls.size() >= 2 && alerts.isEmpty() && errors.isEmpty(), "Start: Abfragen laufen, vorhandene Alarme l\u00f6sen keinen neuen aus (" + polls.size() + " Abfragen)");
        c.testAlert();
        long end = System.currentTimeMillis() + 10000;
        while (System.currentTimeMillis() < end && alerts.isEmpty()) {
            pause(200);
        }
        pause(2500);
        check(alerts.size() == 1 && "test".equals(alerts.get(0).kind), "Testalarm wird genau einmal gemeldet (" + alerts.size() + ")");
        int n = polls.size();
        c.mute(5);
        loop.pollNow();
        pause(700);
        check(polls.size() > n && polls.get(polls.size() - 1).muted, "pollNow fragt sofort ab und sieht \u201estumm\u201c");
        c.unmute();
        loop.stop();
        t.join(5000);
        check(!t.isAlive(), "Abfrageschleife l\u00e4sst sich beenden");

        Client wrong = new Client(base, "falscher-schluessel-9999", "x", "");
        final List<Boolean> fatals = new CopyOnWriteArrayList<Boolean>();
        PollLoop l2 = new PollLoop(wrong, new PollLoop.Listener() {
            public void onPoll(Model.Poll p, List<Model.Alert> fresh) {
            }

            public void onError(int failures, String text, boolean fatal) {
                fatals.add(Boolean.valueOf(fatal));
            }
        }, 1000);
        Thread t2 = new Thread(l2);
        t2.start();
        t2.join(8000);
        check(!t2.isAlive() && fatals.size() == 1 && fatals.get(0).booleanValue(), "falscher Schl\u00fcssel: Abfrage endet nach einem Versuch");
    }

    static void httpsPinning() throws Exception {
        section("HTTPS mit Fingerabdruck (selbst erzeugtes Zertifikat)");
        Client good = new Client(httpsBase, token, "Tablet K\u00fcche", pinGood);
        Model.Poll p = good.poll(0);
        check(p.version.length() > 0, "richtiger Fingerabdruck: Verbindung steht (TLS, selbstsigniertes Zertifikat)");
        Client lower = new Client(httpsBase, token, "Tablet K\u00fcche", pinGood.replace(":", "").toLowerCase());
        check(lower.poll(0).version.length() > 0, "Fingerabdruck in Kleinbuchstaben ohne Doppelpunkte funktioniert gleich");
        String bad = "00" + pinGood.substring(2);
        if (bad.equals(pinGood)) {
            bad = "FF" + pinGood.substring(2);
        }
        final Client wrongPin = new Client(httpsBase, token, "Tablet K\u00fcche", bad);
        ApiException e = expectApi(() -> wrongPin.poll(0));
        check(e != null && e.isNetwork() && e.getMessage().contains("Fingerabdruck") && e.getMessage().toUpperCase().contains(pinGood.toUpperCase()),
                "falscher Fingerabdruck: abgelehnt, Meldung nennt den echten (zum Abgleichen)");
        final Client noPin = new Client(httpsBase, token, "Tablet K\u00fcche", "");
        e = expectApi(() -> noPin.poll(0));
        check(e != null && e.isNetwork(), "ohne Fingerabdruck wird das selbstsignierte Zertifikat nicht akzeptiert");
        check(e != null && !e.getMessage().contains(token), "Fehlermeldung enth\u00e4lt den Schl\u00fcssel nicht");
        final Client plain = new Client("http://" + httpsBase.substring("https://".length()), token, "x", "");
        e = expectApi(() -> plain.poll(0));
        check(e != null, "http auf einen https-Port: Fehler statt H\u00e4ngen/Absturz");
        // Bilder per HTTPS
        pause(300);
        Model.FrameReply r = good.sendFrame(file("ok.jpg"));
        check(r.intervalMs >= 250, "Bild per HTTPS abgeliefert");
    }

    static void takeover() throws Exception {
        section("Stationswechsel (dauert ~20 s: alte Station muss erst schweigen)");
        byte[] ok = file("ok.jpg");
        Client a = new Client(base, token, "Tablet K\u00fcche", "");
        pause(500);
        try {
            a.sendFrame(ok);
        } catch (ApiException e) {
            // schon zu schnell: egal, die Station ist ohnehin aktiv
        }
        Client b = new Client(base, token, "Zweites Geraet", "");
        Rec rec = new Rec();
        StationLoop loop = new StationLoop(b, new FileSource(ok), rec);
        Thread t = new Thread(loop);
        long start = System.currentTimeMillis();
        t.start();
        pause(3000);
        check(rec.has(StationLoop.WAIT, "Tablet Kueche") && rec.sent == 0, "zweite Station wartet und meldet, wer aktiv ist");
        long end = start + 40000;
        while (System.currentTimeMillis() < end && rec.sent == 0) {
            pause(500);
        }
        check(rec.sent > 0, "nach Schweigen der ersten \u00fcbernimmt die zweite (nach " + (System.currentTimeMillis() - start) / 1000.0 + " s)");
        check(c(a).poll(0).station.equals("Zweites Geraet"), "W\u00e4chter zeigt nun \u201eZweites Geraet\u201c");
        loop.stop();
        t.join(5000);
    }

    static Client c(Client x) {
        return x;
    }
}
