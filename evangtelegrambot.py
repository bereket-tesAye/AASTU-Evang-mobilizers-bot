import os
import threading
from urllib.parse import urlparse
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask
import telebot
from telebot.types import KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
import mysql.connector
from apscheduler.schedulers.background import BackgroundScheduler

load_dotenv()

# ─────────────────────────────────────────────
#  Flask health-check server (for Render)
# ─────────────────────────────────────────────
app = Flask(__name__)

@app.route("/")
@app.route("/health")
def health_check():
    return "Bot is alive!", 200

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


# ─────────────────────────────────────────────
#  Database
# ─────────────────────────────────────────────
def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user="root",
        password=os.getenv("DB_PASSWORD"),
        database="EvangBibleStudyPlan",
        charset='utf8mb4'
    )


# ─────────────────────────────────────────────
#  Bot & config
# ─────────────────────────────────────────────
API_KEY        = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID", "0"))

# Individual mentor IDs (used only for registration-complete notifications)
MENTOR_EVANGELISM_ID  = int(os.getenv("MENTOR_EVANGELISM_ID",  "111111111"))
MENTOR_COUNSELING_ID  = int(os.getenv("MENTOR_COUNSELING_ID",  "222222222"))
MENTOR_BIBLE_STUDY_ID = int(os.getenv("MENTOR_BIBLE_STUDY_ID", "333333333"))

SPECIALIST_MENTOR_MAP = {
    "አማካሪ ማግኘት እፈልጋለሁ": MENTOR_COUNSELING_ID,
    "ጥያቄ መጠየቅ እፈልጋለሁ":  MENTOR_BIBLE_STUDY_ID,
}

BOT_MODE    = os.getenv("BOT_MODE", "polling").strip().lower()
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip()

bot = telebot.TeleBot(API_KEY)


# ─────────────────────────────────────────────
#  In-memory mapping: user_id <-> forum topic_id
#  { user_telegram_id: topic_id }
# ─────────────────────────────────────────────
user_topic_map: dict[int, int] = {}


def get_or_create_topic(user_id: int, display_name: str) -> int:
    """Return existing forum topic ID for the user, or create a new one."""
    if user_id in user_topic_map:
        return user_topic_map[user_id]

    try:
        result = bot.create_forum_topic(
            chat_id=ADMIN_GROUP_ID,
            name=f"👤 {display_name} ({user_id})"
        )
        topic_id = result.message_thread_id
        user_topic_map[user_id] = topic_id
        return topic_id
    except Exception as e:
        print(f"Error creating forum topic for {user_id}: {e}")
        raise


def relay_to_admin(user_id: int, display_name: str, message):
    """Forward a user message into their dedicated admin group topic."""
    topic_id = get_or_create_topic(user_id, display_name)
    try:
        # Forward the original message into the topic thread
        bot.forward_message(
            chat_id=ADMIN_GROUP_ID,
            from_chat_id=user_id,
            message_id=message.message_id,
            message_thread_id=topic_id
        )
    except Exception as e:
        print(f"Error relaying message from {user_id} to admin group: {e}")


def relay_to_user(admin_message):
    """
    When a mentor replies inside a forum topic thread, parse the user_id
    from the topic name and relay the reply back to the user anonymously.
    """
    thread_id = admin_message.message_thread_id
    if not thread_id:
        return  # Message not inside a topic thread, ignore

    # Find the user whose topic this is
    user_id = next(
        (uid for uid, tid in user_topic_map.items() if tid == thread_id),
        None
    )

    if user_id is None:
        # Try to resolve from topic title via getForumTopics (fallback)
        print(f"Warning: received reply in topic {thread_id} but no user mapping found.")
        return

    try:
        # Send the mentor's text/media back to the user, attributed only as the bot
        if admin_message.text:
            bot.send_message(user_id, f"💬 {admin_message.text}")
        elif admin_message.photo:
            bot.send_photo(user_id, admin_message.photo[-1].file_id,
                           caption=admin_message.caption or "")
        elif admin_message.document:
            bot.send_document(user_id, admin_message.document.file_id,
                              caption=admin_message.caption or "")
        elif admin_message.voice:
            bot.send_voice(user_id, admin_message.voice.file_id)
        elif admin_message.video:
            bot.send_video(user_id, admin_message.video.file_id,
                           caption=admin_message.caption or "")
        elif admin_message.sticker:
            bot.send_sticker(user_id, admin_message.sticker.file_id)
        else:
            bot.send_message(user_id, "📎 አዲስ መልዕክት ከአማካሪ ደርሷል።")
    except Exception as e:
        print(f"Error relaying admin reply to user {user_id}: {e}")


