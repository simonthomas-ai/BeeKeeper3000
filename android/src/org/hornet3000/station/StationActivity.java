package org.hornet3000.station;

import android.app.Activity;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.ImageFormat;
import android.hardware.Camera;
import android.os.Bundle;
import android.os.Handler;
import android.view.Gravity;
import android.view.SurfaceHolder;
import android.view.SurfaceView;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import java.util.List;

/**
 * Kamera-Betrieb: zeigt die Kamera-Vorschau und schickt in ruhigem Takt Einzelbilder (JPEG) an den Wächter. Die Kamera
 * läuft nur, solange dieser Bildschirm vorne ist (ab Android 9 erlaubt das System ohnehin keine Kamera im Hintergrund);
 * der Bildschirm bleibt an. Wiederholung/Wartezeiten steckt in StationLoop (dort JVM-geprüft).
 */
public class StationActivity extends Activity implements SurfaceHolder.Callback {
    private static final int REQ_CAMERA = 11;

    private final Handler ui = new Handler();
    private Prefs prefs;
    private Client client;
    private SurfaceView surface;
    private SurfaceHolder holder;
    private TextView status;
    private Button btnSwitch;
    private Camera camera;
    private CameraSource source;
    private StationLoop loop;
    private boolean surfaceReady, resumed, permAsked, dimmed, fatal;
    private int stateKind = StationLoop.WAIT;
    private String stateText = "Starte …";
    private long sentTotal;
    private int lastBytes;
    private int generation;                 // jede neue Schleife bekommt eine Nummer; Meldungen alter Schleifen werden verworfen

    @Override
    public void onCreate(Bundle b) {
        super.onCreate(b);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        prefs = new Prefs(this);
        try {
            client = prefs.client();
        } catch (IllegalArgumentException e) {
            Toast.makeText(this, e.getMessage(), Toast.LENGTH_LONG).show();
            finish();
            return;
        }
        source = new CameraSource();

        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.BLACK);
        surface = new SurfaceView(this);
        holder = surface.getHolder();
        holder.addCallback(this);
        holder.setType(SurfaceHolder.SURFACE_TYPE_PUSH_BUFFERS);     // nur für Android < 3 nötig
        root.addView(surface, new FrameLayout.LayoutParams(FrameLayout.LayoutParams.FILL_PARENT,
                FrameLayout.LayoutParams.FILL_PARENT));

