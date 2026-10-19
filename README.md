# RunCoach

אפליקציה שהופכת תוכנית ריצה למסלול ואימון ב-Garmin ולפלייליסט ב-Spotify.

## הרצה מקומית
`pip install -r requirements.txt` ואז `python app.py` ופתח http://127.0.0.1:5000

## פריסה ל-Vercel
1. Import של המאגר ב-Vercel (Framework: Flask / Other).
2. Environment Variables: `APP_PASSWORD` (סיסמת כניסה, חובה), ו-`ORS_API_KEY` (אופציונלי, אפשר גם מהדף).
3. Storage ← Marketplace ← Upstash Redis (חינמי), חבר לפרויקט. זה מוסיף לבד את משתני `KV_REST_API_*`.
4. Redeploy.
5. ב-Spotify dashboard הוסף Redirect URI: `https://<הדומיין שלך>/callback`.
6. Garmin: אם נדרש MFA או שיש חסימה, הרץ במחשב `python garmin_login.py` והדבק את הטוקנים בדף.
