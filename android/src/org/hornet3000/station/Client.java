package org.hornet3000.station;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.MalformedURLException;
import java.net.URL;
import java.security.MessageDigest;
import java.security.cert.CertificateException;
import java.security.cert.X509Certificate;
import java.util.Locale;
import java.util.Map;

import javax.net.ssl.HostnameVerifier;
import javax.net.ssl.HttpsURLConnection;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLSession;
import javax.net.ssl.SSLSocketFactory;
import javax.net.ssl.TrustManager;
import javax.net.ssl.X509TrustManager;

/**
 * Sprechstelle zum Hornet3000-Wächter (reines Java, keine Android-Klassen → läuft ab Android 2.2 und wird in der
 * JVM gegen den echten Server geprüft).
 *
 * Anmeldung: "Authorization: Bearer &lt;Zugangsschlüssel&gt;" bei jedem Aufruf (kein Cookie nötig).
 * Sicherheit: keine Weiterleitungen (der Schlüssel wandert nie zu einem anderen Rechner); nur http/https;
 * Antworten sind in der Größe begrenzt; der Schlüssel steht in keiner Fehlermeldung; Schlüssel und Stationsname werden vor
 * dem Senden auf erlaubte Zeichen geprüft (kein Einschleusen von Kopfzeilen).
 * HTTPS: Ist ein SHA-256-Fingerabdruck des Server-Zertifikats eingetragen, wird GENAU dieses Zertifikat verlangt (auch ein
 * selbst erzeugtes; Name und Ablaufdatum zählen dann nicht – die Uhr alter Geräte geht oft falsch). Ohne Fingerabdruck
 * gilt die normale Prüfung des Geräts.
 */
public final class Client {
    public static final int CONNECT_MS = 8000;
    public static final int READ_MS = 15000;
    public static final int MAX_JSON = 256 * 1024;
    public static final int MAX_IMAGE = 4 * 1024 * 1024;
    public static final int MAX_FRAME = 1 << 20;

    private final String base;
    private final String token;
    private final String stationHeader;
    private final byte[] pin;                       // null = keine Festlegung
    private final SSLSocketFactory tlsFactory;      // null bei http
    private final HostnameVerifier verifier;        // null = Standard

    public Client(String baseUrl, String token, String station, String pinSha256) {
        this.base = normalizeBase(baseUrl);
        this.token = checkToken(token);
        this.stationHeader = headerStation(station);
        this.pin = parsePin(pinSha256);
        if (this.base.startsWith("https://")) {
            SSLSocketFactory f;
            HostnameVerifier hv = null;
            try {
                if (pin != null) {
                    SSLContext ctx = SSLContext.getInstance("TLS");
                    ctx.init(null, new TrustManager[] {new PinTrust(pin)}, null);
                    f = ctx.getSocketFactory();
                    hv = new HostnameVerifier() {
                        public boolean verify(String host, SSLSession session) {
                            return true;                   // der Fingerabdruck ersetzt die Namensprüfung
                        }
                    };
                } else {
                    f = (SSLSocketFactory) SSLSocketFactory.getDefault();
                }
            } catch (Exception e) {
                throw new IllegalArgumentException("HTTPS kann auf diesem Gerät nicht eingerichtet werden: " + e.getMessage());
            }
            this.tlsFactory = new TlsFactory(f);
            this.verifier = hv;
        } else {
            this.tlsFactory = null;
            this.verifier = null;
        }
    }

    public String base() {
        return base;
    }

    @Override
    public String toString() {
        return "Client(" + base + ")";                  // bewusst ohne Schlüssel
    }