# ─────────────────────────────────────────────
#  Daily bible study scheduler
# ─────────────────────────────────────────────
def send_daily_lessons():
    db = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        query = """
            SELECT telegram_id, active_book, current_day
            FROM user_progress
            WHERE last_sent_at <= NOW() - INTERVAL 24 HOUR
            AND subscription_status = 'active'
        """
        cursor.execute(query)
        due_users = cursor.fetchall()

        for user in due_users:
            next_day = user['current_day'] + 1
            cursor.execute(
                "SELECT chapter, teaching_content FROM study_content WHERE book_name = %s AND day_number = %s",
                (user['active_book'], next_day)
            )
            content = cursor.fetchone()

            if content:
                text = f"📖 *{content['chapter']}*\n\n{content['teaching_content']}"
                try:
                    bot.send_message(user['telegram_id'], text, parse_mode="Markdown")
                    cursor.execute(
                        "UPDATE user_progress SET current_day = %s, last_sent_at = NOW() WHERE telegram_id = %s",
                        (next_day, user['telegram_id'])
                    )
                    db.commit()
                except Exception as e:
                    print(f"Error sending daily lesson to {user['telegram_id']}: {e}")
            else:
                cursor.execute(
                    "UPDATE user_progress SET subscription_status = 'completed' WHERE telegram_id = %s",
                    (user['telegram_id'],)
                )
                db.commit()
                bot.send_message(
                    user['telegram_id'],
                    "🎉 እንኳን ደስ አሎት! የ21 ቀን የዮሐንስ ወንጌል ጥናትዎን አጠናቅቀዋል።"
                )
    except Exception as e:
        print(f"Scheduler Error: {e}")
    finally:
        if db and db.is_connected():
            cursor.close()
            db.close()

scheduler = BackgroundScheduler()
scheduler.add_job(send_daily_lessons, 'interval', minutes=60)
scheduler.start()


# ─────────────────────────────────────────────
#  Keyboards
# ─────────────────────────────────────────────
reply_keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
reply_keyboard.row("ኢየሱስን እንደ ግል አዳኝ አድርጌ ለመቀበል")
reply_keyboard.row("በንሰሀ መመለስ እፈልጋለሁ")
reply_keyboard.row("ስለ ኢየሱስ ክርስቶስ በበለጠ ለማወቅ")
reply_keyboard.row("የመጽሐፍ ቅዱስ ጥናት እቅድ ለማግኘት")
reply_keyboard.row("አማካሪ ማግኘት እፈልጋለሁ")
reply_keyboard.row("ጥያቄ መጠየቅ እፈልጋለሁ")
reply_keyboard.row("በስህተት ነው የነካሁት")

cancel_keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
cancel_keyboard.add(KeyboardButton("❌ ሰርዝ (Cancel)"))

sex_keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
sex_keyboard.row("Male", "Female")
sex_keyboard.row("❌ ሰርዝ (Cancel)")