        LinearLayout bar = new LinearLayout(this);
        bar.setOrientation(LinearLayout.VERTICAL);
        bar.setBackgroundColor(Color.argb(170, 0, 0, 0));
        int pad = Ui.dp(this, 8);
        bar.setPadding(pad, pad, pad, pad);
        status = Ui.text(this, "", 14, Ui.TEXT, false);
        bar.addView(status);
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        btnSwitch = Ui.button(this, "Kamera wechseln", new View.OnClickListener() {
            public void onClick(View v) {
                switchCamera();
            }
        });
        row.addView(btnSwitch, Ui.weight(1));
        row.addView(Ui.button(this, "Display dunkel", new View.OnClickListener() {
            public void onClick(View v) {
                toggleDim((Button) v);
            }
        }), Ui.weight(1));
        row.addView(Ui.button(this, "Beenden", new View.OnClickListener() {
            public void onClick(View v) {
                finish();
            }
        }), Ui.weight(1));
        bar.addView(row);
        FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(FrameLayout.LayoutParams.FILL_PARENT,
                FrameLayout.LayoutParams.WRAP_CONTENT, Gravity.BOTTOM);
        root.addView(bar, lp);
        setContentView(root);
        btnSwitch.setVisibility(Compat.cameraCount() > 1 ? View.VISIBLE : View.GONE);
        render();
    }

    // ---- Lebenslauf ---------------------------------------------------------------------------------------------
    @Override
    protected void onResume() {
        super.onResume();
        resumed = true;
        tryStart();
    }

    @Override
    protected void onPause() {
        resumed = false;
        stopAll();
        super.onPause();
    }

    public void surfaceCreated(SurfaceHolder h) {
        surfaceReady = true;
        tryStart();
    }

    public void surfaceChanged(SurfaceHolder h, int format, int w, int hh) {
    }

    public void surfaceDestroyed(SurfaceHolder h) {
        surfaceReady = false;
        stopAll();
    }

    // Ab Android 6 ruft das System diese Methode auf; vorher gibt es sie nicht (darum ohne @Override).
    public void onRequestPermissionsResult(int code, String[] perms, int[] results) {
        if (code != REQ_CAMERA) {
            return;
        }
        if (results != null && results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED) {
            tryStart();
        } else {
            setState(StationLoop.FATAL, "Ohne Kamera-Erlaubnis kann diese Station kein Bild liefern. "
                    + "Erlaubnis unter Einstellungen → Apps → Hornet3000 Station erteilen.");
        }
    }

    private void tryStart() {
        if (!resumed || !surfaceReady || camera != null || client == null || fatal) {
            return;
        }
        if (!Compat.hasCameraPermission(this)) {
            if (!permAsked) {
                permAsked = true;
                Compat.requestCameraPermission(this, REQ_CAMERA);
            }
            setState(StationLoop.WAIT, "Warte auf die Kamera-Erlaubnis …");
            return;
        }
        startCamera();
    }

    // ---- Kamera -----------------------------------------------------------------------------------------------------
    private void startCamera() {
        int n = Compat.cameraCount();
        int idx = Math.max(0, Math.min(prefs.camera(), n - 1));
        Camera c = null;
        try {
            c = Compat.openCamera(idx);
        } catch (RuntimeException e) {
            c = null;
        }
        if (c == null) {
            setState(StationLoop.ERROR, "Kamera nicht verfügbar – wird sie von einer anderen App benutzt?");
            ui.postDelayed(new Runnable() {
                public void run() {
                    tryStart();
                }
            }, 5000);
            return;
        }
        try {
            configure(c);
            c.setPreviewDisplay(holder);
            c.setPreviewCallback(source);
            c.startPreview();
        } catch (Exception e) {
            try {
                c.release();
            } catch (RuntimeException e2) {
                // egal
            }
            setState(StationLoop.ERROR, "Kamera lässt sich nicht starten (" + e.getClass().getSimpleName() + ")");
            return;
        }
        camera = c;
        final int gen = ++generation;
        loop = new StationLoop(client, source, new StationLoop.Listener() {
            public void onState(final int kind, final String text) {
                ui.post(new Runnable() {
                    public void run() {
                        if (gen == generation) {
                            setState(kind, text);
                        }
                    }
                });
            }

            public void onSent(final long total, final int bytes) {
                ui.post(new Runnable() {
                    public void run() {
                        if (gen == generation) {
                            sentTotal = total;
                            lastBytes = bytes;
                            render();
                        }
                    }
                });
            }
        });
        Thread t = new Thread(loop, "station-loop");
        t.setDaemon(true);
        t.start();
        btnSwitch.setText("Kamera " + (idx + 1) + "/" + n + " " + Compat.facing(idx));
    }

    /** Vorschaugröße, Bildrate und Fokus einstellen – jedes einzeln und fehlertolerant (Geräte sind da eigenwillig). */
    private void configure(Camera c) {
        Camera.Parameters p = c.getParameters();
        try {
            List<Camera.Size> sizes = p.getSupportedPreviewSizes();
            if (sizes != null && !sizes.isEmpty()) {
                int[] w = new int[sizes.size()];
                int[] h = new int[sizes.size()];
                for (int i = 0; i < w.length; i++) {
                    w[i] = sizes.get(i).width;
                    h[i] = sizes.get(i).height;
                }
                int k = Logic.chooseSize(w, h, 800, 320);
                if (k >= 0) {
                    p.setPreviewSize(w[k], h[k]);
                }
            }
        } catch (RuntimeException e) {
            // Standardgröße bleibt
        }
        try {
            if (p.getPreviewFormat() != ImageFormat.NV21) {
                p.setPreviewFormat(ImageFormat.NV21);
            }
        } catch (RuntimeException e) {
            // NV21 ist ohnehin der Standard
        }
        try {
            List<Integer> rates = p.getSupportedPreviewFrameRates();
            if (rates != null && !rates.isEmpty()) {
                int[] r = new int[rates.size()];
                for (int i = 0; i < r.length; i++) {
                    r[i] = rates.get(i).intValue();
                }
                int best = Logic.chooseFrameRate(r, 1000);
                if (best > 0) {
                    p.setPreviewFrameRate(best);
                }
            }
        } catch (RuntimeException e) {
            // Bildrate bleibt wie sie ist
        }
        try {
            List<String> modes = p.getSupportedFocusModes();
            if (modes != null) {
                if (modes.contains("continuous-picture")) {
                    p.setFocusMode("continuous-picture");
                } else if (modes.contains("continuous-video")) {
                    p.setFocusMode("continuous-video");
                }
            }
        } catch (RuntimeException e) {
            // Fokus bleibt Standard
        }
        try {
            c.setParameters(p);
        } catch (RuntimeException e) {
            // manche Geräte lehnen die Kombination ab: dann mit den Standardwerten weiter
        }
        try {
            c.setDisplayOrientation(0);
        } catch (RuntimeException e) {
            // egal
        }
        Camera.Size s = c.getParameters().getPreviewSize();
        source.setSize(s.width, s.height);
    }

    private void stopAll() {
        generation++;
        if (loop != null) {
            loop.stop();
            loop = null;
        }
        if (camera != null) {
            try {
                camera.setPreviewCallback(null);
                camera.stopPreview();
            } catch (RuntimeException e) {
                // Kamera war schon weg
            }
            try {
                camera.release();
            } catch (RuntimeException e) {
                // egal
            }
            camera = null;
        }
    }

    private void switchCamera() {
        int n = Compat.cameraCount();
        prefs.saveCamera((prefs.camera() + 1) % n);
        stopAll();
        fatal = false;
        tryStart();
    }

    private void toggleDim(Button b) {
        dimmed = !dimmed;
        WindowManager.LayoutParams lp = getWindow().getAttributes();
        lp.screenBrightness = dimmed ? 0.02f : -1f;
        getWindow().setAttributes(lp);
        b.setText(dimmed ? "Display hell" : "Display dunkel");
    }

    // ---- Anzeige ----------------------------------------------------------------------------------------------------
    private void setState(int kind, String text) {
        stateKind = kind;
        stateText = text;
        if (kind == StationLoop.FATAL) {
            fatal = true;
            stopAll();
        }
        render();
    }

    private void render() {
        if (status == null) {
            return;
        }
        String head = "Station „" + prefs.station() + "“ · " + sentTotal + " Bilder gesendet"
                + (lastBytes > 0 ? " (zuletzt " + (lastBytes / 1024) + " KB)" : "");
        status.setText(head + "\n" + stateText);
        status.setTextColor(stateKind == StationLoop.OK ? Ui.GOOD : stateKind == StationLoop.WAIT ? Ui.TEXT : Ui.BAD);
    }
}