    // ---- Eingaben prüfen ---------------------------------------------------------------------------------------
    /** „192.168.1.20:8000“ → „http://192.168.1.20:8000“; nur http/https, ohne Zugangsdaten, Frage- oder Rautenteil. */
    public static String normalizeBase(String in) {
        String t = in == null ? "" : in.trim();
        if (t.length() == 0) {
            throw new IllegalArgumentException("Bitte die Adresse des Wächters eintragen (z. B. 192.168.1.20:8000)");
        }
        if (t.length() > 200) {
            throw new IllegalArgumentException("Adresse zu lang");
        }
        String low = t.toLowerCase(Locale.ENGLISH);
        if (!(low.startsWith("http://") || low.startsWith("https://"))) {
            if (low.indexOf("://") >= 0) {
                throw new IllegalArgumentException("Nur http:// oder https:// ist erlaubt");
            }
            t = "http://" + t;
        }
        URL u;
        try {
            u = new URL(t);
        } catch (MalformedURLException e) {
            throw new IllegalArgumentException("Adresse nicht lesbar");
        }
        if (u.getHost() == null || u.getHost().length() == 0) {
            throw new IllegalArgumentException("Adresse ohne Rechnername");
        }
        if (u.getUserInfo() != null || u.getQuery() != null || u.getRef() != null) {
            throw new IllegalArgumentException("Adresse darf kein Passwort, kein ? und kein # enthalten");
        }
        String path = u.getPath() == null ? "" : u.getPath();
        while (path.endsWith("/")) {
            path = path.substring(0, path.length() - 1);
        }
        if (path.indexOf("..") >= 0 || path.indexOf('\\') >= 0 || path.indexOf(' ') >= 0) {
            throw new IllegalArgumentException("Adresse nicht lesbar");
        }
        return u.getProtocol() + "://" + u.getHost() + (u.getPort() >= 0 ? ":" + u.getPort() : "") + path;
    }

    static String checkToken(String t) {
        String s = t == null ? "" : t.trim();
        if (s.length() < 8 || s.length() > 256) {
            throw new IllegalArgumentException("Der Zugangsschlüssel ist zu kurz oder zu lang (8 bis 256 Zeichen)");
        }
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            boolean ok = (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || "-_.~+/=".indexOf(c) >= 0;
            if (!ok) {
                throw new IllegalArgumentException("Der Zugangsschlüssel enthält ein unerlaubtes Zeichen");
            }
        }
        return s;
    }

