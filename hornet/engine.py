"""Erkennungs- und Alarmlogik.

Ablauf:  Kamera -> Detektor -> Bestätigung (k von n Bildern) -> Ereignis (ein Alarm je Besuch)
         -> optional KI-Prüfung -> SOFORT Foto+Text an alle Kanäle -> Clip mit Ton folgt nach dem Nachlauf.
"""
from __future__ import annotations

import io
import logging
import queue
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

from . import __version__, security, verifier
from .camera import Camera
from .config import Settings
from .detector import Detection, YoloOnnx, iou
from .phonecam import PhoneCamera
from .imaging import LATIN, crop_around, display_name, draw_detections, to_jpeg
from .notifiers import Hub
from .store import Store

log = logging.getLogger("hornet.engine")

CROSS_CHECK_IOU = 0.5


class EventBus:
    """Verteilt Ereignisse (Alarm, Status …) an offene PWA-Sitzungen (Server-Sent Events)."""

    def __init__(self) -> None:
        self._subs: list[queue.Queue] = []
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=200)
        with self._lock:
            self._subs.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)

    def publish(self, event: str, data: dict) -> None:
        with self._lock:
            subs = list(self._subs)
        for q in subs:
            try:
                q.put_nowait((event, data))
            except queue.Full:
                pass


def compose_texts(s: Settings, kind: str, *, camera: str, ts: float, count: int, conf: float,
                  verdict: verifier.Verdict, link: str | None) -> tuple[str, str]:
    """Liefert (ausführlicher Text, SMS-Kurztext)."""
    when = time.strftime("%H:%M:%S", time.localtime(ts))
    day = time.strftime("%d.%m.%Y", time.localtime(ts))
    animals = "1 Tier" if count == 1 else f"{count} Tiere"
    pct = int(round(conf * 100))
    heads = {
        "new": ("🐝 ALARM – Asiatische Hornisse erkannt", "HORNISSEN-ALARM"),
        "update": (f"⚠️ Verstärkung – jetzt {animals} am Stock", "HORNISSEN-ALARM Verstaerkung"),
        "reminder": ("⏱️ Aktivität dauert an – Asiatische Hornisse", "HORNISSEN-ALARM dauert an"),
        "test": ("🧪 TEST-ALARM – alles in Ordnung, keine Hornisse", "TEST Hornet3000"),
    }
    head, sms_head = heads.get(kind, heads["new"])
    if verdict.contradicts and kind != "test":
        head = "❓ Verdacht – KI-Prüfung widerspricht"
    lines = [head, f"{camera} · {when} Uhr · {day}"]
    if kind != "test":
        lines.append(f"{animals} · Erkennungssicherheit {pct} %")
    if verdict.provider != "none" and kind in ("new", "test"):
        if verdict.error:
            lines.append("KI-Prüfung: nicht möglich (Fehler) – bitte Foto selbst ansehen")
        elif verdict.confirms:
            lines.append(f"KI-Prüfung: bestätigt Vespa velutina ({int(verdict.sicherheit * 100)} %)")
        elif verdict.contradicts:
            art = {"crabro": "Europäische Hornisse (geschützt!)", "andere_wespe": "eine andere Wespe",
                   "biene": "eine Biene", "anderes_insekt": "ein anderes Insekt"}.get(verdict.art, verdict.art)
            lines.append(f"KI-Prüfung: sieht eher nach {art} aus – bitte selbst prüfen")
        else:
            lines.append("KI-Prüfung: unklar – bitte Foto selbst ansehen")
        if verdict.merkmale and not verdict.error:
            lines.append(f"„{verdict.merkmale}“")
    if kind in ("new", "update"):
        lines.append("Erst Art am Foto bestätigen, nicht selbst bekämpfen: die Europäische Hornisse ist geschützt.")
    if link:
        lines.append(f"Foto & Video: {link}")
    sms = f"{sms_head} {camera} {when}"
    if kind != "test":
        sms += f", {animals}, {pct}%"
    if verdict.contradicts and kind != "test":
        sms += ", KI-Pruefung: eher andere Art"
    if link:
        sms += f". {link}"
    return "\n".join(lines), sms


