"""אחסון מפתח-ערך. בענן (Vercel) משתמש ב-Upstash Redis דרך REST; מקומית בקבצי JSON."""
import json
import os

import requests

from paths import DATA_DIR

URL = os.getenv("KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL")
TOKEN = os.getenv("KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN")
IN_CLOUD = bool(os.getenv("VERCEL") or os.getenv("RENDER") or os.getenv("FLY_APP_NAME"))
LOCAL = DATA_DIR / ".store"


def _cmd(*args):
    r = requests.post(URL, headers={"Authorization": f"Bearer {TOKEN}"}, json=list(args), timeout=15)
    r.raise_for_status()
    return r.json().get("result")


def _check():
    if IN_CLOUD and not URL:
        raise RuntimeError("חסר אחסון: חבר Upstash Redis לפרויקט ב-Vercel (Storage)")


def get(key):
    _check()
    if URL:
        v = _cmd("GET", key)
        return json.loads(v) if v else None
    p = LOCAL / f"{key}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def set(key, value):
    _check()
    if URL:
        _cmd("SET", key, json.dumps(value))
        return
    LOCAL.mkdir(parents=True, exist_ok=True)
    (LOCAL / f"{key}.json").write_text(json.dumps(value), encoding="utf-8")
