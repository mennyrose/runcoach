"""אחסון מפתח-ערך. בענן (Vercel) משתמש ב-Upstash Redis דרך REST; מקומית בקבצי JSON."""
import json
import os

import requests

from paths import DATA_DIR

def _find(suffixes, exclude=()):
    """Vercel מוסיף קידומת לפי הבחירה בחיבור (KV_, UPSTASH_REDIS_, STORAGE_ ...), לכן מחפשים לפי סיומת."""
    for k, v in os.environ.items():
        if v and k.endswith(suffixes) and not any(x in k for x in exclude):
            return v


URL = _find(("REST_API_URL", "REDIS_REST_URL"))
TOKEN = _find(("REST_API_TOKEN", "REDIS_REST_TOKEN"), exclude=("READ_ONLY",))
REDIS_URL = os.getenv("REDIS_URL") or _find(("_REDIS_URL",), exclude=("REST",))
IN_CLOUD = bool(os.getenv("VERCEL") or os.getenv("RENDER") or os.getenv("FLY_APP_NAME"))
LOCAL = DATA_DIR / ".store"


def _cmd(*args):
    r = requests.post(URL, headers={"Authorization": f"Bearer {TOKEN}"}, json=list(args), timeout=15)
    r.raise_for_status()
    return r.json().get("result")


_redis = None


def _r():
    global _redis
    if _redis is None:
        import redis
        _redis = redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=10)
    return _redis


def _check():
    if IN_CLOUD and not (URL or REDIS_URL):
        raise RuntimeError("חסר אחסון: חבר מסד Redis לפרויקט ב-Vercel (Storage)")


def get(key):
    _check()
    if URL:
        v = _cmd("GET", key)
        return json.loads(v) if v else None
    if REDIS_URL:
        v = _r().get(key)
        return json.loads(v) if v else None
    p = LOCAL / f"{key}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def set(key, value):
    _check()
    if URL:
        _cmd("SET", key, json.dumps(value))
        return
    if REDIS_URL:
        _r().set(key, json.dumps(value))
        return
    LOCAL.mkdir(parents=True, exist_ok=True)
    (LOCAL / f"{key}.json").write_text(json.dumps(value), encoding="utf-8")