class Engine:
    def __init__(self, s: Settings, store: Store, hub: Hub, bus: EventBus | None = None,
                 detector: YoloOnnx | None = None):
        self.s, self.store, self.hub = s, store, hub
        self.bus = bus or EventBus()
        self.detector = detector
        self.model_error = ""
        camera_cls = PhoneCamera if s.camera_source.strip().lower() == "phone" else Camera
        self.camera = camera_cls(s, self._on_frame)
        self._latest: tuple[bytes, float] | None = None
        self._latest_lock = threading.Lock()
        self._frame_evt = threading.Event()
        self.live_jpeg: bytes | None = None
        self.live_ts = 0.0
        self.last_dets: list[Detection] = []
        self.last_seen: dict[str, float] = {}
        self._window: deque[bool] = deque(maxlen=max(1, s.confirm_window))
        self._best: dict | None = None
        self.event: dict | None = None
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="alert")
        self._stop = threading.Event()
        self.started = time.time()
        self.frames_processed = 0
        self.infer_ms = 0.0
        self.tuning = {"conf_alert": s.conf_alert, "confirm_hits": s.confirm_hits, "event_gap_s": s.event_gap_s}
        saved = store.kv_get("tuning")
        if isinstance(saved, dict):
            for k in self.tuning:
                if k in saved:
                    self.tuning[k] = saved[k]
        self.telegram_cmds = None
        self.mesh = None  # MeshService (Funknetz), von server.create_app gesetzt

    # -- Lebenszyklus -----------------------------------------------------------------
    def start(self) -> None:
        self.camera.start()
        self._detect_thread = threading.Thread(target=self._loop, daemon=True, name="detect")
        self._detect_thread.start()
        threading.Thread(target=self._housekeeping, daemon=True, name="housekeeping").start()
        if self.mesh is not None:
            self.mesh.start()
        if self.s.telegram_commands and self.hub.telegram.token:
            from .notifiers.telegram import TelegramCommands

            self.telegram_cmds = TelegramCommands(self.hub.telegram, {
                "status": self._cmd_status, "foto": self._cmd_foto, "stumm": self._cmd_mute, "laut": self._cmd_unmute})
            self.telegram_cmds.start()

    def stop(self) -> None:
        self._stop.set()
        self._frame_evt.set()
        self.camera.stop()
        th = getattr(self, "_detect_thread", None)
        if th is not None:
            th.join(timeout=5)  # laufende Inferenz sauber beenden (sonst Absturzmeldung von onnxruntime beim Beenden)
        if self.telegram_cmds:
            self.telegram_cmds.stop()
        if self.mesh is not None:
            self.mesh.stop()
        # wait=True: ein noch laufender Alarmversand (Clip-Wartezeit, HTTP-Zustellung) darf zu Ende laufen,
        # bevor store.close() folgt – sonst könnte er in eine bereits geschlossene Datenbank schreiben.
        # Noch nicht begonnene, wartende Aufgaben werden weiterhin sofort verworfen (cancel_futures=True).
        self.pool.shutdown(wait=True, cancel_futures=True)

    def _housekeeping(self) -> None:
        while not self._stop.wait(3600):
            try:
                n = self.store.cleanup(self.s.alerts_dir, self.s.retention_days)
                if n:
                    log.info("%d alte Alarme gelöscht", n)
            except Exception as e:
                log.warning("Aufräumen fehlgeschlagen: %s", e)

    # -- Einstellungen zur Laufzeit -------------------------------------------------------
    def set_tuning(self, **kw) -> dict:
        limits = {"conf_alert": (0.3, 0.99, float), "confirm_hits": (1, 20, int), "event_gap_s": (30, 7200, int)}
        for k, v in kw.items():
            if k in limits and v is not None:
                lo, hi, typ = limits[k]
                self.tuning[k] = max(lo, min(hi, typ(v)))
        self.store.kv_set("tuning", self.tuning)
        return self.tuning

    # -- Stummschalten ----------------------------------------------------------------
    @property
    def mute_until(self) -> float:
        return float(self.store.kv_get("mute_until", 0) or 0)

    def is_muted(self) -> bool:
        return time.time() < self.mute_until

    def mute(self, minutes: float) -> float:
        until = time.time() + max(1.0, minutes) * 60
        self.store.kv_set("mute_until", until)
        self.bus.publish("status", {"muted": True, "mute_until": until})
        return until

    def unmute(self) -> None:
        self.store.kv_set("mute_until", 0)
        self.bus.publish("status", {"muted": False, "mute_until": 0})

    # -- Frames -----------------------------------------------------------------------
    def _on_frame(self, jpeg: bytes, ts: float) -> None:
        with self._latest_lock:
            self._latest = (jpeg, ts)
        if self.detector is None:  # ohne Modell trotzdem Live-Bild zeigen
            self.live_jpeg, self.live_ts = jpeg, ts
        self._frame_evt.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            if not self._frame_evt.wait(1.0):
                continue
            self._frame_evt.clear()
            with self._latest_lock:
                frame = self._latest
            if not frame:
                continue
            jpeg, ts = frame
            try:
                img = Image.open(io.BytesIO(jpeg))
                img.load()
            except Exception:
                continue
            dets: list[Detection] = []
            if self.detector is not None:
                t0 = time.time()
                try:
                    dets = self.detector.detect(img, self.s.conf_min)
                except Exception as e:
                    self.model_error = f"{type(e).__name__}: {e}"
                    log.error("Erkennung fehlgeschlagen: %s", e)
                dt = (time.time() - t0) * 1000
                self.infer_ms = dt if self.infer_ms == 0 else 0.9 * self.infer_ms + 0.1 * dt
            try:
                self._handle(img, jpeg, dets, ts)
            except Exception:
                log.exception("Fehler in der Alarmlogik")

    # -- Auswertung -------------------------------------------------------------------
    def _classify(self, dets: list[Detection]) -> list[Detection]:
        alert = set(self.s.alert_classes)
        prot = set(self.s.protected_classes)
        cand = [d for d in dets if d.name in alert and d.conf >= self.tuning["conf_alert"]]
        prots = [d for d in dets if d.name in prot]
        # dieselbe Stelle wurde mindestens ebenso sicher als geschützte Art erkannt -> kein Alarm
        return [d for d in cand if not any(iou(d.box, p.box) > CROSS_CHECK_IOU and p.conf >= d.conf for p in prots)]

    def _handle(self, img: Image.Image, jpeg: bytes, dets: list[Detection], ts: float) -> None:
        self.frames_processed += 1
        self.last_dets = dets
        for d in dets:
            if d.conf >= self.tuning["conf_alert"]:
                self.last_seen[d.name] = ts
        if dets:
            ann = draw_detections(img, dets, set(self.s.alert_classes), set(self.s.protected_classes))
            self.live_jpeg = to_jpeg(ann, 80)
        else:
            self.live_jpeg = jpeg
        self.live_ts = ts

        hits = self._classify(dets)
        self._window.append(bool(hits))
        if hits:
            conf = max(d.conf for d in hits)
            if self._best is None or conf > self._best["conf"]:
                self._best = {"conf": conf, "jpeg": jpeg, "dets": dets, "hits": hits, "ts": ts}
        if not any(self._window):
            self._best = None
        if sum(self._window) >= self.tuning["confirm_hits"] and self._best is not None:
            self._confirmed(hits or self._best["hits"])

    def _confirmed(self, hits: list[Detection]) -> None:
        now = time.time()
        tun = self.tuning
        ev = self.event
        count = len(hits)
        kind: str | None = None
        if ev is None or now - ev["last_hit"] > tun["event_gap_s"]:
            ev = self.event = {"id": int(now), "first": now, "last_hit": now, "max_count": count,
                               "last_alert": now, "alerts": 1}
            kind = "new"
        else:
            ev["last_hit"] = now
            if count > ev["max_count"] and now - ev["last_alert"] >= self.s.escalate_min_s:
                ev["max_count"] = count
                kind = "update"
            elif now - ev["last_alert"] >= self.s.reminder_s:
                kind = "reminder"
            else:
                ev["max_count"] = max(ev["max_count"], count)
            if kind:
                ev["last_alert"] = now
                ev["alerts"] += 1
        if kind:
            best = dict(self._best)
            self.pool.submit(self._raise_alert, kind, dict(ev), best, count)

    # -- Alarm --------------------------------------------------------------------------
    def share_link(self, alert_id: int) -> str | None:
        if not self.s.public_url:
            return None
        exp, sig = security.sign_alert(self.s.access_token, alert_id)
        return f"{self.s.public_url}/share/{alert_id}?e={exp}&s={sig}"

    def _media_url(self, alert_id: int, name: str) -> str:
        exp, sig = security.sign_alert(self.s.access_token, alert_id)
        return f"/media/{alert_id}/{name}?e={exp}&s={sig}"

    def _raise_alert(self, kind: str, ev: dict, best: dict, count: int) -> int | None:
        try:
            return self._raise_alert_inner(kind, ev, best, count)
        except Exception:
            log.exception("Alarmverarbeitung fehlgeschlagen")
            return None

    def _raise_alert_inner(self, kind: str, ev: dict, best: dict, count: int) -> int:
        s, store = self.s, self.store
        ts = best["ts"]
        img = Image.open(io.BytesIO(best["jpeg"]))
        img.load()
        dets: list[Detection] = best["dets"]
        top = max(best["hits"], key=lambda d: d.conf) if best["hits"] else None
        species = top.name if top else "test"
        conf = top.conf if top else 1.0
        muted = self.is_muted() and kind != "test"

        alert_id = store.add_alert(
            ts=ts, camera=s.camera_name, kind=kind, species=species,
            label=display_name(species) if top else "Test", conf=round(conf, 3), count=count,
            muted=int(muted), event_id=ev.get("id"), detections=[d.to_dict() for d in dets])
        adir = s.alerts_dir / str(alert_id)
        adir.mkdir(parents=True, exist_ok=True)
        ann = draw_detections(img, dets, set(s.alert_classes), set(s.protected_classes))
        snap = adir / "snapshot.jpg"
        snap.write_bytes(to_jpeg(ann, 88))
        store.update_alert(alert_id, snapshot=f"{alert_id}/snapshot.jpg")
        summary = {"id": alert_id, "kind": kind, "label": display_name(species) if top else "Test",
                   "count": count, "conf": round(conf, 3), "ts": ts, "muted": muted,
                   "camera": s.camera_name, "snapshot": f"/media/{alert_id}/snapshot.jpg"}
        self.bus.publish("alert", summary)  # PWA klingelt sofort – noch vor Versand und KI-Prüfung

        verdict = verifier.Verdict()
        if kind in ("new", "test") and verifier.resolve_provider(s) != "none":
            crop = crop_around(img, top.box) if top else img
            verdict = verifier.verify(s, to_jpeg(crop, 88), to_jpeg(img, 82, 1024))
            store.update_alert(alert_id, verify=verdict.to_dict())

        if self.mesh is not None and kind in ("new", "update") and not muted:
            try:  # Nachbarstationen informieren (Warteschlange, blockiert nicht)
                ai = "-" if verdict.provider == "none" else "J" if verdict.confirms else "N" if verdict.contradicts else "?"
                self.mesh.announce(kind, count, conf, "?" if verdict.error else ai)
            except Exception:
                log.exception("Funknetz: Sichtung konnte nicht gemeldet werden")

        link = self.share_link(alert_id)
        long_text, short_text = compose_texts(s, kind, camera=s.camera_name, ts=time.time(), count=count,
                                              conf=conf, verdict=verdict, link=link)
        meta = {"url": f"/#alarm-{alert_id}", "image_url": self._media_url(alert_id, "snapshot.jpg"),
                "tag": "hornet", "alert_id": alert_id}
        if not muted:
            res = self.hub.dispatch("alarm", long_text, short_text, snap, meta)
            store.merge_delivery(alert_id, res)
            self.bus.publish("delivery", {"id": alert_id, "delivery": store.get_alert(alert_id)["delivery"]})

        if kind in ("new", "test") and s.clip_enabled:
            clip = self.camera.make_clip(ts, adir / "clip.mp4")
            if clip:
                store.update_alert(alert_id, clip=f"{alert_id}/clip.mp4")
                self.bus.publish("clip", {"id": alert_id, "clip": f"/media/{alert_id}/clip.mp4"})
                if not muted:
                    cap = f"🎬 Clip mit Ton · {s.camera_name} · {time.strftime('%H:%M:%S', time.localtime(ts))}"
                    res = self.hub.dispatch("clip", cap, cap, clip, meta)
                    store.merge_delivery(alert_id, res)
                    self.bus.publish("delivery", {"id": alert_id, "delivery": store.get_alert(alert_id)["delivery"]})
            else:
                log.warning("Kein Clip erzeugt (keine Segmente verfügbar?)")
        return alert_id

    def has_frame(self) -> bool:
        with self._latest_lock:
            return self._latest is not None and time.time() - self._latest[1] < 30

    def test_alert(self) -> int | None:
        """Vollständiger Testlauf über die echte Kette: aktuelles Kamerabild, Video mit Ton, alle Meldewege."""
        with self._latest_lock:
            frame = self._latest
        if frame is None or time.time() - frame[1] > 30:
            raise RuntimeError("Kein aktuelles Kamerabild – Kamera prüfen")
        jpeg, ts = frame
        best = {"conf": 1.0, "jpeg": jpeg, "dets": [], "hits": [], "ts": time.time()}
        fut = self.pool.submit(self._raise_alert, "test", {"id": None}, best, 1)
        return fut.result(timeout=120)

    def test_alert_async(self) -> None:
        """Wie test_alert(), kehrt aber sofort zurück (Ergebnis kommt per Server-Sent Event in die PWA)."""
        if not self.has_frame():
            raise RuntimeError("Kein aktuelles Kamerabild – Kamera prüfen")
        threading.Thread(target=self.test_alert, daemon=True, name="test-alert").start()

    # -- Telegram-Befehle -----------------------------------------------------------------
    def status(self) -> dict:
        cam = self.camera
        cam_info = {"name": self.s.camera_name, "online": cam.online, "state": cam.state, "error": cam.error,
                    "source": cam.source_label, "last_frame_age": round(time.time() - cam.last_frame_ts, 1)
                    if cam.last_frame_ts else None, "restarts": cam.restarts,
                    "type": "phone" if isinstance(cam, PhoneCamera) else "stream"}
        if isinstance(cam, PhoneCamera):
            cam_info.update(cam.status_extra())
        return {
            "version": __version__,
            "camera": cam_info,
            "detector": {"loaded": self.detector is not None, "provider": getattr(self.detector, "provider", None),
                         "model": Path(self.s.model_path).name, "error": self.model_error,
                         "classes": getattr(self.detector, "names", {}), "infer_ms": round(self.infer_ms),
                         "frames": self.frames_processed},
            "tuning": self.tuning,
            "muted": self.is_muted(), "mute_until": self.mute_until,
            "event": ({"first": self.event["first"], "last_hit": self.event["last_hit"],
                       "max_count": self.event["max_count"]}
                      if self.event and time.time() - self.event["last_hit"] < self.tuning["event_gap_s"] else None),
            "alarms_24h": self.store.count_alerts(time.time() - 86400),
            "detections_now": [d.to_dict() for d in self.last_dets],
            "last_seen": {display_name(k): v for k, v in self.last_seen.items()},
            "configured": bool(self.s.camera_source.strip()),
            "clip_enabled": self.s.clip_enabled,
            "verify": verifier.resolve_provider(self.s),
            "uptime_s": int(time.time() - self.started),
        }

    def _cmd_status(self, chat: str, args: str) -> str:
        st = self.status()
        cam = "online" if st["camera"]["online"] else f"OFFLINE ({st['camera']['error'] or st['camera']['state']})"
        mute = f"stumm bis {time.strftime('%H:%M', time.localtime(st['mute_until']))}" if st["muted"] else "scharf"
        return (f"Hornet3000 {st['version']}\nKamera: {cam}\nAlarme: {mute}\n"
                f"Alarme (24 h): {st['alarms_24h']}\nErkennung: "
                f"{'aktiv, ' + str(st['detector']['infer_ms']) + ' ms/Bild' if st['detector']['loaded'] else 'KEIN MODELL'}")

    def _cmd_foto(self, chat: str, args: str) -> str | None:
        if not self.live_jpeg:
            return "Noch kein Kamerabild verfügbar."
        self.hub.telegram.send_photo_to(chat, self.live_jpeg,
                                        f"{self.s.camera_name} · {time.strftime('%H:%M:%S')}")
        return None

    def _cmd_mute(self, chat: str, args: str) -> str:
        try:
            minutes = float(args.split()[0]) if args.strip() else 60
        except ValueError:
            minutes = 60
        until = self.mute(minutes)
        return f"Alarme stumm bis {time.strftime('%H:%M', time.localtime(until))}. /laut schaltet wieder scharf."

    def _cmd_unmute(self, chat: str, args: str) -> str:
        self.unmute()
        return "Alarme wieder scharf."