# ─────────────────────────────────────────────
#  Study files
# ─────────────────────────────────────────────
STUDY_FILES_MAP = {
    "እኩል ስልጣን ካላቸው በ ዩሐ5 ለምን አብ ከእኔ ይበልጣል አለ?": "BQACAgQAAyEFAATkiwQeAAMUacTbMcmwvG88u9injn2s_JNg3ZIAAhMdAAIHdihST2mm2MGw0qo6BA",
    "ሥላሴ ሚለው ቃል መፅሐፍ ቅዱስ ላይ አለ ወይ?":             "BQACAgQAAyEFAATkiwQeAAMNacTbMaZk4sg1CaPu9ZZ6Dfkio8kAAgwdAAIHdihSTwX9MvVYtmM6BA",
    "አምላክ እንዴት ወደ አምላክ ይፀልያል?":                   "BQACAgQAAyEFAATkiwQeAAMQacTbMRzZ4yCmC2JPLW7iwLsOHoAAAg8dAAIHdihSZqqDCB2OQhU6BA",
    "አምላክ እንዴት ይወልዳል?":                            "BQACAgQAAyEFAATkiwQeAAMRacTbMed9vEegLIPBPTQoILT--40AAhAdAAIHdihS0ds89QKq1lA6BA",
    "ስንት አምላክ ነው ያላቹ?":                            "BQACAgQAAyEFAATkiwQeAAMOacTbMUIqjlYCQCvzKuIkmaecm5QAAg0dAAIHdihS8mG5Xi5-0uY6BA",
    "አንድ አምላክ እንዴት የአንድ አምላክ ልጅ ይባላል?":           "BQACAgQAAyEFAATkiwQeAAMTacTbMdKoMbmiUWz0Rd4WMAWby9QAAhIdAAIHdihSoaptNhjhh-A6BA",
    "የውሃ ጥምቀት በኢየሱስ ክርስቶስ ስም":                    "BQACAgQAAyEFAATkiwQeAAMWacTbMS3oCKVxFvlfMYJiBAq8nEIAAhUdAAIHdihSJ9OUTPAO0ao6BA",
    "ትምህርተ ሥላሴና የአረማውያኑ":                          "BQACAgQAAyEFAATkiwQeAAMPacTbMXJsAmzgTpc-i8sQsFyPXJIAAg4dAAIHdihSyaA5H27yGsM6BA",
    "የኦንሊ ጂሰሱ_አብ ወልድና መንፈስ ቅዱስ":                  "BQACAgQAAyEFAATkiwQeAAMVacTbMbVLit8MP8ZBqN7W5fD4pfMAAhQdAAIHdihSk2HT3OjY4ic6BA",
    "አብ ፣ ወልድና መንፈስ ቅዱስ የተለያዩ አካላት አይደሉምን":      "BQACAgQAAyEFAATkiwQeAAMSacTbMSGtXjsgRvk8DAQo4ud2cRwAAhEdAAIHdihS7tw9h3oYsWs6BA",
}


# ─────────────────────────────────────────────
#  Bot commands menu
# ─────────────────────────────────────────────
bot.set_my_commands([
    telebot.types.BotCommand('start', 'Start the bot'),
    telebot.types.BotCommand('help',  'Learn what this bot can do'),
    telebot.types.BotCommand('yes',   "I would like a mentor's guidance"),
    telebot.types.BotCommand('no',    "I do not need a mentor's guidance"),
])


# ─────────────────────────────────────────────
#  Registration state machine  (in-memory)
# ─────────────────────────────────────────────
user_states: dict[int, dict] = {}


def start_mentor_request(message, source: str):
    chat_id = message.chat.id
    user_states[chat_id] = {"step": "full_name", "source": source}

    if "አማካሪ ማግኘት እፈልጋለሁ" in source:
        msg = ("እኛን ለማግኘት ስለፈለጉ እናመሰግናለን🙏\n"
               "በcounseling Team ወደ ሚሰጥ ወደ ማማከር አገልግሎት ይወስዶታል።\n"
               "ለማቋረጥ 'cancel' ብለው ይጻፉ።\n\n"
               "ለመቀጠል እባክዎ ሙሉ ስምዎን ያስገቡ፦")

    elif "በንሰሀ መመለስ እፈልጋለሁ" in source:
        msg = (
            "🙏 በንሰሀ ለመመለስ መወሰንዎ ትልቅ ደስታ ነው!\n"
            "በኃጢአታችን ብንናዘዝ ኃጢአታችንን ይቅር ሊለን ከዓመፃም ሁሉ ሊያነጻን የታመነና ጻድቅ ነው።\n"
            "        - 1ኛ የዮሐንስ መልእክት 1 : 9\n\n"
            "ይህንን አጭር ፀሎት ይፀልዩ፦\n"
            "  'አምላክ ሆይ፣ በእኔ ምትክ እንዲቆምልኝና የሚገባኝን ቁጣህን በእርሱ ላይ ስለተቀበለልኝ "
            "ስለ ልጅህ አመሰግንሃለሁ። ... በኢየሱስ ስም፣ አሜን።'\n\n"
            "ለማቋረጥ 'cancel' ብለው ይጻፉ።\n\n"
            "ለመቀጠል እባክዎ ሙሉ ስምዎን ያስገቡ፦"
        )

    elif "ኢየሱስን እንደ ግል አዳኝ አድርጌ ለመቀበል" in source:
        msg = ("🙏 ኢየሱስን እንደ ግል አዳኝ ለመቀበል የመወሰንዎ ትልቅ ደስታ ነው!\n"
               "ለማቋረጥ 'cancel' ብለው ይጻፉ።\n\n"
               "ለመቀጠል እባክዎ ሙሉ ስምዎን ያስገቡ፦")
    else:
        msg = ("🙏 ጥያቄ መጠየቅ ስለፈለጉ እናመሰግናለን🙏\n"
               "ለማቋረጥ 'cancel' ብለው ይጻፉ።\n\n"
               "ለመቀጠል እባክዎ ሙሉ ስምዎን ያስገቡ፦")

    bot.send_message(chat_id, msg)


