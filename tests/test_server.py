"""Prüft server/nginx.conf.beispiel an einem ECHT laufenden nginx (Syntax, Kopfzeilen, Methoden, IP-Kürzung, Downloads).

Voraussetzung: nginx und openssl sind installiert. Sonst werden die Tests übersprungen und das steht im Bericht.
Das Zertifikat ist selbstsigniert und nur für diesen Test (TESTSTAND) erzeugt.
"""
from __future__ import annotations

import hashlib
import http.client
import re
import shutil
import socket
import ssl
import subprocess
import time
from pathlib import Path

import pytest

from test_site import ROOT, VERSION, attrappen, fertig  # noqa: F401  (Fixtures wiederverwendet)

NGINX = shutil.which("nginx") or "/usr/sbin/nginx"
pytestmark = pytest.mark.skipif(not Path(NGINX).exists() or not shutil.which("openssl"), reason="nginx/openssl nicht installiert")

HTTP_PORT, HTTPS_PORT = 18080, 18443
DOMAIN = "teststand.invalid"


def freier_port(p: int) -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", p))
    return p


@pytest.fixture(scope="module")
def nginx(fertig, tmp_path_factory):
    tmp = tmp_path_factory.mktemp("nginx")
    freier_port(HTTP_PORT)
    freier_port(HTTPS_PORT)
    key, crt = tmp / "test.key", tmp / "test.crt"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out", str(crt),
                    "-days", "2", "-subj", f"/CN={DOMAIN}"], check=True, capture_output=True)
    conf = (ROOT / "server" / "nginx.conf.beispiel").read_text(encoding="utf-8")
    conf = conf.replace("ihre-domain.de", DOMAIN)
    conf = conf.replace("/etc/letsencrypt/live/" + DOMAIN + "/fullchain.pem", str(crt))
    conf = conf.replace("/etc/letsencrypt/live/" + DOMAIN + "/privkey.pem", str(key))
    conf = conf.replace("/var/www/hornet3000", str(fertig))
    conf = conf.replace("/var/log/nginx/hornet3000-access.log", str(tmp / "access.log"))
    conf = conf.replace("listen 80;", f"listen {HTTP_PORT};").replace("listen [::]:80;", "")
    conf = conf.replace("listen 443 ssl;", f"listen {HTTPS_PORT} ssl;").replace("listen [::]:443 ssl;", "")
    conf = conf.replace(f"return 301 https://{DOMAIN}$request_uri;", f"return 301 https://{DOMAIN}:{HTTPS_PORT}$request_uri;")
    # Nur im Test: die Adresse kommt aus einer Kopfzeile, damit auch IPv6-Fälle prüfbar sind.
    conf = conf.replace("map $remote_addr $ip_gekuerzt", "map $http_x_test_ip $ip_gekuerzt")
    (tmp / "hornet3000.conf").write_text(conf, encoding="utf-8")
    haupt = f"""daemon off;
user root;
pid {tmp}/nginx.pid;
error_log {tmp}/error.log crit;
events {{ worker_connections 64; }}
http {{
    include /etc/nginx/mime.types;
    access_log off;
    client_body_temp_path {tmp}/b; proxy_temp_path {tmp}/p; fastcgi_temp_path {tmp}/f; uwsgi_temp_path {tmp}/u; scgi_temp_path {tmp}/s;
    include {tmp}/hornet3000.conf;
}}
"""
    (tmp / "nginx.conf").write_text(haupt, encoding="utf-8")
    t = subprocess.run([NGINX, "-t", "-c", str(tmp / "nginx.conf"), "-p", str(tmp)], capture_output=True, text=True)
    assert t.returncode == 0, t.stderr
    proc = subprocess.Popen([NGINX, "-c", str(tmp / "nginx.conf"), "-p", str(tmp)], stderr=subprocess.PIPE)
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", HTTP_PORT), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    else:
        proc.kill()
        pytest.fail("nginx startet nicht: " + proc.stderr.read().decode())
    yield {"tmp": tmp, "root": fertig, "log": tmp / "access.log"}
    proc.terminate()
    proc.wait(timeout=10)


def holen(methode: str, pfad: str, https: bool = True, kopf: dict | None = None):
    kopf = {"Host": DOMAIN, **(kopf or {})}
    if https:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE          # selbstsigniertes Testzertifikat
        c = http.client.HTTPSConnection("127.0.0.1", HTTPS_PORT, context=ctx, timeout=10)
    else:
        c = http.client.HTTPConnection("127.0.0.1", HTTP_PORT, timeout=10)
    c.request(methode, pfad, headers=kopf)
    r = c.getresponse()
    body = r.read()
    return r, body


def test_nginx_syntax_ok(nginx):
    assert (nginx["tmp"] / "nginx.pid").exists()


def test_http_leitet_auf_https_um(nginx):
    r, _ = holen("GET", "/impressum.html", https=False)
    assert r.status == 301
    assert r.getheader("Location") == f"https://{DOMAIN}:{HTTPS_PORT}/impressum.html"


