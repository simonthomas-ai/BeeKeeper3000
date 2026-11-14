"""Statische Prüfung der Oberfläche: alles, was verlinkt ist, existiert; nichts, was die strenge CSP sperren würde."""
import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "web"
PAGES = [p for p in WEB.glob("*.html")] + [WEB / "assets" / "knowledge.html"]


def _local(ref: str) -> Path | None:
    ref = ref.split("#")[0].split("?")[0]
    if not ref.startswith("/") or ref.startswith("//") or ref in ("/", ""):
        return None
    if ref.startswith(("/api/", "/share/", "/media/", "/phone", "/mobil/")):
        return None
    return WEB / ref.lstrip("/")


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_pages_have_no_inline_script_style_or_handlers(page):
    t = page.read_text(encoding="utf-8")
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>\s*\S", t), "Inline-<script> wird von der CSP gesperrt"
    assert "<style" not in t, "<style>-Block wird von der CSP gesperrt"
    assert not re.search(r"\sstyle\s*=", t), "style=-Attribut wird von der CSP gesperrt"
    assert not re.search(r"\son[a-z]+\s*=", t), "Inline-Ereignis (onclick …) wird von der CSP gesperrt"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_pages_reference_only_existing_local_files(page):
    t = page.read_text(encoding="utf-8")
    for tag in re.findall(r"<(?:script|img|link|iframe|source|video|audio|embed|object)\b[^>]*>", t):
        for ref in re.findall(r'(?:src|href)="([^"]+)"', tag):
            assert not ref.startswith(("http://", "https://", "//")), f"{page.name}: externe Ressource {ref}"
    for ref in re.findall(r'(?:src|href)="([^"]+)"', t):
        p = _local(ref)
        if p is not None:
            assert p.exists(), f"{page.name}: {ref} fehlt"


@pytest.mark.parametrize("css", sorted((WEB / "assets").glob("*.css")), ids=lambda p: p.name)
def test_css_urls_exist_and_are_local(css):
    t = css.read_text(encoding="utf-8")
    for ref in re.findall(r"url\(\s*[\"']?([^)\"']+)", t):
        if ref.startswith("data:"):
            continue
        assert not ref.startswith(("http://", "https://", "//")), f"externe Ressource {ref}"
        p = _local(ref)
        assert p is not None and p.exists(), f"{css.name}: {ref} fehlt"


def test_service_worker_shell_exists():
    t = (WEB / "sw.js").read_text(encoding="utf-8")
    shell = re.search(r"SHELL\s*=\s*\[(.*?)\]", t, re.S).group(1)
    refs = re.findall(r"'([^']+)'", shell)
    assert refs
    for ref in refs:
        p = _local(ref)
        if p is not None:
            assert p.exists(), f"sw.js: {ref} fehlt"


def test_scripts_do_not_write_inline_style_attributes_or_html():
    for js in (WEB / "assets").glob("*.js"):
        t = js.read_text(encoding="utf-8")
        assert not re.search(r"\.innerHTML\s*=", t), f"{js.name}: innerHTML"
        assert not re.search(r"""setAttribute\(\s*['"]style['"]""", t), f"{js.name}: setAttribute('style')"
        assert not re.search(r"""\bstyle\s*:\s*['"]""", t), f"{js.name}: style: '…' (Inline-Attribut)"
        assert "eval(" not in t and "new Function(" not in t