# ─────────────────────────────────────────────
#  Handlers — admin group replies
#  Any message a mentor sends inside a topic thread gets relayed to the user
# ─────────────────────────────────────────────
@bot.message_handler(
    func=lambda m: (
        m.chat.id == ADMIN_GROUP_ID
        and m.message_thread_id is not None
        and not (m.from_user and m.from_user.is_bot)
    )
)
def handle_admin_reply(message):
    relay_to_user(message)


# ─────────────────────────────────────────────
#  Handlers — user-facing commands
# ─────────────────────────────────────────────
@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = (
        "🙏 እንኳን ወደ AASTU Evang Mobilizers Team Bot በሰላም መጡ!\n\n"
        "ይህ ቦት ምን ሊያደርግ ይችላል?\n"
        "📋 ትዕዛዞች (Commands):\n"
        "/start - ይህን የእንኳን ደህና መጡ መልዕክት ያሳያል\n"
        "/help  - ይህ ቦት ምን መስራት እንደሚችል ያብራራል\n\n"
        "👇 ወይም ከታች ካሉት አማራጮች አንዱን ይምረጡ፦"
    )
    bot.reply_to(message, welcome_text, reply_markup=reply_keyboard)


@bot.message_handler(commands=['help'])
def show_help(message):
    help_text = (
        "🤖 ይህ ቦት ምን ሊያደርግ ይችላል?\n"
        "🤗 ይህ ቦት ኢየሱስን በበለጠ እንዲያውቁ ይረዳዎታል።\n\n"
        "📋 የሚገኙ ትዕዛዞች:\n"
        "/start - የአማራጭ ቁልፎችን የያዘ የእንኳን ደህና መጡ መልዕክት ያሳያል\n"
        "/help  - ይህን የእገዛ መልዕክት ያሳያል\n\n"
        "👇 ምርጫዎች:\n"
        "• ኢየሱስን እንደ ግል አዳኝ አድርጌ ለመቀበል\n"
        "• በንሰሀ መመለስ እፈልጋለሁ\n"
        "• ስለ ኢየሱስ ክርስቶስ በበለጠ ለማወቅ\n"
        "• የመጽሐፍ ቅዱስ ጥናት እቅድ ለማግኘት\n"
        "• አማካሪ ማግኘት እፈልጋለሁ\n"
        "• ጥያቄ መጠየቅ እፈልጋለሁ\n"
        "• በስህተት ነው የነካሁት\n\n"
        "❤️ ኢየሱስ ሁሉንም ይወዳል!!"
    )
    bot.reply_to(message, help_text, reply_markup=reply_keyboard)


@bot.message_handler(commands=['no'])
def no_mentor_assign(message):
    bot.send_message(
        message.chat.id,
        "ችግር የለም😊! ሃሳብዎን ከቀየሩ በማንኛውም ጊዜ /yes መጫን ይችላሉ።\n"
        "እግዚአብሔር ይባርክዎ! 🙏"
    )


@bot.message_handler(commands=['yes'])
def yes_mentor_assign(message):
    start_mentor_request(message, "ኢየሱስን እንደ ግል አዳኝ አድርጌ ለመቀበል")


