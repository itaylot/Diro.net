# Safe Commit

## Steps

1. Run `git diff` and `git status` to see what changed
2. Review the diff:
   - Are all changes intentional and related to the same task?
   - Are there any debug prints, test values, or accidental edits?
   - Are there any sensitive values (tokens, passwords) being committed?
     - Check especially: `settings.json` contains `telegram_token` and `telegram_chat_id` — do NOT commit this file
3. Run a basic sanity check:
   - `python -m py_compile dashboard.py` — syntax check
   - `python -m py_compile apartment_agent.py`
   - `python -m py_compile facebook_agent.py`
4. Suggest a commit message following this format:
   ```
   <type>: <short description>

   <optional body — what changed and why>
   ```
   Types: `feat`, `fix`, `style`, `refactor`, `docs`, `chore`

5. Ask for confirmation before committing

## Files to NEVER commit
- `settings.json` (contains Telegram token + chat ID)
- `fb_chrome_profile/` (Chrome login session)
- `*.json` data files (`all_listings.json`, `dismissed.json`, `seen_*.json`, `tips.json`)
- `__pycache__/`

## If git is not initialized
Say so and ask whether to initialize it.
