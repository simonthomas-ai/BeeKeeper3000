package org.hornet3000.station;

import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.os.Bundle;
import android.os.Handler;
import android.text.InputType;
import android.view.View;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

/** Einstellungen und Auswahl: als Kamera (Station) oder als Alarm-Anzeige starten. */
public class MainActivity extends Activity {
    private final Handler ui = new Handler();
    private Prefs prefs;
    private EditText fServer, fToken, fStation, fPin;
    private TextView status;

    @Override
    public void onCreate(Bundle b) {
        super.onCreate(b);
        prefs = new Prefs(this);
        ScrollView sv = new ScrollView(this);
        sv.setBackgroundColor(Ui.BG);
        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        int pad = Ui.dp(this, 16);
        col.setPadding(pad, pad, pad, pad);
        sv.addView(col);

        String ver = "";
        try {
            PackageInfo pi = getPackageManager().getPackageInfo(getPackageName(), 0);
            ver = pi.versionName == null ? "" : pi.versionName;
        } catch (Exception e) {
            // egal
        }
        col.addView(Ui.text(this, "Hornet3000 Station " + ver, 22, Ui.AMBER, true));
        col.addView(Ui.text(this, "Macht aus diesem Gerät eine Kamera für den Wächter oder eine Alarm-Anzeige.",
                14, Ui.TEXT, false), Ui.wrap(this, 6));

        col.addView(Ui.text(this, "Adresse des Wächters", 14, Ui.DIM, false), Ui.wrap(this, 14));
        fServer = Ui.field(this, prefs.server(), InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI
                | InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        fServer.setHint("z. B. 192.168.1.20:8000");
        col.addView(fServer, Ui.wrap(this, 2));

        col.addView(Ui.text(this, "Zugangsschlüssel (Einrichtung → Zugang)", 14, Ui.DIM, false), Ui.wrap(this, 10));
        fToken = Ui.field(this, prefs.token(), InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD
                | InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        col.addView(fToken, Ui.wrap(this, 2));

        col.addView(Ui.text(this, "Name dieses Geräts", 14, Ui.DIM, false), Ui.wrap(this, 10));
        fStation = Ui.field(this, prefs.station(), InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        col.addView(fStation, Ui.wrap(this, 2));

        col.addView(Ui.text(this, "Nur bei https://: Fingerabdruck des Zertifikats (SHA-256, optional)", 14, Ui.DIM, false),
                Ui.wrap(this, 10));
        fPin = Ui.field(this, prefs.pin(), InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        col.addView(fPin, Ui.wrap(this, 2));

        status = Ui.text(this, "", 14, Ui.TEXT, false);
        col.addView(status, Ui.wrap(this, 12));

        col.addView(Ui.button(this, "Verbindung prüfen", new View.OnClickListener() {
            public void onClick(View v) {
                checkConnection();
            }
        }), Ui.wrap(this, 8));
        col.addView(Ui.button(this, "Als Kamera starten", new View.OnClickListener() {
            public void onClick(View v) {
                launch(StationActivity.class);
            }
        }), Ui.wrap(this, 8));
        col.addView(Ui.button(this, "Als Alarm-Anzeige starten", new View.OnClickListener() {
            public void onClick(View v) {
                launch(AlarmActivity.class);
            }
        }), Ui.wrap(this, 4));
        col.addView(Ui.text(this, "Das Gerät sollte am Ladekabel hängen; der Bildschirm bleibt an, solange die Anzeige "
                + "offen ist. Der Schlüssel wird nur auf diesem Gerät gespeichert.", 12, Ui.DIM, false), Ui.wrap(this, 12));
        setContentView(sv);
    }

    private boolean store() {
        try {
            Client.normalizeBase(fServer.getText().toString());
            Client.checkToken(fToken.getText().toString());
            Client.parsePin(fPin.getText().toString());
        } catch (IllegalArgumentException e) {
            say(e.getMessage(), true);
            return false;
        }
        prefs.save(Client.normalizeBase(fServer.getText().toString()), fToken.getText().toString(),
                Client.headerStation(fStation.getText().toString()), fPin.getText().toString());
        fServer.setText(prefs.server());
        fStation.setText(prefs.station());
        return true;
    }

    private void say(String t, boolean bad) {
        status.setText(t);
        status.setTextColor(bad ? Ui.BAD : Ui.GOOD);
    }

    private void launch(Class<?> target) {
        if (store()) {
            startActivity(new Intent(this, target));
        }
    }

    private void checkConnection() {
        if (!store()) {
            return;
        }
        say("Prüfe …", false);
        final Client c = prefs.client();
        new Thread(new Runnable() {
            public void run() {
                String msg;
                boolean bad = false;
                try {
                    Model.Poll p = c.poll(0);
                    msg = "Verbunden mit Wächter " + p.version + ". Kamera: " + p.cameraText() + ".";
                    try {
                        c.config();
                        msg += " Der Wächter nimmt Bilder von Stationen an.";
                    } catch (ApiException e) {
                        if (e.status == 409) {
                            msg += " Zum Kamera-Betrieb muss die Kamera-Quelle des Wächters auf „push“ stehen.";
                        }
                    }
                } catch (ApiException e) {
                    bad = true;
                    msg = e.isAuth() ? "Zugangsschlüssel abgelehnt." : e.getMessage();
                }
                final String m = msg;
                final boolean isBad = bad;
                ui.post(new Runnable() {
                    public void run() {
                        say(m, isBad);
                    }
                });
            }
        }).start();
    }
}
