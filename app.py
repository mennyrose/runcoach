import datetime as dt
import hashlib
import os
import secrets

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session
from werkzeug.middleware.proxy_fix import ProxyFix

load_dotenv()
import garmin_io, music, planner, route, storage  # noqa: E402

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
APP_PASSWORD = os.getenv("APP_PASSWORD")
# מפתח ה-session נגזר מהסיסמה, כך שאין צורך להגדיר עוד משתנה בענן
app.secret_key = os.getenv("SECRET_KEY") or hashlib.sha256(
    ("runcoach|" + (APP_PASSWORD or secrets.token_hex(16))).encode()).hexdigest()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  SESSION_COOKIE_SECURE=storage.IN_CLOUD, PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 90)
DEFAULT_ADDRESS = os.getenv("DEFAULT_ADDRESS", "טרומפלדור 4, קרית אתא")
_settings_loaded = False


def load_settings():
    """הגדרות שנשמרו מהדף (Client ID, מפתח מסלולים). משתני סביבה קודמים להן."""
    global _settings_loaded
    if _settings_loaded:
        return
    for k, v in (storage.get("settings") or {}).items():
        os.environ.setdefault(k, v)
    _settings_loaded = True


def save_setting(key, value):
    cur = storage.get("settings") or {}
    cur[key] = value
    storage.set("settings", cur)
    os.environ[key] = value


LOGIN_HTML = """<!doctype html><html lang=he dir=rtl><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>RunCoach</title>
<body style="font:16px system-ui;background:#f2f5f4;display:grid;place-items:center;min-height:100vh;margin:0">
<form method=post style="background:#fff;padding:24px;border-radius:18px;width:min(340px,90vw)">
<h2 style="margin-top:0">RunCoach</h2><input type=password name=password placeholder="סיסמה" autofocus
style="width:100%;font-size:16px;padding:12px;border:1.5px solid #ccd;border-radius:12px">
<button style="width:100%;margin-top:12px;padding:13px;border:0;border-radius:12px;background:#0f766e;color:#fff;font-size:16px;font-weight:700">כניסה</button>
{err}</form></body></html>"""


@app.before_request
def gate():
    if storage.IN_CLOUD and not APP_PASSWORD:
        return "APP_PASSWORD לא מוגדר – השרת נעול", 503
    if APP_PASSWORD and not session.get("ok") and request.path != "/login":
        if request.path.startswith("/api/"):
            return jsonify(error="לא מחובר"), 401
        return redirect("/login")
    try:
        load_settings()
    except Exception as e:  # אחסון לא מוגדר: הדף עדיין צריך להיטען
        print("settings:", e)
    return None


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if APP_PASSWORD and secrets.compare_digest(request.form.get("password", ""), APP_PASSWORD):
            session.permanent = True
            session["ok"] = True
            return redirect("/")
        return LOGIN_HTML.format(err='<p style="color:#b91c1c">סיסמה שגויה</p>'), 401
    return LOGIN_HTML.format(err="")


@app.get("/")
def index():
    return render_template("index.html", default_address=DEFAULT_ADDRESS,
                           today=dt.date.today().isoformat())


@app.get("/api/status")
def status():
    try:
        return jsonify(spotify=music.is_connected(), garmin=garmin_io.is_connected(),
                       spotify_configured=bool(os.getenv("SPOTIPY_CLIENT_ID")),
                       ors=bool(os.getenv("ORS_API_KEY")), storage=True)
    except Exception as e:
        return jsonify(spotify=False, garmin=False, spotify_configured=False,
                       ors=bool(os.getenv("ORS_API_KEY")), storage=False, error=str(e))


@app.post("/api/spotify/setup")
def spotify_setup():
    cid = (request.json.get("client_id") or "").strip()
    if len(cid) < 20:
        return jsonify(error="Client ID לא נראה תקין"), 400
    save_setting("SPOTIPY_CLIENT_ID", cid)
    return jsonify(ok=True)


@app.post("/api/ors/setup")
def ors_setup():
    key = (request.json.get("key") or "").strip()
    if len(key) < 20:
        return jsonify(error="המפתח לא נראה תקין"), 400
    save_setting("ORS_API_KEY", key)
    return jsonify(ok=True)


