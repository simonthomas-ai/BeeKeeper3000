"""Optionale zweite Prüfung durch eine Bild-KI (Claude oder lokales Ollama-Modell).

Wichtig: Die Prüfung kann einen Alarm nur *einordnen* (bestätigt / widerspricht / unklar) – sie unterdrückt
ihn nie. Ein verpasster Alarm ist bei Vespa velutina teurer als ein Fehlalarm.
"""
from __future__ import annotations

import base64
import json
import re
from dataclasses import asdict, dataclass

import httpx

from .config import Settings

SYSTEM = (
    "Du bist Entomologe und hilfst einem Imker in Deutschland, Vespa velutina (Asiatische Hornisse) sicher von "
    "Vespa crabro (Europäische Hornisse, streng geschützt), Wespen, Bienen und Schwebfliegen zu unterscheiden. "
    "Urteile nur nach sichtbaren Merkmalen und gib 'unklar' an, wenn das Bild nicht ausreicht."
)

PROMPT = (
    "Eine Kamera am Flugloch eines Bienenstocks hat ein Insekt aufgenommen; ein lokales Erkennungsmodell meldet "
    "'Vespa velutina'. Bild 1 ist ein Ausschnitt um das Tier, Bild 2 das Gesamtbild.\n"
    "Merkmale zur Orientierung: V. velutina – Brust und Kopfoberseite schwarzbraun, Beinenden gelb, Hinterleib "
    "überwiegend dunkel mit orange-gelbem Bereich hinten, Gesicht orange, kleiner als V. crabro. "
    "V. crabro – Kopf/Brust/Beine rotbraun, Hinterleib gelb mit dunkler Zeichnung, Gesicht gelb, größer.\n"
    "Antworte AUSSCHLIESSLICH mit einem JSON-Objekt ohne weiteren Text:\n"
    '{"art": "velutina" | "crabro" | "andere_wespe" | "biene" | "anderes_insekt" | "unklar", '
    '"sicherheit": Zahl 0.0-1.0, "merkmale": "kurze Begründung auf Deutsch, max. 25 Wörter"}'
)

VALID = {"velutina", "crabro", "andere_wespe", "biene", "anderes_insekt", "unklar"}


@dataclass
class Verdict:
    art: str = "nicht_geprueft"
    sicherheit: float = 0.0
    merkmale: str = ""
    provider: str = "none"
    model: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def contradicts(self) -> bool:
        """Prüfung widerspricht klar der Meldung 'Vespa velutina'."""
        return self.art in ("crabro", "andere_wespe", "biene", "anderes_insekt") and self.sicherheit >= 0.8

    @property
    def confirms(self) -> bool:
        return self.art == "velutina" and self.sicherheit >= 0.6


def resolve_provider(s: Settings) -> str:
    p = s.verify_provider
    if p == "auto":
        return "anthropic" if s.anthropic_api_key else "none"
    return p if p in ("none", "anthropic", "ollama") else "none"


def _parse(text: str) -> tuple[str, float, str]:
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        raise ValueError("keine JSON-Antwort")
    d = json.loads(m.group(0))
    art = str(d.get("art", "unklar")).strip().lower()
    if art not in VALID:
        art = "unklar"
    try:
        conf = float(d.get("sicherheit", 0))
    except (TypeError, ValueError):
        conf = 0.0
    return art, max(0.0, min(1.0, conf)), str(d.get("merkmale", ""))[:300]


def verify(s: Settings, crop_jpeg: bytes, full_jpeg: bytes) -> Verdict:
    provider = resolve_provider(s)
    if provider == "none":
        return Verdict()
    b64 = [base64.b64encode(crop_jpeg).decode(), base64.b64encode(full_jpeg).decode()]
    try:
        if provider == "anthropic":
            content = [
                {"type": "text", "text": "Bild 1 (Ausschnitt):"},
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64[0]}},
                {"type": "text", "text": "Bild 2 (Gesamtbild):"},
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64[1]}},
                {"type": "text", "text": PROMPT},
            ]
            r = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": s.anthropic_api_key, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": s.verify_model, "max_tokens": 300, "system": SYSTEM,
                      "messages": [{"role": "user", "content": content}]},
                timeout=s.verify_timeout_s)
            r.raise_for_status()
            text = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
            model = s.verify_model
        else:  # ollama
            r = httpx.post(
                f"{s.ollama_url}/api/chat",
                json={"model": s.ollama_model, "stream": False, "format": "json",
                      "messages": [{"role": "system", "content": SYSTEM},
                                   {"role": "user", "content": PROMPT, "images": b64}]},
                timeout=s.verify_timeout_s)
            r.raise_for_status()
            text = r.json().get("message", {}).get("content", "")
            model = s.ollama_model
        art, conf, why = _parse(text)
        return Verdict(art, conf, why, provider, model)
    except Exception as e:  # Fail-open: Alarm wird trotzdem gesendet
        return Verdict(art="fehler", provider=provider, error=f"{type(e).__name__}: {str(e)[:160]}")
