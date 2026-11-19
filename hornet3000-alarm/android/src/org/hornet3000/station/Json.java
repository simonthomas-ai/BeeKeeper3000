// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
package org.hornet3000.station;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Kleiner, strenger JSON-Leser ohne Abhängigkeiten (org.json gibt es auf dem Test-Rechner nicht, und so läuft derselbe
 * Code auf jedem Android ab 2.2 und in der JVM-Prüfung). Ergebnis: Map (HashMap), List (ArrayList), String, Double,
 * Boolean oder null. Grenzen: 512 K Zeichen, Schachtelungstiefe 32 – gegen übergroße oder bösartige Antworten.
 */
public final class Json {
    public static final int MAX_CHARS = 512 * 1024;
    public static final int MAX_DEPTH = 32;

    private final String s;
    private int i;

    private Json(String s) {
        this.s = s;
    }

    public static Object parse(String text) {
        if (text == null) {
            throw new IllegalArgumentException("JSON: kein Text");
        }
        if (text.length() > MAX_CHARS) {
            throw new IllegalArgumentException("JSON: zu groß");
        }
        Json p = new Json(text);
        p.ws();
        Object v = p.value(0);
        p.ws();
        if (p.i != p.s.length()) {
            throw p.err("Text nach dem Wert");
        }
        return v;
    }

    // ---- Zugriffshilfen (tolerant: falscher Typ oder fehlender Schlüssel ergibt den Vorgabewert) ----------------
    @SuppressWarnings("unchecked")
    public static Map<String, Object> obj(Object o) {
        return o instanceof Map ? (Map<String, Object>) o : new HashMap<String, Object>();
    }

    @SuppressWarnings("unchecked")
    public static List<Object> list(Object o) {
        return o instanceof List ? (List<Object>) o : new ArrayList<Object>();
    }

    public static String str(Map<String, Object> m, String key, String def) {
        Object v = m.get(key);
        return v instanceof String ? (String) v : def;
    }

    public static double num(Map<String, Object> m, String key, double def) {
        Object v = m.get(key);
        return v instanceof Double ? ((Double) v).doubleValue() : def;
    }

    public static long lng(Map<String, Object> m, String key, long def) {
        Object v = m.get(key);
        if (!(v instanceof Double)) {
            return def;
        }
        double d = ((Double) v).doubleValue();
        if (Double.isNaN(d) || Double.isInfinite(d)) {
            return def;
        }
        return (long) d;
    }

    public static boolean bool(Map<String, Object> m, String key, boolean def) {
        Object v = m.get(key);
        return v instanceof Boolean ? ((Boolean) v).booleanValue() : def;
    }

    // ---- Leser ---------------------------------------------------------------------------------------------------
    private IllegalArgumentException err(String what) {
        return new IllegalArgumentException("JSON: " + what + " (Position " + i + ")");
    }

    private void ws() {
        while (i < s.length()) {
            char c = s.charAt(i);
            if (c == ' ' || c == '\t' || c == '\n' || c == '\r') {
                i++;
            } else {
                break;
            }
        }
    }

    private Object value(int depth) {
        if (depth > MAX_DEPTH) {
            throw err("zu tief verschachtelt");
        }
        if (i >= s.length()) {
            throw err("unerwartetes Ende");
        }
        char c = s.charAt(i);
        if (c == '{') {
            return object(depth);
        }
        if (c == '[') {
            return array(depth);
        }
        if (c == '"') {
            return string();
        }
        if (c == 't') {
            word("true");
            return Boolean.TRUE;
        }
        if (c == 'f') {
            word("false");
            return Boolean.FALSE;
        }
        if (c == 'n') {
            word("null");
            return null;
        }
        if (c == '-' || (c >= '0' && c <= '9')) {
            return number();
        }
        throw err("unerwartetes Zeichen");
    }

    private void word(String w) {
        if (!s.startsWith(w, i)) {
            throw err("ungültiges Wort");
        }
        i += w.length();
    }

