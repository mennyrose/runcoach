"""פענוח תוכנית אימון בעברית למבנה JSON, ו-fallback בלי Claude."""
import json
import os
import re

SYSTEM = """אתה מפענח תוכניות אימון ריצה בעברית. החזר JSON בלבד, בלי טקסט נוסף:
{"name": "שם קצר", "blocks": [ ... ]}
כל בלוק הוא אחד מאלה:
{"kind": "walk" | "run", "seconds": מספר שלם, "pace": "m:ss" או null}
{"repeat": מספר, "steps": [ בלוקי kind בלבד ]}
"הליכה מהירה" = walk. "ריצה" = run. pace רק אם צוין מקצב במפורש (דק' לק"מ).
"דקה וחצי" = 90 שניות. סדר הבלוקים כסדר התוכנית."""


def parse_plan(text: str) -> dict:
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            import anthropic
            msg = anthropic.Anthropic().messages.create(
                model="claude-sonnet-5-5", max_tokens=2000, system=SYSTEM,
                messages=[{"role": "user", "content": text}])
            raw = msg.content[0].text
            return json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
        except Exception as e:  # נופל ל-fallback
            print("Claude parse failed, using regex:", e)
    return regex_parse(text)


def _seconds(s: str):
    s = s.strip()
    if re.search(r"חצי\s*דקה", s):
        return 30
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:דק|דקות)['׳]?\s*וחצי", s)
    if m:
        return int(float(m.group(1)) * 60 + 30)
    if re.search(r"דקה\s*וחצי", s):
        return 90
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:שניות|שנ)", s)
    if m:
        return int(float(m.group(1)))
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:דק|דקות)", s)
    if m:
        return int(float(m.group(1)) * 60)
    if "דקה" in s:
        return 60
    return None


def _step(piece: str):
    sec = _seconds(piece)
    if not sec:
        return None
    kind = "run" if re.search(r"ריצ|רוץ|רץ", piece) else "walk"
    return {"kind": kind, "seconds": sec, "pace": None}


def regex_parse(text: str) -> dict:
    blocks = []
    for chunk in re.split(r"[,\n;]| ואז | לבסוף ", text):
        chunk = chunk.strip()
        if not chunk:
            continue
        m = re.search(r"(\d+)\s*(?:סבבים|חזרות|פעמים)", chunk)
        if m:
            body = re.split(r"\bשל\b", chunk, maxsplit=1)[-1]
            steps = [s for s in (_step(p) for p in re.split(r"\s[-–—]\s|ואז", body)) if s]
            if steps:
                blocks.append({"repeat": int(m.group(1)), "steps": steps})
            continue
        s = _step(chunk)
        if s:
            blocks.append(s)
    return {"name": "אימון", "blocks": blocks}


def expand(blocks):
    """רשימה שטוחה של (kind, seconds)."""
    out = []
    for b in blocks:
        if "repeat" in b:
            for _ in range(b["repeat"]):
                out += [(s["kind"], s["seconds"]) for s in b["steps"]]
        else:
            out.append((b["kind"], b["seconds"]))
    return out


def stats(blocks, walk_kmh=6.0, run_pace="6:30"):
    mm, ss = run_pace.split(":")
    run_kmh = 60 / (int(mm) + int(ss) / 60)
    steps = expand(blocks)
    total = sum(s for _, s in steps)
    meters = sum(s / 3600 * (run_kmh if k == "run" else walk_kmh) * 1000 for k, s in steps)
    return {"seconds": total, "meters": round(meters)}


def phases(blocks):
    """שלבים למוזיקה: ריצות קצרות עם הליכה קצרה ביניהן מתמזגות לשלב אחד."""
    steps = [[k, s] for k, s in expand(blocks)]
    for i in range(1, len(steps) - 1):
        if (steps[i][0] == "walk" and steps[i][1] <= 180
                and steps[i - 1][0] == "run" and any(k == "run" for k, _ in steps[i + 1:])):
            steps[i][0] = "run"
    merged = []
    for k, s in steps:
        if merged and merged[-1][0] == k:
            merged[-1][1] += s
        else:
            merged.append([k, s])
    return merged


if __name__ == "__main__":
    p = regex_parse("5 דק' הליכה מהירה, 8 סבבים של דקה אחת ריצה - דקה וחצי הליכה מהירה, לבסוף 3 דקות הליכה מהירה")
    print(json.dumps(p, ensure_ascii=False))
    print(stats(p["blocks"]), phases(p["blocks"]))
