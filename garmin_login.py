"""מריצים פעם אחת במחשב: מתחברים ל-Garmin (כולל MFA) ומעתיקים טוקנים להדבקה באפליקציה.

    python garmin_login.py
"""
import getpass
import subprocess

from garminconnect import Garmin

email = input("אימייל Garmin: ").strip()
password = getpass.getpass("סיסמה: ")
g = Garmin(email, password, prompt_mfa=lambda: input("קוד אימות (MFA): ").strip())
g.login()
tokens = g.client.dumps()
try:
    subprocess.run("clip", input=tokens.encode("ascii"), check=True)
    print("\nהטוקנים הועתקו ללוח. הדבק אותם באפליקציה: חיבורים ← Garmin ← 'הדבק טוקנים'.")
except Exception:
    print("\nהעתק את הטקסט הבא והדבק באפליקציה:\n")
    print(tokens)
