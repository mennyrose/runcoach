"""העלאת מסלול ואימון ל-Garmin Connect (ספרייה לא רשמית)."""
import tempfile
from pathlib import Path

from garminconnect import Garmin
from garminconnect.workout import (RunningWorkout, WorkoutSegment, create_cooldown_step,
                                   create_interval_step, create_recovery_step,
                                   create_repeat_group, create_warmup_step)

import storage

KEY = "garmin_tokens"
_api = None
_pending_mfa = None


def _legacy_tokens():
    """חיבור מקומי קיים מגרסאות קודמות (~/.garminconnect)."""
    p = Path.home() / ".garminconnect"
    if not storage.IN_CLOUD and p.exists():
        g = Garmin()
        g.login(str(p))
        return g.client.dumps()


def api():
    """חיבור מתוך טוקנים ששמורים באחסון. הסיסמה לא נשמרת."""
    global _api
    if _api is None:
        tokens = storage.get(KEY) or _legacy_tokens()
        if not tokens:
            raise RuntimeError("Garmin לא מחובר")
        g = Garmin()
        g.login(tokens)
        storage.set(KEY, g.client.dumps())  # שומר גם טוקן שהתחדש
        _api = g
    return _api


def is_connected() -> bool:
    return bool(storage.get(KEY)) or (not storage.IN_CLOUD and (Path.home() / ".garminconnect").exists())


def connect(email: str, password: str, mfa_code: str | None = None) -> dict:
    """התחברות ראשונית. מחזיר {"ok": True} או {"mfa": True} אם נדרש קוד אימות (מקומית בלבד)."""
    global _api, _pending_mfa
    if mfa_code and _pending_mfa:
        g, state = _pending_mfa
        g.resume_login(state, mfa_code)
        storage.set(KEY, g.client.dumps())
        _api, _pending_mfa = g, None
        return {"ok": True}
    g = Garmin(email, password, return_on_mfa=True)
    needs_mfa, state = g.login()
    if needs_mfa:
        if storage.IN_CLOUD:
            raise RuntimeError("בחשבון שלך נדרש קוד אימות (MFA), וזה לא נתמך בענן. "
                               "הרץ במחשב garmin_login.py והדבק כאן את הטוקנים.")
        _pending_mfa = (g, state)
        return {"mfa": True}
    storage.set(KEY, g.client.dumps())
    _api = g
    return {"ok": True}


def import_tokens(text: str) -> dict:
    """הדבקת טוקנים שנוצרו במחשב (garmin_login.py). מאמת שהם עובדים."""
    global _api
    g = Garmin()
    g.login(text.strip())
    storage.set(KEY, g.client.dumps())
    _api = g
    return {"ok": True}


def upload_course(gpx_xml: str, name: str):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / f"{name}.gpx"
        p.write_text(gpx_xml, encoding="utf-8")
        return api().import_course(str(p))


def _flat(blocks):
    n = 0
    steps = []

    def nxt():
        nonlocal n
        n += 1
        return n

    first_walk = blocks and "kind" in blocks[0] and blocks[0]["kind"] == "walk"
    last_i = len(blocks) - 1
    for i, b in enumerate(blocks):
        if "repeat" in b:
            order = nxt()
            inner = []
            for s in b["steps"]:
                fn = create_interval_step if s["kind"] == "run" else create_recovery_step
                inner.append(fn(float(s["seconds"]), nxt()))
            steps.append(create_repeat_group(b["repeat"], inner, order))
        elif i == 0 and first_walk:
            steps.append(create_warmup_step(float(b["seconds"]), nxt()))
        elif i == last_i and b["kind"] == "walk" and i > 0:
            steps.append(create_cooldown_step(float(b["seconds"]), nxt()))
        else:
            fn = create_interval_step if b["kind"] == "run" else create_recovery_step
            steps.append(fn(float(b["seconds"]), nxt()))
    return steps


def upload_workout(plan: dict, total_seconds: int, date_str: str | None):
    w = RunningWorkout(
        workoutName=plan.get("name") or "אימון",
        estimatedDurationInSecs=total_seconds,
        workoutSegments=[WorkoutSegment(
            segmentOrder=1,
            sportType={"sportTypeId": 1, "sportTypeKey": "running", "displayOrder": 1},
            workoutSteps=_flat(plan["blocks"]))])
    res = api().upload_running_workout(w)
    if date_str:
        api().schedule_workout(res["workoutId"], date_str)
    return res
