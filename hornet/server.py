"""Webserver: PWA, JSON-API, Live-Bild (MJPEG), Server-Sent Events, Medien und teilbare Alarm-Seiten."""
from __future__ import annotations

import asyncio
import base64
import html
import io
import json
import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, mesh as mesh_pkg, security
from .config import ROOT, Settings, ensure_access_token, ensure_env_file, ensure_private_dir, parse_env_file
from .detector import YoloOnnx
from .engine import Engine, EventBus
from .notifiers import Hub
from .phonecam import FORMAT_BY_MIME, PhoneCamera
from .setup_wizard import apply_updates, list_devices, probe_camera, read_config, telegram_discover
from .sightings import fetch_sightings
from .store import Store
from .webguard import WebGuard

log = logging.getLogger("hornet.server")
WEB = ROOT / "web"
MEDIA_NAMES = {"snapshot.jpg": "image/jpeg", "clip.mp4": "video/mp4"}


def load_detector(s: Settings) -> tuple[YoloOnnx | None, str]:
    try:
        return YoloOnnx(s.resolve_model(), providers=s.ort_providers or None), ""
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def create_app(s: Settings | None = None, *, start_engine: bool = True, detector: YoloOnnx | None = None,
               load_model: bool = True, env_path: Path | None = None) -> FastAPI:
    s = s or Settings.from_env()
    env_file = ensure_env_file(env_path or ROOT / ".env")
    ensure_access_token(s, env_file)
    ensure_private_dir(s.data_dir)
    store = Store(s.db_path)
    hub = Hub(s, store)
    bus = EventBus()
    model_error = ""
    if detector is None and load_model:
        detector, model_error = load_detector(s)
    engine = Engine(s, store, hub, bus, detector)
    engine.model_error = model_error
    mesh, mesh_problems = mesh_pkg.create_service(s, store, bus=bus, hub=hub, forward_ok=lambda: not engine.is_muted())
    engine.mesh = mesh if mesh.transports else None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if start_engine:
            engine.start()
        yield
        engine.stop()
        store.close()

    app = FastAPI(title="Hornet3000 Alarm", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None,
                  openapi_url=None)
    app.add_middleware(WebGuard, public_url=s.public_url)
    app.state.engine, app.state.store, app.state.hub, app.state.settings = engine, store, hub, s
    app.state.mesh = mesh
    app.state.restart_requested = False
    app.state.shutdown = None  # setzt hornet.cli: beendet den Server, danach wird mit neuer Konfiguration gestartet

    # -- Anmeldung -----------------------------------------------------------------------
    fails: dict[str, list[float]] = defaultdict(list)
    FAILS_MAX_IPS = 2000

    async def body_json(request: Request) -> dict:
        try:
            data = await request.json()
        except Exception:
            raise HTTPException(400, "Ungültige Anfrage (JSON erwartet)") from None
        if not isinstance(data, dict):
            raise HTTPException(400, "Ungültige Anfrage (JSON-Objekt erwartet)")
        return data

    def is_authed(request: Request) -> bool:
        if security.check_session(s.access_token, request.cookies.get("hn_session")):
            return True
        auth = request.headers.get("authorization", "")
        return auth.lower().startswith("bearer ") and security.check_token(s.access_token, auth[7:].strip())

    async def require_auth(request: Request) -> None:
        if not is_authed(request):
            raise HTTPException(401, "Anmeldung erforderlich")

    @app.post("/api/login")
    async def login(request: Request, response: Response):
        ip = request.client.host if request.client else "?"
        now = time.time()
        if len(fails) > FAILS_MAX_IPS:   # Speicher begrenzen: abgelaufene Einträge entfernen, sonst die ältesten
            for k in [k for k, v in fails.items() if not v or now - v[-1] > 600]:
                del fails[k]
            while len(fails) > FAILS_MAX_IPS:
                fails.pop(next(iter(fails)))
        fails[ip] = [t for t in fails[ip] if now - t < 600]
        if len(fails[ip]) >= 10:
            raise HTTPException(429, "Zu viele Versuche – bitte in 10 Minuten erneut probieren")
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        if not security.check_token(s.access_token, str(body.get("token", "")).strip()):
            fails[ip].append(now)
            raise HTTPException(401, "Zugangsschlüssel falsch")
        secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
        response.set_cookie("hn_session", security.session_value(s.access_token), max_age=365 * 86400,
                            httponly=True, samesite="lax", secure=secure, path="/")
        return {"ok": True}

    @app.post("/api/logout")
    async def logout(response: Response):
        response.delete_cookie("hn_session", path="/")
        return {"ok": True}

    @app.get("/api/health")
    async def health():
        return {"ok": True, "version": __version__}

    @app.get("/api/session")
    async def session(request: Request):
        return {"authed": is_authed(request)}

    # -- Status / Live ----------------------------------------------------------------------
    @app.get("/api/status", dependencies=[Depends(require_auth)])
    async def status():
        st = engine.status()
        st["channels"] = hub.status()
        st["apiary_configured"] = bool(s.apiary_lat or s.apiary_lon)
        st["public_url"] = s.public_url
        st["webpush"] = hub.webpush.ready
        st["webpush_hint"] = "" if hub.webpush.ready else "Kontakt-E-Mail unter Einrichtung eintragen (oder https-Adresse der App)"
        st["mesh"] = {"enabled": bool(mesh.transports), "problems": mesh_problems,
                      "transports": [x.status() for x in mesh.transports.values()]}
        st["settings"] = {"alert_classes": s.alert_classes, "protected_classes": s.protected_classes,
                          "clip_pre_s": s.clip_pre_s, "clip_post_s": s.clip_post_s}
        return st

    @app.get("/api/snapshot.jpg", dependencies=[Depends(require_auth)])
    async def snapshot():
        if not engine.live_jpeg:
            raise HTTPException(503, "Noch kein Kamerabild")
        return Response(engine.live_jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.get("/api/live.mjpg", dependencies=[Depends(require_auth)])
    async def live(request: Request):
        async def gen():
            last = 0.0
            while not await request.is_disconnected():
                jpeg, ts = engine.live_jpeg, engine.live_ts
                if jpeg is not None and ts != last:
                    last = ts
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(jpeg)
                           + jpeg + b"\r\n")
                await asyncio.sleep(0.1)
        return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame",
                                 headers={"Cache-Control": "no-store"})

    @app.get("/api/events", dependencies=[Depends(require_auth)])
    async def events(request: Request):
        q = bus.subscribe()

        async def gen():
            try:
                yield "retry: 3000\n\n"
                idle = 0.0
                while not await request.is_disconnected():
                    try:
                        ev, data = q.get_nowait()
                        yield f"event: {ev}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                        idle = 0.0
                    except Exception:
                        await asyncio.sleep(0.25)
                        idle += 0.25
                        if idle >= 15:
                            yield ": ping\n\n"
                            idle = 0.0
            finally:
                bus.unsubscribe(q)
        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    # -- Alarme -------------------------------------------------------------------------
    def public_alert(a: dict) -> dict:
        a = dict(a)
        a["snapshot_url"] = f"/media/{a['id']}/snapshot.jpg" if a.get("snapshot") else None
        a["clip_url"] = f"/media/{a['id']}/clip.mp4" if a.get("clip") else None
        a["share_url"] = engine.share_link(a["id"])
        return a

    @app.get("/api/alerts", dependencies=[Depends(require_auth)])
    async def alerts(limit: int = 50, offset: int = 0):
        rows = store.list_alerts(max(1, min(limit, 200)), max(0, offset))
        return {"items": [public_alert(a) for a in rows]}

    @app.get("/api/alerts/{alert_id}", dependencies=[Depends(require_auth)])
    async def alert_one(alert_id: int):
        a = store.get_alert(alert_id)
        if not a:
            raise HTTPException(404, "Alarm nicht gefunden")
        return public_alert(a)

    @app.post("/api/test-alert", dependencies=[Depends(require_auth)])
    async def test_alert():
        try:
            engine.test_alert_async()
        except RuntimeError as e:
            raise HTTPException(409, str(e))
        return {"ok": True, "detail": "Testalarm läuft – Foto sofort, Video mit Ton nach ca. %d s" % (
            s.clip_post_s + s.segment_s + 3)}

    @app.post("/api/channels/{name}/test", dependencies=[Depends(require_auth)])
    async def channel_test(name: str):
        return await asyncio.to_thread(hub.test_channel, name)

    @app.post("/api/mute", dependencies=[Depends(require_auth)])
    async def mute(request: Request):
        body = await body_json(request)
        minutes = float(body.get("minutes", 60))
        return {"muted": True, "mute_until": engine.mute(min(max(minutes, 1), 60 * 24 * 7))}

    @app.post("/api/unmute", dependencies=[Depends(require_auth)])
    async def unmute():
        engine.unmute()
        return {"muted": False}

    @app.get("/api/tuning", dependencies=[Depends(require_auth)])
    async def tuning_get():
        return engine.tuning

    @app.put("/api/tuning", dependencies=[Depends(require_auth)])
    async def tuning_put(request: Request):
        body = await body_json(request)
        return engine.set_tuning(conf_alert=body.get("conf_alert"), confirm_hits=body.get("confirm_hits"),
                                 event_gap_s=body.get("event_gap_s"))

    # -- Web-Push -------------------------------------------------------------------------
    @app.get("/api/push/key", dependencies=[Depends(require_auth)])
    async def push_key():
        if not hub.webpush.ready:
            raise HTTPException(503, "Web-Push nicht eingerichtet: Kontakt-E-Mail fehlt (Einrichtung)")
        return {"key": hub.webpush.public_key}

    @app.post("/api/push/subscribe", dependencies=[Depends(require_auth)])
    async def push_sub(request: Request):
        sub = await body_json(request)
        if not isinstance(sub, dict) or not str(sub.get("endpoint", "")).startswith("https://") or "keys" not in sub:
            raise HTTPException(400, "Ungültiges Push-Abo")
        store.push_add(sub)
        return {"ok": True, "devices": len(store.push_list())}

    @app.post("/api/push/unsubscribe", dependencies=[Depends(require_auth)])
    async def push_unsub(request: Request):
        body = await body_json(request)
        store.push_remove(str(body.get("endpoint", "")))
        return {"ok": True}

    # -- Sichtungen (GBIF) ---------------------------------------------------------------------
    @app.get("/api/sightings", dependencies=[Depends(require_auth)])
    async def sightings(refresh: bool = False):
        return await asyncio.to_thread(fetch_sightings, s, store, refresh)


    # -- Funknetz --------------------------------------------------------------------------------------
    @app.get("/api/mesh", dependencies=[Depends(require_auth)])
    async def mesh_state():
        st = mesh.status()
        st["problems"] = mesh_problems
        rows = store.mesh_list(60)
        acks = store.mesh_ack_counts([r["ident"] for r in rows if r["direction"] == "out"])
        for r in rows:
            r["acks"] = acks.get(r["ident"], 0) if r["direction"] == "out" else None
        st["messages"] = rows
        return st

    @app.get("/api/mesh/messages", dependencies=[Depends(require_auth)])
    async def mesh_messages(limit: int = 100, offset: int = 0, direction: str = ""):
        return store.mesh_list(limit, offset, direction or None)

    @app.post("/api/mesh/test", dependencies=[Depends(require_auth)])
    async def mesh_test():
        if not mesh.transports:
            raise HTTPException(409, "Kein Funkweg eingeschaltet (Einrichtung → Funknetz)")
        ident = await asyncio.to_thread(mesh.send_test)
        return {"ok": True, "ident": ident}

    @app.get("/api/mesh/lora/ports", dependencies=[Depends(require_auth)])
    async def mesh_ports():
        def scan():
            from serial.tools import list_ports
            return [{"device": p.device, "name": p.description or "", "usb": f"{p.vid:04x}:{p.pid:04x}" if p.vid else ""}
                    for p in list_ports.comports()]
        try:
            return await asyncio.to_thread(scan)
        except Exception as e:
            raise HTTPException(500, f"Anschlüsse konnten nicht gelistet werden: {e}")

    @app.post("/api/mesh/freenet/invite", dependencies=[Depends(require_auth)])
    async def mesh_invite(request: Request):
        from .mesh.freenet import accept_invite
        from .mesh.transport import TransportError
        body = await body_json(request)
        try:
            out = await asyncio.to_thread(accept_invite, s.mesh_freenet_riverctl, str(body.get("code", "")),
                                          s.mesh_freenet_node, s.data_dir / "river", str(body.get("nickname", "")))
        except ValueError as e:
            raise HTTPException(400, str(e))
        except (TransportError, OSError) as e:
            raise HTTPException(502, str(e))
        return {"ok": True, "output": out}

    # -- Einrichtung -------------------------------------------------------------------------------
    @app.get("/api/setup", dependencies=[Depends(require_auth)])
    async def setup_get():
        cfg = read_config(env_file)
        cfg["can_restart"] = app.state.shutdown is not None
        cfg["configured"] = bool(s.camera_source.strip())
        return cfg

    @app.put("/api/setup", dependencies=[Depends(require_auth)])
    async def setup_put(request: Request):
        body = await body_json(request)
        try:
            vals = body.get("values", {})
            if not isinstance(vals, dict):
                raise ValueError("Ungültige Einstellungen")
            changed = await asyncio.to_thread(apply_updates, env_file, vals)
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"changed": changed, "restart_required": bool(changed)}

    @app.post("/api/setup/camera-test", dependencies=[Depends(require_auth)])
    async def setup_camera(request: Request):
        body = await body_json(request)
        try:
            return await asyncio.to_thread(probe_camera, str(body.get("source", "")), str(body.get("audio_device", "")), s.ffmpeg_bin)
        except ValueError as e:
            raise HTTPException(400, str(e))
        except RuntimeError as e:  # ffmpeg fehlt
            raise HTTPException(500, str(e))

    @app.get("/api/setup/devices", dependencies=[Depends(require_auth)])
    async def setup_devices():
        try:
            return await asyncio.to_thread(list_devices, s.ffmpeg_bin)
        except Exception as e:
            raise HTTPException(500, f"Geräte konnten nicht gelistet werden: {e}")

    @app.post("/api/setup/telegram", dependencies=[Depends(require_auth)])
    async def setup_telegram(request: Request):
        body = await body_json(request)
        token = str(body.get("token", "")).strip() or parse_env_file(env_file).get("TELEGRAM_BOT_TOKEN", "")
        return await asyncio.to_thread(telegram_discover, token, s.telegram_api_base)

    @app.post("/api/setup/restart", dependencies=[Depends(require_auth)])
    async def setup_restart():
        if app.state.shutdown is None:
            raise HTTPException(501, "Neustart nur im normalen Programmbetrieb möglich – Programm bitte selbst neu starten")
        app.state.restart_requested = True
        asyncio.get_running_loop().call_later(0.6, app.state.shutdown)
        return {"ok": True}

    @app.get("/api/setup/phone-pair", dependencies=[Depends(require_auth)])
    async def phone_pair():
        if not s.public_url.startswith("https://"):
            return {"ready": False,
                    "reason": "Dafür muss „Adresse der App“ mit https:// beginnen (siehe Einrichtung) – "
                              "sonst kann das Handy keine sichere Verbindung aufbauen und Kamera/Mikrofon verweigern."}
        url = f"{s.public_url}/phone?t={s.access_token}"
        import qrcode
        qr = qrcode.QRCode(border=2)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return {"ready": True, "url": url, "qr_png_base64": base64.b64encode(buf.getvalue()).decode("ascii")}

    # -- Medien und teilbare Seite ---------------------------------------------------------------
    def media_ok(request: Request, alert_id: int) -> bool:
        if is_authed(request):
            return True
        q = request.query_params
        return security.verify_alert(s.access_token, alert_id, q.get("e"), q.get("s"))

    @app.get("/media/{alert_id}/{name}")
    async def media(alert_id: int, name: str, request: Request):
        if name not in MEDIA_NAMES:
            raise HTTPException(404)
        if not media_ok(request, alert_id):
            raise HTTPException(401, "Nicht berechtigt")
        p = s.alerts_dir / str(alert_id) / name
        if not p.is_file():
            raise HTTPException(404, "Datei nicht (mehr) vorhanden")
        return FileResponse(p, media_type=MEDIA_NAMES[name], headers={"Cache-Control": "private, max-age=3600"})

    @app.get("/share/{alert_id}", response_class=HTMLResponse)
    async def share(alert_id: int, request: Request):
        if not media_ok(request, alert_id):
            return HTMLResponse("<h1>Link abgelaufen</h1><p>Bitte in der App anmelden.</p>", status_code=401)
        a = store.get_alert(alert_id)
        if not a:
            raise HTTPException(404)
        q = f"?e={html.escape(request.query_params.get('e', ''))}&s={html.escape(request.query_params.get('s', ''))}"
        when = time.strftime("%d.%m.%Y %H:%M:%S", time.localtime(a["ts"]))
        clip = (f'<video controls playsinline preload="auto" src="/media/{alert_id}/clip.mp4{q}"></video>'
                if a.get("clip") else
                '<p class="hint">Das Video mit Ton wird noch erstellt – Seite in einigen Sekunden neu laden.</p>')
        refresh = '<meta http-equiv="refresh" content="8">' if (not a.get("clip") and time.time() - a["ts"] < 120) else ""
        page = f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Hornissen-Alarm {alert_id}</title>{refresh}