    /** Nur ASCII im Kopfzeilenwert (Umlaute werden umgeschrieben), höchstens 40 Zeichen, sonst „Station“. */
    public static String headerStation(String name) {
        String n = name == null ? "" : name.trim();
        StringBuilder b = new StringBuilder();
        for (int i = 0; i < n.length(); i++) {
            char c = n.charAt(i);
            if (c == 'ä') {
                b.append("ae");
            } else if (c == 'ö') {
                b.append("oe");
            } else if (c == 'ü') {
                b.append("ue");
            } else if (c == 'Ä') {
                b.append("Ae");
            } else if (c == 'Ö') {
                b.append("Oe");
            } else if (c == 'Ü') {
                b.append("Ue");
            } else if (c == 'ß') {
                b.append("ss");
            } else if ((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '.' || c == '_'
                    || c == ' ' || c == '-') {
                b.append(c);
            }
        }
        String r = b.toString().trim();
        if (r.length() > 40) {
            r = r.substring(0, 40).trim();
        }
        return r.length() == 0 ? "Station" : r;
    }

    /** Fingerabdruck als 64 Hexziffern (Doppelpunkte/Leerzeichen erlaubt); leer = keiner. */
    public static byte[] parsePin(String s) {
        String t = s == null ? "" : s.trim();
        if (t.length() == 0) {
            return null;
        }
        StringBuilder h = new StringBuilder();
        for (int i = 0; i < t.length(); i++) {
            char c = t.charAt(i);
            if (c == ':' || c == ' ' || c == '-') {
                continue;
            }
            if (Character.digit(c, 16) < 0 || c > 127) {
                throw new IllegalArgumentException("Fingerabdruck: nur Hexziffern 0-9, A-F (und Doppelpunkte)");
            }
            h.append(c);
        }
        if (h.length() != 64) {
            throw new IllegalArgumentException("Fingerabdruck: SHA-256 hat 64 Hexziffern (hier " + h.length() + ")");
        }
        byte[] out = new byte[32];
        for (int i = 0; i < 32; i++) {
            out[i] = (byte) ((Character.digit(h.charAt(2 * i), 16) << 4) | Character.digit(h.charAt(2 * i + 1), 16));
        }
        return out;
    }

    // ---- Aufrufe ------------------------------------------------------------------------------------------------
    public Model.Config config() throws ApiException {
        Reply r = call("GET", "/api/station/config", null, null, MAX_JSON);
        return Model.Config.from(Json.obj(r.json()));
    }

    /** Ein JPEG als Bild der Station abliefern. */
    public Model.FrameReply sendFrame(byte[] jpeg) throws ApiException {
        if (jpeg == null || jpeg.length == 0) {
            throw new ApiException(400, "Leeres Bild", 0);
        }
        if (jpeg.length > MAX_FRAME) {          // der Wächter bricht die Verbindung mitten im Senden ab – gar nicht erst versuchen
            throw new ApiException(413, "Bild ist gr\u00f6\u00dfer als 1 MiB (" + (jpeg.length / 1024) + " KB)", 0);
        }
        Reply r = call("POST", "/api/station/frame", "image/jpeg", jpeg, MAX_JSON);
        Model.FrameReply f = new Model.FrameReply();
        long iv = Json.lng(Json.obj(r.json()), "interval_ms", 1000);
        f.intervalMs = (int) Math.max(200, Math.min(60000, iv));
        return f;
    }

    public Model.Poll poll(long since) throws ApiException {
        Reply r = call("GET", "/api/mobile/poll?since=" + Math.max(0, since), null, null, MAX_JSON);
        return Model.Poll.from(Json.obj(r.json()));
    }

    /** Alarm für die angegebene Zeit stummschalten (1 bis 10080 Minuten). */
    public void mute(int minutes) throws ApiException {
        int m = Math.max(1, Math.min(10080, minutes));
        byte[] body = utf8Bytes("{\"minutes\":" + m + "}");
        call("POST", "/api/mute", "application/json", body, MAX_JSON);
    }

    public void unmute() throws ApiException {
        call("POST", "/api/unmute", "application/json", utf8Bytes("{}"), MAX_JSON);
    }

    public void testAlert() throws ApiException {
        call("POST", "/api/test-alert", "application/json", utf8Bytes("{}"), MAX_JSON);
    }

    /** Bild einer Meldung (nur Pfade unter /media/ – der Pfad kommt vom Server und wird nicht blind verwendet). */
    public byte[] fetchMedia(String path) throws ApiException {
        if (path == null || !path.startsWith("/media/") || path.length() > 200 || path.indexOf("..") >= 0
                || path.indexOf("//") >= 0 || path.indexOf('\\') >= 0 || path.indexOf('?') >= 0 || path.indexOf('#') >= 0
                || path.indexOf(' ') >= 0) {
            throw new ApiException(400, "Ungültiger Medienpfad", 0);
        }
        return call("GET", path, null, null, MAX_IMAGE).body;
    }

    private static byte[] utf8Bytes(String s) {
        try {
            return s.getBytes("UTF-8");
        } catch (java.io.UnsupportedEncodingException e) {
            throw new IllegalStateException("UTF-8 fehlt");          // gibt es auf jedem Android
        }
    }

    // ---- HTTP -------------------------------------------------------------------------------------------------------
    private static final class Reply {
        final int status;
        final byte[] body;

        Reply(int status, byte[] body) {
            this.status = status;
            this.body = body;
        }

        Object json() throws ApiException {
            try {
                return Json.parse(new String(body, "UTF-8"));
            } catch (Exception e) {
                throw new ApiException(502, "Antwort des Wächters nicht lesbar", 0);
            }
        }
    }

    private Reply call(String method, String path, String ctype, byte[] body, int maxReply) throws ApiException {
        HttpURLConnection c = null;
        try {
            URL u = new URL(base + path);
            c = (HttpURLConnection) u.openConnection();
            if (c instanceof HttpsURLConnection && tlsFactory != null) {
                HttpsURLConnection sc = (HttpsURLConnection) c;
                sc.setSSLSocketFactory(tlsFactory);
                if (verifier != null) {
                    sc.setHostnameVerifier(verifier);
                }
            }
            c.setRequestMethod(method);
            c.setConnectTimeout(CONNECT_MS);
            c.setReadTimeout(READ_MS);
            c.setInstanceFollowRedirects(false);
            c.setUseCaches(false);
            c.setRequestProperty("Authorization", "Bearer " + token);
            c.setRequestProperty("Accept", ctype == null && path.startsWith("/media/") ? "image/*" : "application/json");
            c.setRequestProperty("X-Station", stationHeader);
            c.setRequestProperty("User-Agent", "Hornet3000-Station");
            if (body != null) {
                c.setDoOutput(true);
                c.setRequestProperty("Content-Type", ctype);
                c.setFixedLengthStreamingMode(body.length);
                OutputStream o = c.getOutputStream();
                try {
                    o.write(body);
                    o.flush();
                } finally {
                    o.close();
                }
            }
            int st = c.getResponseCode();
            InputStream in = st >= 400 ? c.getErrorStream() : c.getInputStream();
            byte[] data = in == null ? new byte[0] : readCapped(in, st >= 400 ? MAX_JSON : maxReply);
            if (st >= 300 && st < 400) {
                throw new ApiException(st, "Weiterleitung abgelehnt – bitte die genaue Adresse (http/https) eintragen", 0);
            }
            if (st >= 400) {
                throw new ApiException(st, detailOf(data, st), retryAfterMs(c));
            }
            return new Reply(st, data);
        } catch (ApiException e) {
            throw e;
        } catch (IOException e) {
            throw new ApiException(0, netText(e), 0);
        } catch (RuntimeException e) {
            throw new ApiException(0, "Verbindungsfehler (" + e.getClass().getSimpleName() + ")", 0);
        } finally {
            if (c != null) {
                c.disconnect();
            }
        }
    }

    private static String netText(IOException e) {
        String n = e.getClass().getSimpleName();
        String m = e.getMessage() == null ? "" : e.getMessage();
        if (m.indexOf("Fingerabdruck") >= 0) {
            return m;
        }
        if (e instanceof javax.net.ssl.SSLException) {
            Throwable t = e;
            for (int i = 0; i < 6 && t != null; i++, t = t.getCause()) {
                if (t.getMessage() != null && t.getMessage().indexOf("Fingerabdruck") >= 0) {
                    return t.getMessage();
                }
            }
            return "Sichere Verbindung fehlgeschlagen (" + n + ") – Fingerabdruck des Zertifikats prüfen";
        }
        if (e instanceof java.net.SocketTimeoutException) {
            return "Zeitüberschreitung – Wächter antwortet nicht";
        }
        if (e instanceof java.net.UnknownHostException) {
            return "Rechner nicht gefunden – Adresse prüfen";
        }
        if (e instanceof java.net.ConnectException) {
            return "Keine Verbindung – läuft der Wächter, stimmt Adresse und Port?";
        }
        return "Netzwerkfehler (" + n + ")";
    }

    private static int retryAfterMs(HttpURLConnection c) {
        String h = c.getHeaderField("Retry-After");
        if (h == null) {
            return 0;
        }
        try {
            long s = Long.parseLong(h.trim());
            return (int) Math.max(0, Math.min(120, s)) * 1000;
        } catch (NumberFormatException e) {
            return 0;
        }
    }

    private static String detailOf(byte[] data, int status) {
        try {
            Object j = Json.parse(new String(data, "UTF-8"));
            Map<String, Object> m = Json.obj(j);
            Object d = m.get("detail");
            if (d instanceof String && ((String) d).length() > 0) {
                String s = (String) d;
                return s.length() > 300 ? s.substring(0, 300) : s;
            }
        } catch (Exception e) {
            // keine JSON-Antwort: unten Standardtext
        }
        return "HTTP-Fehler " + status;
    }

    private static byte[] readCapped(InputStream in, int max) throws IOException {
        try {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buf = new byte[8192];
            int n, total = 0;
            while ((n = in.read(buf)) > 0) {
                total += n;
                if (total > max) {
                    throw new IOException("Antwort zu groß");
                }
                out.write(buf, 0, n);
            }
            return out.toByteArray();
        } finally {
            in.close();
        }
    }

    // ---- TLS ----------------------------------------------------------------------------------------------------------
    static String hex(byte[] b) {
        StringBuilder s = new StringBuilder();
        for (int i = 0; i < b.length; i++) {
            if (i > 0) {
                s.append(':');
            }
            s.append("0123456789ABCDEF".charAt((b[i] >> 4) & 15)).append("0123456789ABCDEF".charAt(b[i] & 15));
        }
        return s.toString();
    }

    /** Vertraut genau einem Zertifikat (SHA-256 des DER-Inhalts). */
    static final class PinTrust implements X509TrustManager {
        private final byte[] pin;

        PinTrust(byte[] pin) {
            this.pin = pin.clone();
        }

        public void checkClientTrusted(X509Certificate[] chain, String authType) throws CertificateException {
            throw new CertificateException("Client-Zertifikate werden nicht angenommen");
        }

        public void checkServerTrusted(X509Certificate[] chain, String authType) throws CertificateException {
            if (chain == null || chain.length == 0) {
                throw new CertificateException("Kein Zertifikat vom Server");
            }
            byte[] got;
            try {
                got = MessageDigest.getInstance("SHA-256").digest(chain[0].getEncoded());
            } catch (Exception e) {
                throw new CertificateException("Fingerabdruck nicht berechenbar");
            }
            if (!MessageDigest.isEqual(got, pin)) {
                throw new CertificateException("Das Zertifikat passt nicht zum eingetragenen Fingerabdruck (Server hat: "
                        + hex(got) + ")");
            }
        }

        public X509Certificate[] getAcceptedIssuers() {
            return new X509Certificate[0];
        }
    }
}
