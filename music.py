"""רשימת השמעה לפי שלבי האימון. Claude מציע שירים עם BPM, Spotify מאתר ויוצר פלייליסט."""
import json
import os
import random

import spotipy
from spotipy.cache_handler import CacheHandler
from spotipy.oauth2 import SpotifyPKCE
from concurrent.futures import ThreadPoolExecutor

import planner

PROMPT = """הצע שירים כדי לבנות פלייליסט ריצה. סגנון: {genres}.
החזר JSON בלבד: {{"walk": [...], "run": [...]}} כשכל פריט {{"title": "...", "artist": "...", "bpm": מספר}}.
walk = שירים לקצב הליכה מהירה (כ-115-130 BPM), run = שירים לריצה (כ-150-175 BPM, או 75-88 בהכפלה).
25 שירים בכל קטגוריה, שירים אמיתיים שקיימים ב-Spotify, בלי כפילויות."""


RUN_ARTISTS = ["Noa Kirel", "Netta", "Static & Ben El", "Tuna", "Ness & Stila", "Eden Hason",
               "Roni Dalumi", "Omer Adam", "Ravid Plotnik", "Hanan Ben Ari"]
WALK_ARTISTS = ["Omer Adam", "Eden Ben Zaken", "Sarit Hadad", "Moshe Peretz", "Eyal Golan",
                "Shlomi Shabat", "Ninet Tayeb", "Mosh Ben Ari", "Ofra Haza", "Kobi Peretz"]


def suggest(genres: str) -> dict:
    """עם מפתח Anthropic: שירים לפי BPM. בלי מפתח: חיפוש ב-Spotify (אמנים ישראליים קצביים, או לפי הסגנון)."""
    if os.getenv("ANTHROPIC_API_KEY"):
        import anthropic
        msg = anthropic.Anthropic().messages.create(
            model="claude-sonnet-5-5", max_tokens=4000,
            messages=[{"role": "user", "content": PROMPT.format(genres=genres)}])
        raw = msg.content[0].text
        return json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    if "ישראל" in genres or "עברי" in genres:
        return {"run": [{"q": f"artist:{a}"} for a in RUN_ARTISTS],
                "walk": [{"q": f"artist:{a}"} for a in WALK_ARTISTS]}
    return {"run": [{"q": f"{genres} running"}, {"q": f"{genres} workout"}, {"q": f"{genres} energy"}],
            "walk": [{"q": f"{genres} walking"}, {"q": f"{genres} happy"}, {"q": f"{genres} upbeat"}]}


import storage


class StoreCache(CacheHandler):
    def get_cached_token(self):
        return storage.get("spotify_token")

    def save_token_to_cache(self, token_info):
        storage.set("spotify_token", token_info)


_auth = None


def auth():
    """OAuth PKCE של Spotify: דורש רק Client ID (בלי secret). אותו אובייקט משמש ל-login ול-callback."""
    global _auth
    cid = os.getenv("SPOTIPY_CLIENT_ID")
    if _auth is None or _auth.client_id != cid:
        _auth = SpotifyPKCE(
            client_id=cid, scope="playlist-modify-private", cache_handler=StoreCache(), open_browser=False,
            redirect_uri=os.getenv("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:5000/callback"))
    return _auth


def is_connected() -> bool:
    try:
        return bool(auth().cache_handler.get_cached_token())
    except Exception:
        return False


def sp():
    if not is_connected():
        raise RuntimeError("Spotify לא מחובר – לחץ על 'חבר Spotify'")
    return spotipy.Spotify(auth_manager=auth())


def _track(t, bpm=None):
    return {"uri": t["uri"], "title": t["name"], "artist": t["artists"][0]["name"],
            "seconds": t["duration_ms"] // 1000, "bpm": bpm}


def _resolve_one(client, it):
    if "q" in it:  # חיפוש חופשי: עד 4 שירים באורך סביר
        res = client.search(q=it["q"], type="track", limit=10, market="IL")["tracks"]["items"]
        return [_track(t) for t in res if 120_000 <= t["duration_ms"] <= 300_000][:4]
    res = client.search(q=f'{it["title"]} {it["artist"]}', type="track", limit=1,
                        market="IL")["tracks"]["items"]
    return [_track(res[0], it.get("bpm"))] if res else []


def resolve(client, items):
    with ThreadPoolExecutor(8) as ex:
        results = list(ex.map(lambda it: _resolve_one(client, it), items))
    out, seen = [], set()
    for found in results:
        for t in found:
            if t["uri"] not in seen:
                seen.add(t["uri"])
                out.append(t)
    return out


def assemble(blocks, pools):
    """ממלא כל שלב בשירים מהמאגר המתאים עד שמכסים את משך השלב."""
    pools = {k: random.sample(v, len(v)) for k, v in pools.items()}
    used = {"walk": 0, "run": 0}
    playlist, t, end = [], 0, 0
    for kind, secs in planner.phases(blocks):
        end += secs
        pool = pools[kind]
        while t < end and pool:
            song = pool[used[kind] % len(pool)]
            used[kind] += 1
            playlist.append({**song, "kind": kind})
            t += song["seconds"]
    return playlist


def create_playlist(client, name, tracks):
    """Spotify העבירו יצירת פלייליסט ל-/me/playlists והוספת שירים ל-/items; ננסה גם את הנתיבים הישנים."""
    body = {"name": name, "public": False, "description": "נוצר אוטומטית ע\"י RunCoach"}
    try:
        pl = client._post("me/playlists", payload=body)
    except spotipy.SpotifyException:
        pl = client.user_playlist_create(client.current_user()["id"], name, public=False,
                                         description=body["description"])
    uris = [t["uri"] for t in tracks]
    for i in range(0, len(uris), 100):
        chunk = uris[i:i + 100]
        try:
            client._post(f"playlists/{pl['id']}/items", payload={"uris": chunk})
        except spotipy.SpotifyException:
            client.playlist_add_items(pl["id"], chunk)
    return pl["external_urls"]["spotify"]