# ─────────────────────────────────────────────
#  Registration multi-step handler
# ─────────────────────────────────────────────
@bot.message_handler(func=lambda message: message.chat.id in user_states)
def process_mentor_steps(message):
    chat_id = message.chat.id
    text = message.text.strip() if message.text else ""

    # Universal cancel
    if text == "❌ ሰርዝ (Cancel)" or text.lower() == "cancel":
        del user_states[chat_id]
        bot.send_message(chat_id, "ምዝገባው ተሰርዟል። ወደ ዋናው ማውጫ ተመልሰዋል። 🙏",
                         reply_markup=reply_keyboard)
        return

    state = user_states[chat_id]

    # Stage 1 — full name
    if state["step"] == "full_name":
        state["full_name"] = text
        state["step"] = "sex"
        bot.send_message(chat_id, "👉 ፆታዎን ያስገቡ (Male / Female):", reply_markup=sex_keyboard)

    # Stage 2 — sex
    elif state["step"] == "sex":
        if text.lower() not in ["male", "female"]:
            bot.send_message(chat_id, "❌ እባክዎ Male ወይም Female ብቻ ያስገቡ።", reply_markup=sex_keyboard)
            return
        state["sex"] = text
        state["step"] = "username"
        bot.send_message(chat_id, "👉 የቴሌግራም Username ያስገቡ (ለምሳሌ @yourname)፦",
                         reply_markup=cancel_keyboard)

    # Stage 3 — username → complete registration
    elif state["step"] == "username":
        username = text if text.startswith('@') else '@' + text
        source   = state['source']

        display_name = f"{state['full_name']} ({state['sex']})"

        # ── Create a forum topic for this user in the admin group ──
        try:
            topic_id = get_or_create_topic(chat_id, display_name)

            # Post the registration summary into their topic
            registration_report = (
                f"🚨 *New Mentor Request*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📌 *From:* {source}\n"
                f"👤 *Name:* {state['full_name']}\n"
                f"⚧ *Sex:* {state['sex']}\n"
                f"📱 *Username:* {username}\n"
                f"🆔 *User ID:* `{chat_id}`\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"↩️ Reply here to send a message back to the user anonymously."
            )
            bot.send_message(
                ADMIN_GROUP_ID,
                registration_report,
                parse_mode="Markdown",
                message_thread_id=topic_id
            )
        except Exception as e:
            print(f"Error setting up admin topic for {chat_id}: {e}")

        # ── Notify specialist mentor directly (DM) about the registration ──
        specialist_id = SPECIALIST_MENTOR_MAP.get(source)
        dm_report = (
            f"🚨 *New Mentor Request*\n"
            f"📌 *From:* {source}\n"
            f"👤 *Name:* {state['full_name']} | ⚧ {state['sex']}\n"
            f"📱 *Username:* {username}"
        )
        # Evangelism mentor always notified
        try:
            bot.send_message(MENTOR_EVANGELISM_ID, dm_report, parse_mode="Markdown")
        except Exception as e:
            print(f"Error notifying evangelism mentor: {e}")

        if specialist_id:
            try:
                bot.send_message(specialist_id, dm_report, parse_mode="Markdown")
            except Exception as e:
                print(f"Error notifying specialist mentor: {e}")

        # ── Confirm to user ──
        bot.send_message(
            chat_id,
            "✅ ተመዝግቧል! አማካሪ በቅርቡ ያነጋግርዎታል። እግዚአብሔር ይባርክዎ! 🙏\n\n"
            "ከዚህ በኋላ የምትልኩት ማንኛውም መልዕክት ወደ አማካሪ ቡድናችን ይደርሳል።",
            reply_markup=reply_keyboard
        )
        del user_states[chat_id]


# ─────────────────────────────────────────────
#  Bible study helpers
# ─────────────────────────────────────────────
def get_next_lesson_markup():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(
        "ቀጣዩን ቀን አሳየኝ (Next Day) ➡️", callback_data="next_bible_day"
    ))
    return markup


def start_bible_study(message):
    user_id = message.chat.id
    book    = "የዮሐንስ ወንጌል"
    db      = None
    try:
        db     = get_db_connection()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "SELECT chapter, teaching_content FROM study_content WHERE book_name = %s AND day_number = 1",
            (book,)
        )
        lesson = cursor.fetchone()

        if lesson:
            upsert_query = """
                INSERT INTO user_progress
                    (telegram_id, active_book, current_day, last_sent_at, subscription_status)
                VALUES (%s, %s, 1, NOW(), 'active')
                ON DUPLICATE KEY UPDATE
                    active_book = %s, current_day = 1,
                    last_sent_at = NOW(), subscription_status = 'active'
            """
            cursor.execute(upsert_query, (user_id, book, book))
            db.commit()
            text = f"📖 *{lesson['chapter']}*\n\n{lesson['teaching_content']}"
            bot.send_message(user_id, text, parse_mode="Markdown",
                             reply_markup=get_next_lesson_markup())
        else:
            bot.send_message(user_id, "⚠️ የጥናት ይዘቱ አልተገኘም። እባክዎ አስተዳዳሪውን ያነጋግሩ።")
    except Exception as e:
        print(f"DB Error in start_bible_study: {e}")
        bot.send_message(user_id, "⚠️ ችግር ተፈጥሯል። እባክዎ ቆይተው ይሞክሩ።")
    finally:
        if db and db.is_connected():
            cursor.close()
            db.close()