    private Map<String, Object> object(int depth) {
        Map<String, Object> m = new HashMap<String, Object>();
        i++;
        ws();
        if (i < s.length() && s.charAt(i) == '}') {
            i++;
            return m;
        }
        for (;;) {
            ws();
            if (i >= s.length() || s.charAt(i) != '"') {
                throw err("Schlüssel erwartet");
            }
            String k = string();
            ws();
            if (i >= s.length() || s.charAt(i) != ':') {
                throw err("':' erwartet");
            }
            i++;
            ws();
            m.put(k, value(depth + 1));
            ws();
            if (i >= s.length()) {
                throw err("unerwartetes Ende");
            }
            char c = s.charAt(i++);
            if (c == '}') {
                return m;
            }
            if (c != ',') {
                throw err("',' oder '}' erwartet");
            }
        }
    }

    private List<Object> array(int depth) {
        List<Object> l = new ArrayList<Object>();
        i++;
        ws();
        if (i < s.length() && s.charAt(i) == ']') {
            i++;
            return l;
        }
        for (;;) {
            ws();
            l.add(value(depth + 1));
            ws();
            if (i >= s.length()) {
                throw err("unerwartetes Ende");
            }
            char c = s.charAt(i++);
            if (c == ']') {
                return l;
            }
            if (c != ',') {
                throw err("',' oder ']' erwartet");
            }
        }
    }

    private String string() {
        StringBuilder b = new StringBuilder();
        i++;                                        // öffnendes "
        for (;;) {
            if (i >= s.length()) {
                throw err("Text nicht beendet");
            }
            char c = s.charAt(i++);
            if (c == '"') {
                return b.toString();
            }
            if (c < 0x20) {
                throw err("Steuerzeichen im Text");
            }
            if (c != '\\') {
                b.append(c);
                continue;
            }
            if (i >= s.length()) {
                throw err("Text nicht beendet");
            }
            char e = s.charAt(i++);
            switch (e) {
                case '"': b.append('"'); break;
                case '\\': b.append('\\'); break;
                case '/': b.append('/'); break;
                case 'b': b.append('\b'); break;
                case 'f': b.append('\f'); break;
                case 'n': b.append('\n'); break;
                case 'r': b.append('\r'); break;
                case 't': b.append('\t'); break;
                case 'u':
                    if (i + 4 > s.length()) {
                        throw err("\\u-Folge unvollständig");
                    }
                    int v = 0;
                    for (int k = 0; k < 4; k++) {
                        int d = Character.digit(s.charAt(i + k), 16);
                        if (d < 0) {
                            throw err("\\u-Folge ungültig");
                        }
                        v = (v << 4) | d;
                    }
                    i += 4;
                    b.append((char) v);
                    break;
                default:
                    throw err("ungültige Escape-Folge");
            }
        }
    }

    private Double number() {
        int st = i;
        if (s.charAt(i) == '-') {
            i++;
        }
        if (i >= s.length()) {
            throw err("Zahl unvollständig");
        }
        if (s.charAt(i) == '0') {
            i++;
        } else if (s.charAt(i) >= '1' && s.charAt(i) <= '9') {
            while (i < s.length() && Character.isDigit(s.charAt(i)) && s.charAt(i) < 128) {
                i++;
            }
        } else {
            throw err("Zahl ungültig");
        }
        if (i < s.length() && s.charAt(i) == '.') {
            i++;
            int d0 = i;
            while (i < s.length() && s.charAt(i) >= '0' && s.charAt(i) <= '9') {
                i++;
            }
            if (i == d0) {
                throw err("Zahl ungültig");
            }
        }
        if (i < s.length() && (s.charAt(i) == 'e' || s.charAt(i) == 'E')) {
            i++;
            if (i < s.length() && (s.charAt(i) == '+' || s.charAt(i) == '-')) {
                i++;
            }
            int d0 = i;
            while (i < s.length() && s.charAt(i) >= '0' && s.charAt(i) <= '9') {
                i++;
            }
            if (i == d0) {
                throw err("Zahl ungültig");
            }
        }
        try {
            return Double.valueOf(s.substring(st, i));
        } catch (NumberFormatException e) {
            throw err("Zahl ungültig");
        }
    }
}
