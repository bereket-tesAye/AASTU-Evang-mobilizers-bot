# 🇪🇹 AASTU Evang Mobilizers Team Bot

A comprehensive Telegram bot designed to facilitate Bible study plans, spiritual mentorship, and gospel outreach for the AASTU community. 

## ✨ Features

* 📖 **Interactive Bible Study:** Automated 21-day "Gospel of John" study plan with daily lessons.
* 🤝 **Mentor Assignment:** Integrated system to request spiritual guidance, categorized by user intent (New Believer, Recommitment, General Questions).
* ⏰ **Smart Scheduler:** Uses `APScheduler` to send daily study content every 24 hours based on individual user progress.
* 📚 **Resource Library:** Instant access to digital study materials (Word & PowerPoint) covering common questions on Christianity.
* 🛠️ **Admin Notifications:** Real-time reporting of mentor requests sent directly to a designated Mentor Group ID.

## 🚀 Tech Stack

* **Language:** Python 3.x
* **Framework:** `pyTelegramBotAPI` (Telebot)
* **Database:** MySQL (Connector/Python)
* **Task Scheduling:** `APScheduler`
* **Environment Management:** `python-dotenv`

## 📦 Installation & Setup

1.  **Clone the Repository:**
    ```bash
    git clone [https://github.com/bereket-tesAye/AASTU-Evang-mobilizers-bot.git](https://github.com/bereket-tesAye/AASTU-Evang-mobilizers-bot.git)
    cd AASTU-Evang-mobilizers-bot
    ```

2.  **Create a Virtual Environment:**
    ```bash
    python -m venv .tgvenv
    source .tgvenv/bin/scripts/activate  # On Windows use: .tgvenv\Scripts\activate
    ```

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure Environment Variables:**
    Create a `.env` file in the root directory and add your credentials (do NOT share this file):
    ```text
    TELEGRAM_BOT_TOKEN=your_bot_token_here
    DB_PASSWORD=your_mysql_password_here
    BOT_MODE=polling

    # Webhook mode (only needed when BOT_MODE=webhook)
    # Single public HTTPS URL. Must include a path.
    # WEBHOOK_URL=https://your-domain.com/telegram-webhook
    # Optional: local bind port (defaults to 8443)
    # PORT=8443
    ```

    `BOT_MODE` supports:
    - `polling` (default)
    - `webhook`

    In `polling` mode, the bot runs `infinity_polling()`.
    In `webhook` mode, the bot normalizes `WEBHOOK_URL` to end with `/` and uses that exact webhook path.

5.  **Run the Bot:**
    ```bash
    python evangtelegrambot.py
    ```

## 📂 Project Structure

* `evangtelegrambot.py`: Main bot logic and message handlers.
* `study_materials/`: Directory containing PPTX and DOCX resources.
* `requirements.txt`: List of Python libraries required.
* `.gitignore`: Prevents sensitive files like `.env` and virtual environments from being uploaded.

## ❤️ Community
Developed for the **AASTU Evang Mobilizers Team**. 
*"Go into all the world and preach the gospel to all creation." - Mark 16:15*