@bot.callback_query_handler(func=lambda call: call.data == "next_bible_day")
def handle_next_day(call):
    user_id = call.from_user.id
    db      = None
    try:
        db     = get_db_connection()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "SELECT active_book, current_day FROM user_progress WHERE telegram_id = %s",
            (user_id,)
        )
        user = cursor.fetchone()
        if not user:
            bot.answer_callback_query(call.id, "እባክዎ መጀመሪያ ጥናቱን ይጀምሩ።")
            return

        next_day = user['current_day'] + 1
        cursor.execute(
            "SELECT chapter, teaching_content FROM study_content WHERE book_name = %s AND day_number = %s",
            (user['active_book'], next_day)
        )
        content = cursor.fetchone()

        if content:
            cursor.execute(
                "UPDATE user_progress SET current_day = %s, last_sent_at = NOW() WHERE telegram_id = %s",
                (next_day, user_id)
            )
            db.commit()
            text = f"📖 *{content['chapter']}*\n\n{content['teaching_content']}"
            bot.send_message(user_id, text, parse_mode="Markdown",
                             reply_markup=get_next_lesson_markup())
            bot.edit_message_reply_markup(
                chat_id=user_id, message_id=call.message.message_id, reply_markup=None
            )
            bot.answer_callback_query(call.id)
        else:
            cursor.execute(
                "UPDATE user_progress SET subscription_status = 'completed' WHERE telegram_id = %s",
                (user_id,)
            )
            db.commit()
            bot.send_message(user_id, "🎉 እንኳን ደስ አሎት! የዮሐንስ ወንጌል ጥናትዎን አጠናቅቀዋል።")
            bot.edit_message_reply_markup(
                chat_id=user_id, message_id=call.message.message_id, reply_markup=None
            )
            bot.answer_callback_query(call.id)

    except Exception as e:
        print(f"Error in handle_next_day: {e}")
        bot.answer_callback_query(call.id, "⚠️ ችግር ተፈጥሯል። እባክዎ ቆይተው ይሞክሩ።")
    finally:
        if db and db.is_connected():
            cursor.close()
            db.close()


