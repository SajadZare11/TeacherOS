# TeacherOS Landing Page

This folder is the Day 27 landing page for TeacherOS. It is a static website, so it does not require Python, a database, or a web framework.

## 1. Add the Telegram bot link

Open:

```text
website/site-config.js
```

Replace:

```javascript
telegramBotUrl: "https://t.me/Teacheros1_bot",
```

with your real BotFather username. Example:

```javascript
telegramBotUrl: "https://t.me/Teacheros1_bot",
```

Do not paste the Telegram bot token here. The website needs only the public username.

## 2. Preview the website in PyCharm

Open the PyCharm terminal from the main project folder and run:

```bash
python -m http.server 8000 --directory website
```

Open this address in your browser:

```text
http://localhost:8000
```

Stop the preview server with `Ctrl + C`.

## 3. Files

```text
website/
├── index.html       Website content
├── styles.css       Design and responsive layout
├── script.js        Mobile menu, FAQ, links, and setup warning
├── site-config.js   Public Telegram link
└── README.md        Setup instructions
```

## 4. Before publishing

- Add the real Telegram username in `site-config.js`.
- Open every call-to-action button and verify it opens the correct bot.
- Check the page on a phone and computer.
- Confirm the prices match the current values in `backend/config.py`.
- Never add `.env`, bot tokens, API keys, or payment credentials to this folder.
