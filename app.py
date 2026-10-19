import datetime as dt
import os

from dotenv import load_dotenv, set_key
from flask import Flask, jsonify, redirect, render_template, request, session

import secrets
from werkzeug.middleware.proxy_fix import ProxyFix
from paths import ENV_FILE

load_dotenv()
load_dotenv(ENV_FILE)
import garmin_io, music, planner, route  # noqa: E402

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 90)
APP_PASSWORD = os.getenv("APP_PASSWORD")
IN_CLOUD = bool(os.getenv("RENDER") or os.getenv("FLY_APP_NAME") or os.getenv("RAILWAY_ENVIRONMENT"))
STATE = {}
DEFAULT_ADDRESS = os.getenv("DEFAULT_ADDRESS", "טרומפלדור 4, קרית אתא")


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
    if IN_CLOUD and not APP_PASSWORD:
        return "APP_PASSWORD לא מוגדר – השרת נעול", 503
    if not APP_PASSWORD or session.get("ok") or request.path == "/login":
        return None
    if request.path.startswith("/api/"):
        return jsonify(error="לא מחובר"), 401
    return redirect("/login")


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
    return jsonify(spotify=music.is_connected(), garmin=garmin_io.is_connected(),
                   spotify_configured=bool(os.getenv("SPOTIPY_CLIENT_ID")),
                   ors=bool(os.getenv("ORS_API_KEY")))


@app.post("/api/spotify/setup")
def spotify_setup():
    """שמירה חד-פעמית של Client ID (לא סוד) ב-.env המקומי."""
    cid = (request.json.get("client_id") or "").strip()
    if len(cid) < 20:
        return jsonify(error="Client ID לא נראה תקין"), 400
    env = str(ENV_FILE)
    open(env, "a", encoding="utf-8").close()
    set_key(env, "SPOTIPY_CLIENT_ID", cid)
    os.environ["SPOTIPY_CLIENT_ID"] = cid
    return jsonify(ok=True)


@app.post("/api/ors/setup")
def ors_setup():
    key = (request.json.get("key") or "").strip()
    if len(key) < 20:
        return jsonify(error="המפתח לא נראה תקין"), 400
    env = str(ENV_FILE)
    open(env, "a", encoding="utf-8").close()
    set_key(env, "ORS_API_KEY", key)
    os.environ["ORS_API_KEY"] = key
    return jsonify(ok=True)


@app.get("/spotify/login")
def spotify_login():
    if not os.getenv("SPOTIPY_CLIENT_ID"):
        return redirect("/?spotify_setup=1")
    os.environ.setdefault("SPOTIPY_REDIRECT_URI", request.url_root + "callback")
    return redirect(music.auth().get_authorize_url())


@app.get("/callback")
def spotify_callback():
    code = request.args.get("code")
    os.environ.setdefault("SPOTIPY_REDIRECT_URI", request.url_root + "callback")
    if code:
        music.auth().get_access_token(code, check_cache=False)
    return redirect("/")


@app.post("/api/garmin/connect")
def garmin_connect():
    d = request.json
    try:
        return jsonify(garmin_io.connect(d.get("email", ""), d.get("password", ""), d.get("mfa") or None))
    except Exception as e:
        return jsonify(error=str(e)), 400


@app.post("/api/preview")
def preview():
    d = request.json
    out = {"errors": {}}
    plan = planner.parse_plan(d["plan"])
    if not plan.get("blocks"):
        return jsonify(error="לא הצלחתי לפענח את התוכנית"), 400
    st = planner.stats(plan["blocks"], float(d.get("walk_kmh") or 6), d.get("run_pace") or "6:30")
    out.update(plan=plan, stats=st)
    STATE.update(plan=plan, stats=st)
    try:
        if not os.getenv("ORS_API_KEY"):
            raise RuntimeError("חסר מפתח OpenRouteService – הדבק אותו בכרטיס 'חיבורים' למעלה")
        lat, lon = route.geocode(d.get("address") or DEFAULT_ADDRESS)
        r = route.build_route(lat, lon, st["meters"], bool(d.get("hills")))
        STATE["route"] = r
        pts = r["coords"]
        step = max(1, len(pts) // 8)
        wp = "|".join(f"{c[1]:.5f},{c[0]:.5f}" for c in pts[step:-1:step][:8])
        gm = (f"https://www.google.com/maps/dir/?api=1&travelmode=walking"
              f"&origin={pts[0][1]:.5f},{pts[0][0]:.5f}&destination={pts[-1][1]:.5f},{pts[-1][0]:.5f}"
              f"&waypoints={wp}")
        out["route"] = {"gmaps": gm, "coords": [[c[1], c[0]] for c in r["coords"]],
                        "meters": round(r["meters"]), "ascent": round(r["ascent"])}
    except Exception as e:
        out["errors"]["route"] = str(e)
    try:
        client = music.sp()
        cands = music.suggest(d.get("genres") or "מוזיקה ישראלית קצבית")
        pools = {k: music.resolve(client, v) for k, v in cands.items()}
        tracks = music.assemble(plan["blocks"], pools)
        STATE["tracks"] = tracks
        out["tracks"] = tracks
    except Exception as e:
        out["errors"]["music"] = str(e)
    return jsonify(out)


@app.post("/api/send")
def send():
    d = request.json
    res = {}
    date = d.get("date") or None
    if "course" in d["targets"] and "route" in STATE:
        try:
            name = f'{STATE["plan"].get("name", "אימון")} {date or ""}'.strip()
            garmin_io.upload_course(route.to_gpx(STATE["route"]["coords"], name), name)
            res["course"] = "הועלה ל-Garmin Connect"
        except Exception as e:
            res["course"] = f"שגיאה: {e}"
    if "workout" in d["targets"] and "plan" in STATE:
        try:
            garmin_io.upload_workout(STATE["plan"], STATE["stats"]["seconds"], date)
            res["workout"] = "הועלה ושובץ ביומן" if date else "הועלה"
        except Exception as e:
            res["workout"] = f"שגיאה: {e}"
    if "playlist" in d["targets"] and "tracks" in STATE:
        try:
            url = music.create_playlist(music.sp(), f'RunCoach {date or ""}', STATE["tracks"])
            res["playlist"] = url
        except Exception as e:
            res["playlist"] = f"שגיאה: {e}"
    return jsonify(res)


if __name__ == "__main__":
    app.run(port=5000, debug=False)
