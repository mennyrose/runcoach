"""בניית מסלול מעגלי מישורי דרך OpenRouteService."""
import math
import os

import gpxpy
import gpxpy.gpx
import requests

ORS = "https://api.openrouteservice.org"
UA = {"User-Agent": "runcoach-personal/1.0"}


def geocode(address: str):
    r = requests.get("https://nominatim.openstreetmap.org/search",
                     params={"q": address, "format": "json", "limit": 1, "accept-language": "he"},
                     headers=UA, timeout=20)
    r.raise_for_status()
    data = r.json()
    if not data:
        raise ValueError(f"לא נמצאה כתובת: {address}")
    return float(data[0]["lat"]), float(data[0]["lon"])


def _ascent(coords):
    up = 0.0
    for a, b in zip(coords, coords[1:]):
        if len(a) > 2 and len(b) > 2 and b[2] > a[2]:
            up += b[2] - a[2]
    return up


def _round_trip(lat, lon, meters, seed, profile):
    r = requests.post(
        f"{ORS}/v2/directions/{profile}/geojson",
        headers={"Authorization": os.environ["ORS_API_KEY"], **UA},
        json={"coordinates": [[lon, lat]], "elevation": True,
              "options": {"round_trip": {"length": meters, "points": 3, "seed": seed}}},
        timeout=60)
    r.raise_for_status()
    f = r.json()["features"][0]
    coords = f["geometry"]["coordinates"]
    return {"coords": coords, "meters": f["properties"]["summary"]["distance"],
            "ascent": _ascent(coords), "seed": seed}


def build_route(lat, lon, target_m, allow_hills=False, attempts=6, profile="foot-walking"):
    """מנסה כמה seeds; ברירת מחדל בוחר את המסלול הכי מישורי שקרוב לאורך המבוקש."""
    cands = []
    for seed in range(attempts):
        try:
            cands.append(_round_trip(lat, lon, target_m, seed, profile))
        except requests.HTTPError:
            continue
    if not cands:
        raise RuntimeError("OpenRouteService לא החזיר מסלול (בדוק מפתח/מכסה)")

    def score(c):
        length_err = abs(c["meters"] - target_m) / target_m
        hill = c["ascent"] / max(c["meters"], 1) * 100  # מטר עלייה לכל 100 מ'
        return length_err * 10 + (-hill if allow_hills else hill)

    return min(cands, key=score)


def to_gpx(coords, name):
    gpx = gpxpy.gpx.GPX()
    trk = gpxpy.gpx.GPXTrack(name=name)
    seg = gpxpy.gpx.GPXTrackSegment()
    for c in coords:
        seg.points.append(gpxpy.gpx.GPXTrackPoint(latitude=c[1], longitude=c[0],
                                                  elevation=c[2] if len(c) > 2 else None))
    trk.segments.append(seg)
    gpx.tracks.append(trk)
    return gpx.to_xml()
