// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
package org.hornet3000.station;

import android.app.Activity;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.os.Bundle;
import android.os.Handler;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;

/**
 * Alarm-Anzeige: fragt den Wächter alle 5 s ab, zeigt Zustand und letzte Meldungen und schlägt bei einer neuen Sichtung
 * mit Ton, Vibration und Bild Alarm. Der Alarm läuft bis zum Quittieren, höchstens 5 Minuten. Die Anzeige muss offen
 * sein (der Bildschirm bleibt dafür an; Gerät ans Ladekabel).
 */
public class AlarmActivity extends Activity {
    private static final long ALARM_MAX_MS = 5 * 60 * 1000L;

    private final Handler ui = new Handler();
    private Prefs prefs;
    private Client client;
    private PollLoop loop;
    private AlarmPlayer player;
    private TextView conn, cam, stats, alarmTitle, alarmText, msg;
    private ImageView alarmImg;
    private LinearLayout alarmBox, listBox;
    private Button btnMute, btnUnmute;
    private final List<Model.Alert> shown = new ArrayList<Model.Alert>();
    private boolean firstPoll = true;
    private boolean muted;
    private long currentAlert;
    private Bitmap bitmap;
    private final SimpleDateFormat fmt = new SimpleDateFormat("dd.MM. HH:mm");
    private final Runnable autoStop = new Runnable() {
        public void run() {
            ack();
        }
    };

    @Override
    public void onCreate(Bundle b) {
        super.onCreate(b);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
                | WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED | WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON);
        prefs = new Prefs(this);
        try {
            client = prefs.client();
        } catch (IllegalArgumentException e) {
            Toast.makeText(this, e.getMessage(), Toast.LENGTH_LONG).show();
            finish();
            return;
        }
        player = new AlarmPlayer(this);

        ScrollView sv = new ScrollView(this);
        sv.setBackgroundColor(Ui.BG);
        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        int pad = Ui.dp(this, 12);
        col.setPadding(pad, pad, pad, pad);
        sv.addView(col);

        col.addView(Ui.text(this, "Hornet3000 Alarm-Anzeige", 20, Ui.AMBER, true));
        conn = Ui.text(this, "verbinde …", 14, Ui.DIM, true);
        col.addView(conn, Ui.wrap(this, 4));
        msg = Ui.text(this, "", 14, Ui.BAD, false);
        col.addView(msg, Ui.wrap(this, 2));
        cam = Ui.text(this, "", 16, Ui.TEXT, false);
        col.addView(cam, Ui.wrap(this, 6));
        stats = Ui.text(this, "", 13, Ui.DIM, false);
        col.addView(stats, Ui.wrap(this, 2));

        alarmBox = new LinearLayout(this);
        alarmBox.setOrientation(LinearLayout.VERTICAL);
        alarmBox.setBackgroundColor(android.graphics.Color.rgb(120, 20, 10));
        alarmBox.setPadding(pad, pad, pad, pad);
        alarmTitle = Ui.text(this, "", 22, android.graphics.Color.WHITE, true);
        alarmText = Ui.text(this, "", 16, android.graphics.Color.WHITE, false);
        alarmImg = new ImageView(this);
        alarmImg.setAdjustViewBounds(true);
        alarmBox.addView(alarmTitle);
        alarmBox.addView(alarmText, Ui.wrap(this, 4));
        alarmBox.addView(alarmImg, Ui.wrap(this, 8));
        alarmBox.addView(Ui.button(this, "Quittieren", new View.OnClickListener() {
            public void onClick(View v) {
                ack();
            }
        }), Ui.wrap(this, 8));
        alarmBox.setVisibility(View.GONE);
        col.addView(alarmBox, Ui.wrap(this, 10));

        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        btnMute = Ui.button(this, "Stumm 1 h", new View.OnClickListener() {
            public void onClick(View v) {
                command(true);
            }
        });
        btnUnmute = Ui.button(this, "Stumm aufheben", new View.OnClickListener() {
            public void onClick(View v) {
                command(false);
            }
        });
        btnUnmute.setVisibility(View.GONE);
        row.addView(btnMute, Ui.weight(1));
        row.addView(btnUnmute, Ui.weight(1));
        row.addView(Ui.button(this, "Testalarm", new View.OnClickListener() {
            public void onClick(View v) {
                testAlert();
            }
        }), Ui.weight(1));
        row.addView(Ui.button(this, "Beenden", new View.OnClickListener() {
            public void onClick(View v) {
                finish();
            }
        }), Ui.weight(1));
        col.addView(row, Ui.wrap(this, 10));