# ─────────────────────────────────────────────
#  Main message router (user-facing)
# ─────────────────────────────────────────────
@bot.message_handler(func=lambda message: True)
def check_button(message):
    # Ignore messages coming from the admin group
    if message.chat.id == ADMIN_GROUP_ID:
        return

    text    = message.text or ""
    chat_id = message.chat.id

    # ── If user has an active topic (i.e. already registered), relay freely ──
    if chat_id in user_topic_map and text not in (
        "ኢየሱስን እንደ ግል አዳኝ አድርጌ ለመቀበል", "በንሰሀ መመለስ እፈልጋለሁ",
        "ስለ ኢየሱስ ክርስቶስ በበለጠ ለማወቅ", "የመጽሐፍ ቅዱስ ጥናት እቅድ ለማግኘት",
        "አማካሪ ማግኘት እፈልጋለሁ", "ጥያቄ መጠየቅ እፈልጋለሁ", "በስህተት ነው የነካሁት",
        "Back to Main Menu",
    ):
        display = message.from_user.first_name or str(chat_id)
        relay_to_admin(chat_id, display, message)
        return

    # ── Menu buttons ──
    if text == "አማካሪ ማግኘት እፈልጋለሁ":
        start_mentor_request(message, "አማካሪ ማግኘት እፈልጋለሁ")

    elif text == "ጥያቄ መጠየቅ እፈልጋለሁ":
        start_mentor_request(message, "ጥያቄ መጠየቅ እፈልጋለሁ")

    elif text == "በንሰሀ መመለስ እፈልጋለሁ":
        start_mentor_request(message, "በንሰሀ መመለስ እፈልጋለሁ")

    elif text == "ስለ ኢየሱስ ክርስቶስ በበለጠ ለማወቅ":
        explain_jesus_text = (
            "ኢየሱስ ማነው? ወደ ሰላም የሚወስደውን መንገድ መረዳት!!\n\n"
            "1. ዓለማቀፋዊው እውነት\n"
            "ምንም ዓይነት አስተዳደግ፣ ሀብት ወይም የኑሮ ደረጃ ቢኖረን፣ እያንዳንዱ የሰው ልጅ "
            "ያንኑ መሠረታዊ ጥያቄ ይጠይቃል፦ 'ከሞት በኋላ ምን ይከሰታል?'\n\n"
            "2. ችግሩ፦ ኃጢአትና መለየት\n"
            "እግዚአብሔር የፈጠረን ከእርሱ ጋር ህብረት እንድናደርግ ነበር፤ እኛ ግን የራሳችንን "
            "መንገድ መረጥን። ሮሜ 6፡23 'የኃጢአት ደመወዝ ሞት ነው' ይላል።\n\n"
            "3. መፍትሄው፦ የኢየሱስ መስዋዕትነት\n"
            "ኢየሱስ ክርስቶስ ፍጹም ሕይወት ኖሮ፣ በመስቀል ላይ የእኛን ቦታ ተካ። ከሙታን ተነሳ።\n\n"
            "4. ምላሻችን ምን መሆን አለበት?\n"
            "• ንስሐ መግባት • ማመን • መቀበል\n\n"
            "ከእርሱ ጋር ለመቀጠል 'ኢየሱስን እንደ ግል አዳኝ አድርጌ ለመቀበል' ይጫኑ።\n\n"
            "❤️ ኢየሱስ ሁሉንም ይወዳል!!"
        )
        bot.send_message(chat_id, explain_jesus_text)

    elif text == "ኢየሱስን እንደ ግል አዳኝ አድርጌ ለመቀበል":
        accept_jesus_text = (
            "🙏 እንደ ግል አዳኝ እንዴት መቀበል ይችላሉ?\n\n"
            "1. ኃጢአተኛ መሆንዎን አምነው ይቀበሉ — ሮሜ 3:23\n"
            "2. ኢየሱስ ስለ ኃጢአትዎ እንደሞተ ይምኑ — ሮሜ 5:8\n"
            "3. በኢየሱስ ክርስቶስ ትንሳኤ ያምኑ — ዮሐንስ 11:25\n\n"
            "ማጠቃለያ ፀሎት:\n"
            "'ጌታ ሆይ አኔን ሰለወደድከኝ አመሰግናለሁ። ሃጥያተኛ መሆኔን አምናለሁ። "
            "ኢየሱስ በኔ ፈንታ መሞቱን፣ ሞትን ድል አድርጎ መነሳቱን አምናለሁ። "
            "ህይወቴን ተረከበኝ።'\n\n"
            "🎉 ይህንን ፀሎት ከልብ ከፀለዩ እንኳን ደስ አሎት! አሁን የእግዚአብሔር ልጅ ሆነዋል🎉\n\n"
            "ከክርስቶስ ጋር በሚያደርጉት ጉዞ የሚረዳዎት ጓደኛ ይፈልጋሉ?\n"
            "/yes - ጓደኛ እፈልጋለሁ\n"
            "/no  - ጓደኛ አልፈልጋም"
        )
        bot.send_message(chat_id, accept_jesus_text)

    elif text == "የመጽሐፍ ቅዱስ ጥናት እቅድ ለማግኘት":
        markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.row("የዮሐንስ ወንጌል (Gospel of John)")
        markup.row("Commmon Questions on christianity")
        markup.row("Back to Main Menu")
        bot.send_message(chat_id, "የትኛውን ጥናት መጀመር ይፈልጋሉ?", reply_markup=markup)

    elif text == "Commmon Questions on christianity":
        common_markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        common_markup.row("Common Muslim questions about Christianity?")
        common_markup.row("Common Only Jesus questions about Christianity")
        common_markup.row("Back to Main Menu")
        bot.send_message(chat_id, "የትኛውን ጥናት መጀመር ይፈልጋሉ?", reply_markup=common_markup)

    elif text == "Common Muslim questions about Christianity?":
        muslim_markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        muslim_markup.row("እኩል ስልጣን ካላቸው በ ዩሐ5 ለምን አብ ከእኔ ይበልጣል አለ?")
        muslim_markup.row("ሥላሴ ሚለው ቃል መፅሐፍ ቅዱስ ላይ አለ ወይ?")
        muslim_markup.row("አምላክ እንዴት ወደ አምላክ ይፀልያል?")
        muslim_markup.row("አምላክ እንዴት ይወልዳል?")
        muslim_markup.row("ስንት አምላክ ነው ያላቹ?")
        muslim_markup.row("አንድ አምላክ እንዴት የአንድ አምላክ ልጅ ይባላል?")
        muslim_markup.row("Back to Main Menu")
        bot.send_message(chat_id, "የትኛውን ጥናት መጀመር ይፈልጋሉ?", reply_markup=muslim_markup)

    elif text == "Common Only Jesus questions about Christianity":
        only_jesus_markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        only_jesus_markup.row("የውሃ ጥምቀት በኢየሱስ ክርስቶስ ስም")
        only_jesus_markup.row("ትምህርተ ሥላሴና የአረማውያኑ")
        only_jesus_markup.row("የኦንሊ ጂሰሱ_አብ ወልድና መንፈስ ቅዱስ")
        only_jesus_markup.row("አብ ፣ ወልድና መንፈስ ቅዱስ የተለያዩ አካላት አይደሉምን")
        only_jesus_markup.row("Back to Main Menu")
        bot.send_message(chat_id, "የትኛውን ጥናት መጀመር ይፈልጋሉ?", reply_markup=only_jesus_markup)

    elif text in STUDY_FILES_MAP:
        try:
            bot.send_chat_action(chat_id, 'upload_document')
            bot.send_document(chat_id, STUDY_FILES_MAP[text], caption=f"📄 {text}")
        except Exception as e:
            bot.send_message(chat_id, "⚠️ ፋይሉን ማግኘት አልተቻለም። እባክዎ አማካሪ ያነጋግሩ።")
            print(f"Transfer Error: {e}")

    elif text == "Back to Main Menu":
        bot.send_message(chat_id, "ዋና ማውጫ", reply_markup=reply_keyboard)

    elif text == "የዮሐንስ ወንጌል (Gospel of John)":
        start_bible_study(message)

    elif text == "በስህተት ነው የነካሁት":
        bot.send_message(
            chat_id,
            "ችግር የለም! 😊 አማራጮቹን እንደገና ለማየት /start ይጫኑ።",
            reply_markup=reply_keyboard
        )

    else:
        # Unknown text from a non-registered user — just show menu
        bot.send_message(
            chat_id,
            "አልገባኝም። እባክዎ ከታች ካሉት አማራጮች አንዱን ይጫኑ ወይም /start ይጠቀሙ",
            reply_markup=reply_keyboard
        )