<link rel="stylesheet" href="/assets/share.css"></head><body><main>
<h1>{html.escape(a.get('label') or 'Alarm')} – {html.escape(a.get('camera') or '')}</h1>
<small>{when} · {a.get('count') or 1} Tier(e) · Sicherheit {int((a.get('conf') or 0) * 100)} %</small>
<img alt="Foto" src="/media/{alert_id}/snapshot.jpg{q}">{clip}
<p class="hint">Bitte Art am Foto bestätigen und nicht selbst bekämpfen – die Europäische Hornisse ist geschützt.</p>
</main></body></html>"""
        return HTMLResponse(page, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})

    # -- Handy als Kamera: Seite + Live-Übertragung -----------------------------------------------
    @app.get("/phone", include_in_schema=False)
    async def phone_page():
        # Keine Auth-Abhängigkeit auf Routenebene: die Seite selbst verlangt per JS die Anmeldung
        # (Zugangsschlüssel aus dem ?t=-Link), damit ein noch nicht angemeldetes Handy die Login-Maske sieht.
        return FileResponse(WEB / "phone.html", headers={"Cache-Control": "no-cache"})

    @app.websocket("/ws/phone")
    async def ws_phone(websocket: WebSocket):
        if not security.check_session(s.access_token, websocket.cookies.get("hn_session")):
            await websocket.close(code=4401)
            return
        cam = engine.camera
        if not isinstance(cam, PhoneCamera):
            await websocket.close(code=4409)
            return
        await websocket.accept()
        session = None
        try:
            init = await websocket.receive_json()
            if not isinstance(init, dict):
                await websocket.close(code=1003)
                return
            mime = str(init.get("mimeType", ""))
            device = str(init.get("device", ""))
            try:
                session = cam.attach(mime, device)
            except ValueError as e:
                await websocket.send_json({"error": str(e)})
                await websocket.close(code=1003)
                return
            while True:
                data = await websocket.receive_bytes()
                if not cam.write(session, data):
                    break
        except WebSocketDisconnect:
            pass
        except Exception:
            log.exception("Fehler bei der Handy-Kamera-Übertragung")
        finally:
            if session is not None:
                cam.detach(session)

    # -- PWA-Dateien --------------------------------------------------------------------------------
    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/sw.js", include_in_schema=False)
    async def sw():
        return FileResponse(WEB / "sw.js", media_type="text/javascript",
                            headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})

    @app.get("/manifest.webmanifest", include_in_schema=False)
    async def manifest():
        return FileResponse(WEB / "manifest.webmanifest", media_type="application/manifest+json")

    (WEB / "assets").mkdir(parents=True, exist_ok=True)
    app.mount("/assets", StaticFiles(directory=str(WEB / "assets")), name="assets")
    return app
