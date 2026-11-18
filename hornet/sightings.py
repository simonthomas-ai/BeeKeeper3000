# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
"""Sichtungen der Asiatischen Hornisse in der Umgebung des Bienenstands aus GBIF (offene Biodiversitätsdaten).

GBIF bündelt u. a. iNaturalist, observation.org und weitere Meldeportale. Die Abfrage braucht keinen Schlüssel.
Ergebnisse werden 6 Stunden zwischengespeichert und für die Offline-Anzeige in der Datenbank abgelegt.
"""
from __future__ import annotations

import math
import time
from datetime import date

import httpx

from .config import Settings
from .store import Store

_CACHE: dict = {"ts": 0.0, "key": None, "data": None}


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def fetch_sightings(s: Settings, store: Store | None = None, force: bool = False) -> dict:
    if not (s.apiary_lat or s.apiary_lon):
        return {"configured": False, "items": [], "note": "APIARY_LAT/APIARY_LON in der .env setzen"}
    key = (s.apiary_lat, s.apiary_lon, s.sightings_radius_km)
    if not force and _CACHE["key"] == key and time.time() - _CACHE["ts"] < 6 * 3600 and _CACHE["data"]:
        return _CACHE["data"]

    rad = s.sightings_radius_km
    dlat = rad / 111.0
    dlon = rad / (111.0 * max(0.2, math.cos(math.radians(s.apiary_lat))))
    year = date.today().year
    params = {
        "scientificName": "Vespa velutina",
        "hasCoordinate": "true",
        "decimalLatitude": f"{s.apiary_lat - dlat:.4f},{s.apiary_lat + dlat:.4f}",
        "decimalLongitude": f"{s.apiary_lon - dlon:.4f},{s.apiary_lon + dlon:.4f}",
        "year": f"{year - 1},{year}",
        "limit": 300,
    }
    try:
        r = httpx.get(f"{s.gbif_base}/occurrence/search", params=params, timeout=25)
        r.raise_for_status()
        j = r.json()
        items = []
        for o in j.get("results", []):
            lat, lon = o.get("decimalLatitude"), o.get("decimalLongitude")
            if lat is None or lon is None:
                continue
            dist = _haversine(s.apiary_lat, s.apiary_lon, lat, lon)
            if dist > rad:
                continue
            items.append({
                "date": (o.get("eventDate") or "")[:10],
                "km": round(dist, 1),
                "place": ", ".join(x for x in (o.get("locality"), o.get("municipality") or o.get("county"),
                                               o.get("stateProvince")) if x)[:120],
                "source": o.get("datasetName") or o.get("institutionCode") or "",
                "url": f"https://www.gbif.org/occurrence/{o.get('key')}",
            })
        items.sort(key=lambda x: (x["date"], -x["km"]), reverse=True)
        data = {"configured": True, "items": items[:40], "total": len(items), "radius_km": rad,
                "fetched": time.time(), "count_gbif": j.get("count", 0), "offline": False}
        _CACHE.update(ts=time.time(), key=key, data=data)
        if store:
            store.kv_set("sightings_cache", data)
        return data
    except Exception as e:
        cached = store.kv_get("sightings_cache") if store else None
        if cached:
            cached = dict(cached, offline=True, note=f"Offline – Stand {time.strftime('%d.%m.%Y %H:%M', time.localtime(cached.get('fetched', 0)))}")
            return cached
        return {"configured": True, "items": [], "error": f"GBIF nicht erreichbar ({type(e).__name__})"}