# ─────────────────────────────────────────────
#  Startup
# ─────────────────────────────────────────────
def _webhook_config_from_url(webhook_url):
    parsed = urlparse(webhook_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("WEBHOOK_URL must be a valid HTTP(S) URL")
    path = parsed.path.strip("/")
    if not path:
        raise ValueError("WEBHOOK_URL must include a non-root path")
    return f"{parsed.scheme}://{parsed.netloc}/{path}/", f"{path}/"


def start_bot():
    if BOT_MODE == "webhook":
        if not WEBHOOK_URL:
            raise RuntimeError("WEBHOOK_URL is required when BOT_MODE=webhook")
        webhook_url, webhook_path = _webhook_config_from_url(WEBHOOK_URL)
        listen_port = int(os.getenv("PORT", "8443"))
        print(f"Starting bot in webhook mode: {webhook_url}")
        try:
            bot.run_webhooks(
                listen="0.0.0.0",
                port=listen_port,
                url_path=webhook_path,
                webhook_url=webhook_url,
                drop_pending_updates=False,
            )
        except ImportError as exc:
            raise RuntimeError(
                "Webhook mode requires fastapi, uvicorn, and starlette."
            ) from exc
        return

    if BOT_MODE != "polling":
        print(f"Unknown BOT_MODE='{BOT_MODE}', defaulting to polling")

    print("Starting background health-check server...")
    threading.Thread(target=run_web_server, daemon=True).start()

    print("Starting bot in polling mode...")
    bot.remove_webhook()
    bot.infinity_polling()


if __name__ == "__main__":
    start_bot()
