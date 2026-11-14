package org.hornet3000.station;

import android.content.Context;
import android.content.res.AssetFileDescriptor;
import android.media.AudioManager;
import android.media.MediaPlayer;
import android.media.ToneGenerator;
import android.os.Vibrator;

/** Alarmton (assets/alarm.wav auf dem Alarm-Kanal, notfalls ein Piepton) und Vibration. */
final class AlarmPlayer {
    private final Context ctx;
    private MediaPlayer mp;
    private ToneGenerator tone;

    AlarmPlayer(Context c) {
        ctx = c;
    }

    synchronized void start(boolean loop) {
        stop();
        try {
            AudioManager am = (AudioManager) ctx.getSystemService(Context.AUDIO_SERVICE);
            if (am != null) {
                am.setStreamVolume(AudioManager.STREAM_ALARM, am.getStreamMaxVolume(AudioManager.STREAM_ALARM), 0);
            }
        } catch (RuntimeException e) {
            // Lautstärke nicht änderbar – egal
        }
        try {
            AssetFileDescriptor fd = ctx.getAssets().openFd("alarm.wav");
            MediaPlayer m = new MediaPlayer();
            try {
                m.setDataSource(fd.getFileDescriptor(), fd.getStartOffset(), fd.getLength());
            } finally {
                fd.close();
            }
            m.setAudioStreamType(AudioManager.STREAM_ALARM);
            m.setLooping(loop);
            m.prepare();
            m.start();
            mp = m;
        } catch (Exception e) {
            fallbackTone();
        }
        try {
            Vibrator v = (Vibrator) ctx.getSystemService(Context.VIBRATOR_SERVICE);
            if (v != null) {
                v.vibrate(new long[] {0, 400, 200, 400, 200, 800}, loop ? 0 : -1);
            }
        } catch (RuntimeException e) {
            // kein Vibrationsmotor / keine Erlaubnis
        }
    }

    private void fallbackTone() {
        try {
            tone = new ToneGenerator(AudioManager.STREAM_ALARM, 100);
            tone.startTone(ToneGenerator.TONE_PROP_BEEP2, 2000);
        } catch (RuntimeException e) {
            tone = null;
        }
    }

    synchronized void stop() {
        if (mp != null) {
            try {
                mp.stop();
            } catch (RuntimeException e) {
                // schon gestoppt
            }
            mp.release();
            mp = null;
        }
        if (tone != null) {
            tone.release();
            tone = null;
        }
        try {
            Vibrator v = (Vibrator) ctx.getSystemService(Context.VIBRATOR_SERVICE);
            if (v != null) {
                v.cancel();
            }
        } catch (RuntimeException e) {
            // egal
        }
    }
}
