package org.hornet3000.station;

/** Fehler bei einem Aufruf des Wächters. status 0 = keine Verbindung / Netzwerkfehler, sonst der HTTP-Status. */
public final class ApiException extends Exception {
    private static final long serialVersionUID = 1L;

    public final int status;
    /** Vom Server empfohlene Wartezeit (Retry-After), sonst 0. */
    public final int retryMs;

    public ApiException(int status, String detail, int retryMs) {
        super(detail);
        this.status = status;
        this.retryMs = retryMs;
    }

    public boolean isNetwork() {
        return status == 0;
    }

    /** Schlüssel abgelehnt – erneutes Probieren ohne neuen Schlüssel ist sinnlos (und der Server sperrt bei Häufung). */
    public boolean isAuth() {
        return status == 401 || status == 403;
    }
}
