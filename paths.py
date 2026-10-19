"""נתיב לנתונים מתמידים (טוקנים והגדרות). בענן מצביעים עליו לדיסק קבוע דרך DATA_DIR."""
import os
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR") or Path(__file__).resolve().parent)
DATA_DIR.mkdir(parents=True, exist_ok=True)
ENV_FILE = DATA_DIR / ".env"
