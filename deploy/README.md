# TeacherOS Production Deployment Files

These files are templates for a public server. Do not use them unchanged.

## What each file does

- `teacheros.service.template`: keeps the Telegram bot running after you close the terminal or restart the server.
- `nginx-teacheros.conf.template`: publishes the landing page and forwards ZarinPal callbacks to the private Python payment server.
- `env.production.example.txt`: lists the production environment variables without containing real secrets.

## Required replacements

Replace `/opt/teacheros` if you install the project elsewhere. Replace `teacheros.example.com` with your real domain. Copy `env.production.example.txt` to `/opt/teacheros/.env`, then replace every placeholder.

## Security rules

1. Never place `.env` in the website folder.
2. Never commit `.env` to GitHub.
3. Keep `PAYMENT_SERVER_HOST=127.0.0.1` when Nginx runs on the same server.
4. Use a public HTTPS callback URL before setting `ZARINPAL_SANDBOX=false`.
5. Run `python backend/backup_teacheros.py --label prelaunch` before deployment.
6. Run `python backend/launch_check.py --mode paid` before accepting real payments.

The detailed beginner instructions are in `docs/Day30_Launch_Checklist.md`.
