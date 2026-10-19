# RunCoach

1. `pip install -r requirements.txt`
2. העתק את `.env.example` ל-`.env` ומלא רק מפתחות אפליקציה: Anthropic ו-OpenRouteService. את Spotify Client ID מדביקים בדף בלחיצה הראשונה על 'חבר Spotify' (הדף מסביר איך).
3. `python app.py` ופתח http://127.0.0.1:5000
4. בדף: לחץ "חבר Spotify" (התחברות ב-Spotify, אפשר עם גוגל) ו"חבר Garmin" (אימייל וסיסמה פעם אחת, כולל קוד MFA אם יש; נשמרים טוקנים בלבד ב-~/.garminconnect).
5. אחרי השליחה: סנכרן את השעון עם Garmin Connect, והורד את הפלייליסט לשעון דרך אפליקציית Spotify בשעון ב-Wi-Fi.
