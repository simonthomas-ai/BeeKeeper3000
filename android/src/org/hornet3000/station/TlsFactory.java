// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
package org.hornet3000.station;

import java.io.IOException;
import java.net.InetAddress;
import java.net.Socket;
import java.util.ArrayList;
import java.util.List;

import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;

/**
 * Packt eine SSLSocketFactory ein und schaltet TLS 1.2/1.1/1.0 ausdrücklich ein. Nötig für Android 4.1–4.4: Dort kann das
 * Gerät TLS 1.2, benutzt es aber nur, wenn man es für den Socket anschaltet. Ab Android 5 ist es ohnehin Standard.
 * (Android 2.2–4.0 kann nur TLS 1.0 – dort funktioniert ein moderner HTTPS-Server nicht; im lokalen Netz bleibt dann http.)
 */
final class TlsFactory extends SSLSocketFactory {
    private final SSLSocketFactory f;

    TlsFactory(SSLSocketFactory f) {
        this.f = f;
    }

    private Socket tune(Socket s) {
        if (s instanceof SSLSocket) {
            SSLSocket ss = (SSLSocket) s;
            String[] sup = ss.getSupportedProtocols();
            List<String> on = new ArrayList<String>();
            String[] want = {"TLSv1.3", "TLSv1.2", "TLSv1.1", "TLSv1"};
            for (int i = 0; i < want.length; i++) {
                for (int k = 0; k < sup.length; k++) {
                    if (want[i].equals(sup[k])) {
                        on.add(want[i]);
                    }
                }
            }
            if (!on.isEmpty()) {
                ss.setEnabledProtocols(on.toArray(new String[on.size()]));
            }
        }
        return s;
    }

    @Override
    public String[] getDefaultCipherSuites() {
        return f.getDefaultCipherSuites();
    }

    @Override
    public String[] getSupportedCipherSuites() {
        return f.getSupportedCipherSuites();
    }

    @Override
    public Socket createSocket(Socket s, String host, int port, boolean autoClose) throws IOException {
        return tune(f.createSocket(s, host, port, autoClose));
    }

    @Override
    public Socket createSocket(String host, int port) throws IOException {
        return tune(f.createSocket(host, port));
    }

    @Override
    public Socket createSocket(String host, int port, InetAddress la, int lp) throws IOException {
        return tune(f.createSocket(host, port, la, lp));
    }

    @Override
    public Socket createSocket(InetAddress host, int port) throws IOException {
        return tune(f.createSocket(host, port));
    }

    @Override
    public Socket createSocket(InetAddress a, int port, InetAddress la, int lp) throws IOException {
        return tune(f.createSocket(a, port, la, lp));
    }
}
