1. Create a GitHub repo, push this folder (incl. .github).
2. Settings > Pages > Deploy from branch `main` / root. Your page: https://<user>.github.io/<repo>/
3. Actions tab > fetch-jobs > Run workflow (first run, silent). Runs every ~15 min after.
4. Optional Telegram: add repo secrets TG_TOKEN (from @BotFather) and TG_CHAT (your chat id).
Edit companies.json to add/remove boards (slug = name in the company's jobs URL). Failing slugs are logged as FAIL in the Actions run.