@app.get("/spotify/login")
def spotify_login():
    if not os.getenv("SPOTIPY_CLIENT_ID"):
        return redirect("/?spotify_setup=1")
    a = music.auth(request.url_root + "callback")
    url = a.get_authorize_url()
    storage.set("spotify_pkce", {"v": a.code_verifier, "c": a.code_challenge})  # שורד בין בקשות
    return redirect(url)


@app.get("/callback")
def spotify_callback():
    code = request.args.get("code")
    if code:
        a = music.auth(request.url_root + "callback")
        p = storage.get("spotify_pkce") or {}
        a.code_verifier, a.code_challenge = p.get("v"), p.get("c")
        a.get_access_token(code, check_cache=False)
    return redirect("/")


@app.post("/api/garmin/connect")
def garmin_connect():
    d = request.json
    try:
        return jsonify(garmin_io.connect(d.get("email", ""), d.get("password", ""), d.get("mfa") or None))
    except Exception as e:
        return jsonify(error=str(e)), 400


@app.post("/api/garmin/tokens")
def garmin_tokens():
    try:
        return jsonify(garmin_io.import_tokens(request.json.get("tokens", "")))
    except Exception as e:
        return jsonify(error=f"הטוקנים לא תקינים: {e}"), 400


@app.post("/api/preview")
def preview():
    d = request.json
    out = {"errors": {}}
    plan = planner.parse_plan(d["plan"])
    if not plan.get("blocks"):
        return jsonify(error="לא הצלחתי לפענח את התוכנית"), 400
    st = planner.stats(plan["blocks"], float(d.get("walk_kmh") or 6), d.get("run_pace") or "6:30")
    out.update(plan=plan, stats=st)
    state = {"plan": plan, "stats": st}
    try:
        if not os.getenv("ORS_API_KEY"):
            raise RuntimeError("חסר מפתח OpenRouteService – הדבק אותו בכרטיס 'חיבורים' למעלה")
        lat, lon = route.geocode(d.get("address") or DEFAULT_ADDRESS)
        r = route.build_route(lat, lon, st["meters"], bool(d.get("hills")))
        state["route"] = r
        pts = r["coords"]
        step = max(1, len(pts) // 8)
        wp = "|".join(f"{c[1]:.5f},{c[0]:.5f}" for c in pts[step:-1:step][:8])
        gm = (f"https://www.google.com/maps/dir/?api=1&travelmode=walking"
              f"&origin={pts[0][1]:.5f},{pts[0][0]:.5f}&destination={pts[-1][1]:.5f},{pts[-1][0]:.5f}"
              f"&waypoints={wp}")
        out["route"] = {"gmaps": gm, "coords": [[c[1], c[0]] for c in pts],
                        "meters": round(r["meters"]), "ascent": round(r["ascent"])}
    except Exception as e:
        out["errors"]["route"] = str(e)
    try:
        client = music.sp()
        cands = music.suggest(d.get("genres") or "מוזיקה ישראלית קצבית")
        pools = {k: music.resolve(client, v) for k, v in cands.items()}
        tracks = music.assemble(plan["blocks"], pools)
        state["tracks"] = tracks
        out["tracks"] = tracks
    except Exception as e:
        out["errors"]["music"] = str(e)
    storage.set("state", state)
    return jsonify(out)


@app.post("/api/send")
def send():
    d = request.json
    res = {}
    date = d.get("date") or None
    state = storage.get("state") or {}
    if "course" in d["targets"] and "route" in state:
        try:
            name = f'{state["plan"].get("name", "אימון")} {date or ""}'.strip()
            garmin_io.upload_course(route.to_gpx(state["route"]["coords"], name), name)
            res["course"] = "הועלה ל-Garmin Connect"
        except Exception as e:
            res["course"] = f"שגיאה: {e}"
    if "workout" in d["targets"] and "plan" in state:
        try:
            garmin_io.upload_workout(state["plan"], state["stats"]["seconds"], date)
            res["workout"] = "הועלה ושובץ ביומן" if date else "הועלה"
        except Exception as e:
            res["workout"] = f"שגיאה: {e}"
    if "playlist" in d["targets"] and "tracks" in state:
        try:
            url = music.create_playlist(music.sp(), f'RunCoach {date or ""}', state["tracks"])
            res["playlist"] = url
        except Exception as e:
            res["playlist"] = f"שגיאה: {e}"
    if not res:
        res["course"] = "שגיאה: אין תצוגה מקדימה. בנה קודם אימון"
    return jsonify(res)


if __name__ == "__main__":
    app.run(port=5000, debug=False)
