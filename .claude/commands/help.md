# Available Commands

| Command | Usage | Description |
|---------|-------|-------------|
| `/start-session` | `/start-session` | טוען הקשר פרויקט, מסכם מצב ועדיפות, לא נוגע בקוד |
| `/wrapup` | `/wrapup` | מעדכן PROJECT_STATE.md ומוסיף entry ל-SESSION_LOG.md |
| `/next-step` | `/next-step` | מציע את הצעד הקטן הבא, מפרט קבצים, מחכה לאישור |
| `/fix-bug` | `/fix-bug <תיאור הבאג>` | מאתר ומתקן באג ספציפי, שינוי מינימלי בלבד |
| `/ui-polish` | `/ui-polish <מה לשפר>` | משפר UI/UX בלבד, לא נוגע בלוגיקת סוכנים |
| `/safe-commit` | `/safe-commit` | בודק diff, מאמת syntax, מציע commit message |
| `/commands` | `/commands` | מציג את הטבלה הזו |

## Tips
- `/start-session` — תמיד תתחיל כאן אחרי `/clear`
- `/wrapup` — תריץ בסוף כל session לפני שסוגר
- `/fix-bug` ו-`/ui-polish` מקבלים ארגומנט — תאר מה הבעיה