def test_kopfzeilen_auf_seiten_fehlerseite_und_downloads(nginx):
    for pfad, status in (("/", 200), ("/impressum.html", 200), ("/gibt-es-nicht.html", 404),
                         (f"/downloads/Hornet3000-Station-{VERSION}.apk", 200)):
        r, _ = holen("GET", pfad)
        assert r.status == status, pfad
        h = {k.lower(): v for k, v in r.getheaders()}
        assert "frame-ancestors 'none'" in h["content-security-policy"] and "default-src 'none'" in h["content-security-policy"], pfad
        assert h["x-content-type-options"] == "nosniff", pfad
        assert h["referrer-policy"] == "no-referrer", pfad
        assert "max-age=31536000" in h["strict-transport-security"], pfad
        assert "camera=()" in h["permissions-policy"], pfad
        assert "set-cookie" not in h, pfad
        assert h["server"] == "nginx", "Versionsnummer darf nicht verraten werden"


def test_csp_header_gleich_csp_meta_der_seiten(nginx):
    r, body = holen("GET", "/")
    meta = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', body.decode()).group(1)
    kopf = r.getheader("Content-Security-Policy")
    for teil in meta.split(";"):
        assert teil.strip() in kopf, teil


def test_fehlerseite_ist_die_eigene_404(nginx):
    r, body = holen("GET", "/gibt-es-nicht.html")
    assert r.status == 404 and b"<h1" in body and "Hornet3000" in body.decode()


def test_nur_lesende_methoden(nginx):
    for m in ("POST", "PUT", "DELETE", "PATCH"):
        r, _ = holen(m, "/")
        assert r.status == 405, m
    r, _ = holen("HEAD", "/")
    assert r.status == 200


def test_versteckte_dateien_und_ordnerlisting_gesperrt(nginx):
    (nginx["root"] / ".geheim").write_text("x")
    r, _ = holen("GET", "/.geheim")
    assert r.status == 404
    r, _ = holen("GET", "/downloads/")
    assert r.status in (403, 404)
    r, _ = holen("GET", "/assets/")
    assert r.status in (403, 404)


def test_download_unveraendert_und_mit_richtigem_typ(nginx):
    for name, typ in ((f"Hornet3000-Station-{VERSION}.apk", "application/vnd.android.package-archive"),
                      (f"Hornet3000-Setup-{VERSION}.exe", "application/octet-stream"),
                      (f"Hornet3000-{VERSION}-macos-arm64.zip", "application/zip"),
                      (f"SHA256SUMS-{VERSION}.txt", "text/plain")):
        r, body = holen("GET", f"/downloads/{name}")
        assert r.status == 200, name
        assert r.getheader("Content-Type").startswith(typ), (name, r.getheader("Content-Type"))
        assert hashlib.sha256(body).digest() == hashlib.sha256((nginx["root"] / "downloads" / name).read_bytes()).digest()


@pytest.mark.parametrize("eingabe,erwartet", [
    ("203.0.113.77", "203.0.113.0"),
    ("10.1.2.3", "10.1.2.0"),
    ("2001:db8:85a3:8d3:1319:8a2e:370:7348", "2001:db8::"),
    ("2001:db8::1", "2001:db8::"),
    ("::ffff:198.51.100.9", "198.51.100.0"),
    ("::1", "unbekannt"),
    ("", "unbekannt"),
    ("kein-ip", "unbekannt"),
])
def test_ip_kuerzung_im_zugriffsprotokoll(nginx, eingabe, erwartet):
    marke = f"/ip-test-{abs(hash((eingabe, 'x')))}"
    holen("GET", marke, https=False, kopf={"X-Test-IP": eingabe})
    time.sleep(0.3)
    zeilen = [z for z in nginx["log"].read_text(encoding="utf-8").splitlines() if marke in z]
    assert zeilen, "kein Protokolleintrag"
    assert zeilen[-1].startswith(erwartet + " - ["), zeilen[-1]
    if eingabe and re.fullmatch(r"[0-9a-fA-F:.]+", eingabe) and eingabe not in ("::1",):
        assert eingabe not in zeilen[-1], "volle Adresse darf nicht im Protokoll stehen"


def test_protokollzeile_enthaelt_nur_genannte_angaben(nginx):
    holen("GET", "/anleitung.html", kopf={"X-Test-IP": "192.0.2.55", "User-Agent": "Testbrowser/1.0", "Cookie": "geheim=1"})
    time.sleep(0.3)
    zeile = [z for z in nginx["log"].read_text(encoding="utf-8").splitlines() if "anleitung.html" in z][-1]
    assert re.fullmatch(r'192\.0\.2\.0 - \[[^\]]+\] "GET /anleitung\.html HTTP/1\.1" 200 \d+ "-" "Testbrowser/1\.0"', zeile), zeile
    assert "geheim" not in zeile