        col.addView(Ui.text(this, "Letzte Meldungen", 14, Ui.DIM, true), Ui.wrap(this, 14));
        listBox = new LinearLayout(this);
        listBox.setOrientation(LinearLayout.VERTICAL);
        col.addView(listBox, Ui.wrap(this, 2));
        setContentView(sv);
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (client == null) {
            return;
        }
        firstPoll = true;
        shown.clear();
        loop = new PollLoop(client, new PollLoop.Listener() {
            public void onPoll(final Model.Poll p, final List<Model.Alert> fresh) {
                ui.post(new Runnable() {
                    public void run() {
                        onPolled(p, fresh);
                    }
                });
            }

            public void onError(final int failures, final String text, final boolean fatal) {
                ui.post(new Runnable() {
                    public void run() {
                        conn.setText("getrennt");
                        conn.setTextColor(Ui.BAD);
                        msg.setText(text + (fatal ? "" : " – es wird weiter versucht"));
                    }
                });
            }
        }, 5000);
        Thread t = new Thread(loop, "poll-loop");
        t.setDaemon(true);
        t.start();
    }

    @Override
    protected void onPause() {
        if (loop != null) {
            loop.stop();
            loop = null;
        }
        ack();
        super.onPause();
    }

    // ---- Anzeige ------------------------------------------------------------------------------------------------------
    private void onPolled(Model.Poll p, List<Model.Alert> fresh) {
        conn.setText("verbunden · Wächter " + p.version);
        conn.setTextColor(Ui.GOOD);
        msg.setText("");
        cam.setText(p.cameraText());
        cam.setTextColor(p.cameraOnline ? Ui.GOOD : Ui.BAD);
        muted = p.muted;
        btnMute.setVisibility(muted ? View.GONE : View.VISIBLE);
        btnUnmute.setVisibility(muted ? View.VISIBLE : View.GONE);
        stats.setText("24 h: " + p.alarms24h + (p.alarms24h == 1 ? " Alarm" : " Alarme") + " · jetzt erkannt: "
                + p.detectionsNow + (muted ? " · STUMM bis " + fmt.format(new Date((long) (p.muteUntil * 1000))) : ""));
        if (firstPoll) {
            shown.clear();
            shown.addAll(p.alerts);
            firstPoll = false;
            renderList();
            return;
        }
        if (!fresh.isEmpty()) {
            List<Model.Alert> merged = new ArrayList<Model.Alert>(p.alerts);
            merged.addAll(shown);
            shown.clear();
            for (int i = 0; i < merged.size() && i < 30; i++) {
                shown.add(merged.get(i));
            }
            renderList();
            Model.Alert top = AlertTracker.pickTop(fresh);
            raise(top, muted || top.muted);
        }
    }

    private void renderList() {
        listBox.removeAllViews();
        if (shown.isEmpty()) {
            listBox.addView(Ui.text(this, "Noch keine Meldungen.", 13, Ui.DIM, false));
            return;
        }
        for (int i = 0; i < shown.size() && i < 12; i++) {
            Model.Alert a = shown.get(i);
            String line = fmt.format(new Date((long) (a.ts * 1000))) + " · " + Model.Alert.kindName(a.kind)
                    + (a.muted ? " (stumm)" : "") + "\n" + a.text();
            TextView t = Ui.text(this, line, 14, "new".equals(a.kind) ? Ui.AMBER : Ui.TEXT, false);
            listBox.addView(t, Ui.wrap(this, 6));
        }
    }

    private void raise(Model.Alert a, boolean silent) {
        boolean test = "test".equals(a.kind);
        currentAlert = a.id;
        alarmTitle.setText(("new".equals(a.kind) ? "ALARM – " : "") + Model.Alert.kindName(a.kind));
        alarmText.setText(fmt.format(new Date((long) (a.ts * 1000))) + " · " + a.text()
                + (silent ? " · stumm geschaltet" : ""));
        alarmImg.setImageDrawable(null);
        if (bitmap != null) {
            bitmap.recycle();
            bitmap = null;
        }
        alarmBox.setVisibility(View.VISIBLE);
        ui.removeCallbacks(autoStop);
        player.stop();
        if (a.snapshotUrl.length() > 0) {
            loadSnapshot(a.id, a.snapshotUrl);
        }
        if (silent) {
            return;
        }
        player.start(!test);
        if (!test) {
            ui.postDelayed(autoStop, ALARM_MAX_MS);
        }
    }

    private void ack() {
        ui.removeCallbacks(autoStop);
        if (player != null) {
            player.stop();
        }
        if (alarmBox != null) {
            alarmBox.setVisibility(View.GONE);
        }
    }

    private void loadSnapshot(final long alertId, final String path) {
        final Client c = client;
        Thread t = new Thread(new Runnable() {
            public void run() {
                try {
                    byte[] data = c.fetchMedia(path);
                    BitmapFactory.Options o = new BitmapFactory.Options();
                    o.inJustDecodeBounds = true;
                    BitmapFactory.decodeByteArray(data, 0, data.length, o);
                    if (o.outWidth <= 0 || o.outHeight <= 0) {
                        return;
                    }
                    int s = 1;
                    while (s < 64 && (o.outWidth / s > 1024 || o.outHeight / s > 1024)) {
                        s *= 2;
                    }
                    BitmapFactory.Options o2 = new BitmapFactory.Options();
                    o2.inSampleSize = s;
                    final Bitmap bm = BitmapFactory.decodeByteArray(data, 0, data.length, o2);
                    if (bm == null) {
                        return;
                    }
                    ui.post(new Runnable() {
                        public void run() {
                            if (currentAlert == alertId && alarmBox.getVisibility() == View.VISIBLE) {
                                bitmap = bm;
                                alarmImg.setImageBitmap(bm);
                            } else {
                                bm.recycle();
                            }
                        }
                    });
                } catch (ApiException e) {
                    // kein Bild – der Alarm läuft trotzdem
                } catch (RuntimeException e) {
                    // Bild nicht lesbar
                } catch (OutOfMemoryError e) {
                    // zu wenig Speicher auf dem Altgerät
                }
            }
        }, "snapshot");
        t.setDaemon(true);
        t.start();
    }

    // ---- Befehle an den Wächter -------------------------------------------------------------------------------------
    private void command(final boolean mute) {
        final Client c = client;
        Thread t = new Thread(new Runnable() {
            public void run() {
                try {
                    if (mute) {
                        c.mute(60);
                    } else {
                        c.unmute();
                    }
                    PollLoop l = loop;
                    if (l != null) {
                        l.pollNow();
                    }
                } catch (final ApiException e) {
                    ui.post(new Runnable() {
                        public void run() {
                            msg.setText(e.getMessage());
                        }
                    });
                }
            }
        }, "command");
        t.setDaemon(true);
        t.start();
    }

    private void testAlert() {
        final Client c = client;
        Thread t = new Thread(new Runnable() {
            public void run() {
                try {
                    c.testAlert();
                    PollLoop l = loop;
                    if (l != null) {
                        l.pollNow();
                    }
                } catch (final ApiException e) {
                    ui.post(new Runnable() {
                        public void run() {
                            msg.setText(e.getMessage());
                        }
                    });
                }
            }
        }, "test");
        t.setDaemon(true);
        t.start();
    }
}
