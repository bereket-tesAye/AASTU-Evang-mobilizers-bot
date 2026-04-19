import os
import telebot
from telebot.types import KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv 

from telebot.types import KeyboardButton, ReplyKeyboardMarkup
from dotenv import load_dotenv  
from urllib.parse import urlparse

# DATABASE CONFIG
import mysql.connector
from datetime import datetime

# DATABASE CONNECTION
def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"), 
        password=os.getenv("DB_PASSWORD"), 
        database=os.getenv("DB_NAME", "EvangBibleStudyPlan"),
        charset='utf8mb4'
    )

# scheduler for daily messages
import mysql.connector
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

load_dotenv()

# bot tokens
API_KEY = os.getenv("TELEGRAM_BOT_TOKEN")
bot = telebot.TeleBot(API_KEY)
MENTOR_CHAT_ID = 8067334396


BOT_MODE = os.getenv("BOT_MODE", "polling").strip().lower()
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip()


def _webhook_config_from_url(webhook_url):
    parsed = urlparse(webhook_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("WEBHOOK_URL must be a valid HTTP(S) URL")
    path = parsed.path.strip("/")
    if not path:
        raise ValueError("WEBHOOK_URL must include a non-root path, e.g. /telegram-webhook")
    normalized_url = f"{parsed.scheme}://{parsed.netloc}/{path}/"
    return normalized_url, f"{path}/"


def send_daily_lessons():
    db = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        
        # Select users due for next lesson (24 hour check)
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
            
            # Fetch content
            fetch_query = "SELECT chapter, teaching_content FROM study_content WHERE book_name = %s AND day_number = %s"
            cursor.execute(fetch_query, (user['active_book'], next_day))
            content = cursor.fetchone()

            if content:
                text = f"📖 *{content['chapter']}*\n\n{content['teaching_content']}"
                try:
                    bot.send_message(user['telegram_id'], text, parse_mode="Markdown")
                    
                    # Update progress
                    update_query = "UPDATE user_progress SET current_day = %s, last_sent_at = NOW() WHERE telegram_id = %s"
                    cursor.execute(update_query, (next_day, user['telegram_id']))
                    db.commit()
                except Exception as e:
                    print(f"Error sending to {user['telegram_id']}: {e}")
            else:
                # Study completed
                cursor.execute("UPDATE user_progress SET subscription_status = 'completed' WHERE telegram_id = %s", (user['telegram_id'],))
                db.commit()
                bot.send_message(user['telegram_id'], "🎉 እንኳን ደስ አሎት! የ21 ቀን የዮሐንስ ወንጌል ጥናትዎን አጠናቅቀዋል።")

    except Exception as e:
        print(f"Scheduler Error: {e}")
    finally:
        if db and db.is_connected():
            cursor.close()
            db.close()

# Start Scheduler (Checks every 60 minutes)
scheduler = BackgroundScheduler()
scheduler.add_job(send_daily_lessons, 'interval', minutes=60)
scheduler.start()

# FIX 2: MENTOR_CHAT_ID should be integer, not string
MENTOR_CHAT_ID = 8067334396  # Remove quotes

waiting_for_mentor_username = {}

# create reply keyboard
reply_keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)

# add the buttons
reply_keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
reply_keyboard.row("ኢየሱስን እንደ ግል አዳኝ አድርጌ ለመቀበል")
reply_keyboard.row("በንሰሀ መመለስ እፈልጋለሁ") #give simple prayer and assign mentor
reply_keyboard.row("ስለ ኢየሱስ ክርስቶስ በበለጠ ለማወቅ")
reply_keyboard.row("የመጽሐፍ ቅዱስ ጥናት እቅድ ለማግኘት")
reply_keyboard.row("አማካሪ ማግኘት እፈልጋለሁ") #assign mentor
reply_keyboard.row("ጥያቄ መጠየቅ እፈልጋልሁ") #assign mentor
reply_keyboard.row("በስህተት ነው የነካሁት")

# counseling bot replacement
counseling_bot = "t.me/AASTU_Anony_Counseling_bot" 

# Set up bot commands menu in Telegram
bot.set_my_commands([
    telebot.types.BotCommand('start', 'Start the bot'),
    telebot.types.BotCommand('help', 'Learn what this bot can do'),
    telebot.types.BotCommand('chat_history', 'View chat history'),
    telebot.types.BotCommand('yes', 'I would like a mentor\'s guidance '),
    telebot.types.BotCommand('no', 'I do not need a mentor\'s guidance'),
])
cancel_keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
cancel_keyboard.add(KeyboardButton("❌ ሰርዝ (Cancel)"))

# Keyboard for Sex selection with Cancel
sex_keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
sex_keyboard.row("Male", "Female")
sex_keyboard.row("❌ ሰርዝ (Cancel)")

STUDY_FILES_MAP = {
    "እኩል ስልጣን ካላቸው በ ዩሐ5 ለምን አብ ከእኔ ይበልጣል አለ?" : "BQACAgQAAyEFAATkiwQeAAMUacTbMcmwvG88u9injn2s_JNg3ZIAAhMdAAIHdihST2mm2MGw0qo6BA",
    
    "ሥላሴ ሚለው ቃል መፅሐፍ ቅዱስ ላይ አለ ወይ?" : "BQACAgQAAyEFAATkiwQeAAMNacTbMaZk4sg1CaPu9ZZ6Dfkio8kAAgwdAAIHdihSTwX9MvVYtmM6BA",
    
    "አምላክ እንዴት ወደ አምላክ ይፀልያል?" : "BQACAgQAAyEFAATkiwQeAAMQacTbMRzZ4yCmC2JPLW7iwLsOHoAAAg8dAAIHdihSZqqDCB2OQhU6BA",
    
    "አምላክ እንዴት ይወልዳል?" : "BQACAgQAAyEFAATkiwQeAAMRacTbMed9vEegLIPBPTQoILT--40AAhAdAAIHdihS0ds89QKq1lA6BA",
    
    "ስንት አምላክ ነው ያላቹ?" : "BQACAgQAAyEFAATkiwQeAAMOacTbMUIqjlYCQCvzKuIkmaecm5QAAg0dAAIHdihS8mG5Xi5-0uY6BA",
    
    "አንድ አምላክ እንዴት የአንድ አምላክ ልጅ ይባላል?" : "BQACAgQAAyEFAATkiwQeAAMTacTbMdKoMbmiUWz0Rd4WMAWby9QAAhIdAAIHdihSoaptNhjhh-A6BA",
    
    "የውሃ ጥምቀት በኢየሱስ ክርስቶስ ስም" : "BQACAgQAAyEFAATkiwQeAAMWacTbMS3oCKVxFvlfMYJiBAq8nEIAAhUdAAIHdihSJ9OUTPAO0ao6BA",
    
    "ትምህርተ ሥላሴና የአረማውያኑ" : "BQACAgQAAyEFAATkiwQeAAMPacTbMXJsAmzgTpc-i8sQsFyPXJIAAg4dAAIHdihSyaA5H27yGsM6BA",
    
    "የኦንሊ ጂሰሱ_አብ ወልድና መንፈስ ቅዱስ" : "BQACAgQAAyEFAATkiwQeAAMVacTbMbVLit8MP8ZBqN7W5fD4pfMAAhQdAAIHdihSk2HT3OjY4ic6BA",
    
    "አብ ፣ ወልድና መንፈስ ቅዱስ የተለያዩ አካላት አይደሉምን" : "BQACAgQAAyEFAATkiwQeAAMSacTbMSGtXjsgRvk8DAQo4ud2cRwAAhEdAAIHdihS7tw9h3oYsWs6BA"
}


def get_next_lesson_markup():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("ቀጣዩን ቀን አሳየኝ (Next Day) ➡️", callback_data="next_bible_day"))
    return markup

def start_bible_study(message):
    user_id = message.chat.id
    book = "የዮሐንስ ወንጌል"
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    try:
        # Fetch Day 1 specifically
        cursor.execute("SELECT chapter, teaching_content FROM study_content WHERE book_name = %s AND day_number = 1", (book,))
        lesson = cursor.fetchone()

        if lesson:
            # Reset user to Day 1 in the progress table
            upsert_query = """
            INSERT INTO user_progress (telegram_id, active_book, current_day, last_sent_at, subscription_status)
            VALUES (%s, %s, 1, NOW(), 'active')
            ON DUPLICATE KEY UPDATE active_book = %s, current_day = 1, last_sent_at = NOW(), subscription_status = 'active'
            """
            cursor.execute(upsert_query, (user_id, book, book))
            db.commit()

            # Send text + Inline Button
            text = f"📖 *{lesson['chapter']}*\n\n{lesson['teaching_content']}"
            bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=get_next_lesson_markup())
        else:
            bot.send_message(user_id, "⚠️ የጥናት ይዘቱ አልተገኘም። እባክዎ አስተዳዳሪውን ያነጋግሩ።")
    finally:
        cursor.close()
        db.close()

@bot.callback_query_handler(func=lambda call: call.data == "next_bible_day")
def handle_next_day(call):
    user_id = call.from_user.id
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    try:
        # Find current progress
        cursor.execute("SELECT active_book, current_day FROM user_progress WHERE telegram_id = %s", (user_id,))
        user = cursor.fetchone()

        if not user:
            bot.answer_callback_query(call.id, "እባክዎ መጀመሪያ ጥናቱን ይጀምሩ።")
            return

        next_day = user['current_day'] + 1
        
        # Fetch the next day's content
        cursor.execute(
            "SELECT chapter, teaching_content FROM study_content WHERE book_name = %s AND day_number = %s", 
            (user['active_book'], next_day)
        )
        content = cursor.fetchone()

        if content:
            # Update DB to the new day
            cursor.execute(
                "UPDATE user_progress SET current_day = %s, last_sent_at = NOW() WHERE telegram_id = %s", 
                (next_day, user_id)
            )
            db.commit()

            # Send next lesson
            text = f"📖 *{content['chapter']}*\n\n{content['teaching_content']}"
            bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=get_next_lesson_markup())
            
            # CLEANUP: Remove button from the message the user just clicked
            bot.edit_message_reply_markup(chat_id=user_id, message_id=call.message.message_id, reply_markup=None)
            bot.answer_callback_query(call.id)
        else:
            # End of study reached
            cursor.execute("UPDATE user_progress SET subscription_status = 'completed' WHERE telegram_id = %s", (user_id,))
            db.commit()
            bot.send_message(user_id, "🎉 እንኳን ደስ አሎት! የዮሐንስ ወንጌል ጥናትዎን አጠናቅቀዋል።")
            bot.edit_message_reply_markup(chat_id=user_id, message_id=call.message.message_id, reply_markup=None)
            bot.answer_callback_query(call.id)

    except Exception as e:
        print(f"Error: {e}")
    finally:
        cursor.close()
        db.close()

# Welcome page on the bot
@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = """🙏 እንኳን ወደ AASTU Evang Mobilizers Team Bot በሰላም መጡ!

ይህ ቦት ምን ሊያደርግ ይችላል?

📋 ትዕዛዞች (Commands):
/start - ይህን የእንኳን ደህና መጡ መልዕክት ያሳያል
/help - ይህ ቦት ምን መስራት እንደሚችል ያብራራል

👇 ወይም ከታች ካሉት አማራጮች አንዱን ይምረጡ፦:"""
    
    # this will reply keyboard menu
    bot.reply_to(message, welcome_text, reply_markup=reply_keyboard)

@bot.message_handler(commands=['help'])
def show_help(message):
    help_text = """🤖 ይህ ቦት ምን ሊያደርግ ይችላል?

🤗 ይህ ቦት ኢየሱስን በበለጠ እንዲያውቁ ይረዳዎታል።

📋 የሚገኙ ትዕዛዞች (Commands):
/start - የአማራጭ ቁልፎችን የያዘ የእንኳን ደህና መጡ መልዕክት ያሳያል
/help - ይህን የእገዛ መልዕክት ያሳያል

👇 ምርጫዎች(ለመመልከት /start ን ይጫኑ)፦
• "ኢየሱስን እንደ ግል አዳኝ አድርጌ ለመቀበል" - ኢየሱስ ክርስቶስን የግል አዳኝህ አድርገው መቀበል ከፈለጉ እንዲሁም የሚያናግሮት ሰው ለማግኘት ይህን ተጫኑ።

• "በንሰሀ መመለስ እፈልጋለሁ" - ቀደም ብለው ኢየሱስ ክርስቶስን ያውቁት ከነበረና በተለያዩ ምክንያቶች ከእርሱ ርቀው ከሆነ፣ ይህንን በመጫን መንፈሳዊ መካሪ ማግኘት ይችላሉ።

• "ስለ ኢየሱስ ክርስቶስ በበለጠ ለማወቅ" - ስለ ኢየሱስ ሕይወትና አገልግሎት የበለጠ ለማወቅ ይህንን ይጫኑ።

• "የመጽሐፍ ቅዱስ ጥናት እቅድ ለማግኘት" - የተለያዩ የመጽሐፍ ቅዱስ ጥናት እቅዶችንና እና ክርስትና ላይ ሚነሱ ጥያቄዎች ከነመልሳቸው እና ግብዓቶችን ያገኛሉ ።

• "አማካሪ ማግኘት እፈልጋለሁ" - በማንኛውም ርዕስ ላይ የሚያናግሩት ሰው ከፈለጉ ይህንን ይጫኑ።

• "ጥያቄ መጠየቅ እፈልጋልሁ" - ለማንኛውም ዓይነት ሃይማኖታዊ ጥያቄ ወይም ውይይት ይህንን ቁልፍ ይጠቀሙ።

• "በስህተት ነው የነካሁት" - ትዕዛዙን ሰርዘው ወደ ዋናው ማውጫ ለመመለስ።

💡 አጠቃቀም፦
ቁልፎቹን ለማየት /start ብለው ይጻፉ
ፈጣን እርዳታ ለማግኘት የመረጡትን ቁልፍ ይጫኑ

ማንኛውንም የአመካሪ ምደባ ሂደት ለማቋረጥ 'cancel' ብለው ይጻፉ።

❤️ ኢየሱስ ሁሉንም ይወዳል!!"""    
    bot.reply_to(message, help_text, reply_markup=reply_keyboard)

user_states = {}

def start_mentor_request(message, source):
    chat_id = message.chat.id
    user_states[chat_id] = {
        "step": "full_name",
        "source" : source
        }
    if "አማካሪ ማግኘት እፈልጋለሁ" in source:
        msg = """እኛን ለማግኘት ስለፈለጉ እናመሰግናለን🙏\nለማቋረጥ 'cancel' ብለው ይጻፉ።
\nለመቀጠል እባክዎ ሙሉ ስምዎን ያስገቡ፦"""

    elif "በንሰሀ መመለስ እፈልጋለሁ" in source:
        msg = """🙏 በንሰሀ ለመመለስ መወሰንዎ ትልቅ ደስታ ነው! 

    በኃጢአታችን ብንናዘዝ ኃጢአታችንን ይቅር ሊለን ከዓመፃም ሁሉ ሊያነጻን የታመነና ጻድቅ ነው።
            - 1ኛ የዮሐንስ መልእክት 1 : 9

ይህንን አጭር ፀሎት ይፀልዩ፦

        'አምላክ ሆይ፣
በእኔ ምትክ እንዲቆምልኝና የሚገባኝን ቁጣህን በእርሱ ላይ ስለተቀበለልኝ ስለ ልጅህ አመሰግንሃለሁ።በክርስቶስ የመስቀል ላይ ሥራ ምክንያት በዙፋንህ ፊት ይቅር የተባልኩና የጸደቅኩ ሆኜ እቆማለሁ። 

ምንም እንኳ ከኃጢአቴ ይቅር የተባልኩ ብሆንም፣ ይህ ማለት ግን በኃጢአት ውስጥ አልወድቅም ማለት አይደለም።ሥጋዬ ከመንገድህ ሊያርቀኝ ይፈልጋል፤ አንዳንዴም በፈተናው ተሸንፌ ትእዛዝህን እጥሳለሁ።
ከአንተ ከመሸሽ ይልቅ፣ ንስሐ መግባትን እመርጣለሁ።

መንፈስ ቅዱስ ሆይ፣ ቶሎ ንስሐ እንድገባና ወደ ጸጋው ዙፋን እንድሮጥ እርዳኝ።አባት ሆይ፣ በየማለዳው ስለሚታደሰው ምሕረትህ አመሰግንሃለሁ።ምሕረትህን እንደ ቀላል ነገር እንዳልመለከተው፤ ይልቁንም ሁልጊዜ በፊትህ በታማኝነት መመላለስንና አለመታዘዜን በንስሐ መናዘዝን ልማዴ ላድርገው።አንተ እጅግ ታማኝ አባት ነህ፤ እጆችህን ዘርግተህ ትጠብቀኛለህ።

ለምትሰጠኝ ብርቱ የንስሐ ዕድሎች ሁሉ አመሰግንሃለሁ።
በኢየሱስ ስም፣ አሜን።' \nለማቋረጥ 'cancel' ብለው ይጻፉ።\nለመቀጠል እባክዎ ሙሉ ስምዎን ያስገቡ፦"""
    
    elif "ኢየሱስን እንደ ግል አዳኝ አድርጌ ለመቀበል"in source:
        msg = "🙏 ኢየሱስን እንደ ግል አዳኝ ለመቀበል የመወሰንዎ ትልቅ ደስታ ነው! \nለማቋረጥ 'cancel' ብለው ይጻፉ።\nለመቀጠል እባክዎ ሙሉ ስምዎን ያስገቡ፦"
    else:
        msg = "🙏 ጥያቄ መጠየቅ ስለፈለጉ እናመሰግናለን🙏\nለማቋረጥ 'cancel' ብለው ይጻፉ።\nለመቀጠል እባክዎ ሙሉ ስምዎን ያስገቡ፦"
    bot.send_message(
        message.chat.id, msg)

@bot.message_handler(commands=['no'])
def no_mentor_assign(message):
    bot.send_message(message.chat.id,"""ችግር የለም😊! ሃሳብዎን ከቀየሩ በማንኛውም ጊዜ "/yes" የሚለውን መጫን ይችላሉ፤ እንዲሁም የመጽሐፍ ቅዱስ ጥናት እቅዱን ማየት ይችላሉ👇።
                        እግዚአብሔር ይባርክዎ!  🙏"""
    )

@bot.message_handler(func=lambda message: message.chat.id in user_states)
def process_mentor_steps(message):
    chat_id = message.chat.id
    text = message.text.strip()
    
    # --- UNIVERSAL CANCEL CHECK ---
    # This triggers regardless of if they are at the Name, Sex, or Username stage
    if text == "❌ ሰርዝ (Cancel)" or text.lower() == "cancel":
        del user_states[chat_id]
        bot.send_message(
            chat_id, 
            "ምዝገባው ተሰርዟል። ወደ ዋናው ማውጫ ተመልሰዋል። 🙏", 
            reply_markup=reply_keyboard # Returns them to the main menu
        )
        return

    state = user_states[chat_id]
    
    # --- STAGE 1: FULL NAME ---
    if state["step"] == "full_name":
        state["full_name"] = text
        state["step"] = "sex"
        bot.send_message(chat_id, "👉 ፆታዎን ያስገቡ (Male / Female):", reply_markup=sex_keyboard)

    # --- STAGE 2: SEX ---
    elif state["step"] == "sex":
        if text.lower() not in ["male", "female"]:
            bot.send_message(chat_id, "❌ እባክዎ Male ወይም Female ብቻ ያስገቡ።", reply_markup=sex_keyboard)
            return
        state["sex"] = text
        state["step"] = "username"
        bot.send_message(chat_id, "👉 የቴሌግራም Username ያስገቡ (ለምሳሌ @yourname)፦", reply_markup=cancel_keyboard)

    # --- STAGE 3: USERNAME --- 
    elif state["step"] == "username":
            username = text if text.startswith('@') else '@' + text
            
            # Build the report
            mentor_report = (
                f"🚨 **New Mentor Request**\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📌 **From:** {state['source']}\n"
                f"👤 **Name:** {state['full_name']}\n"
                f"⚧ **Sex:** {state['sex']}\n"
                f"📱 **Username:** {username}\n"
                f"🆔 **User ID:** `{chat_id}`\n"
                f"━━━━━━━━━━━━━━━━━━━━"
            )
            
            # Send to the mentor group/admin
            bot.send_message(MENTOR_CHAT_ID, mentor_report, parse_mode="Markdown")
            
            # Confirm to the user
            bot.send_message(chat_id, "✅ ተመዝግቧል! አማካሪ በቅርቡ ያነጋግርዎታል። እግዚአብሔር ይባርክዎ! 🙏", reply_markup=reply_keyboard)
            del user_states[chat_id]        
            
@bot.message_handler(func=lambda message: True)
def check_button(message):
    # FIX 5: Remove the incorrect if/elif inside "accept jesus" handler
    if message.text == "አማካሪ ማግኘት እፈልጋለሁ":
        general_mentor = """"""
        start_mentor_request(message, "አማካሪ ማግኘት እፈልጋለሁ")

    elif message.text == "ጥያቄ መጠየቅ እፈልጋልሁ":
        start_mentor_request(message, "ጥያቄ መጠየቅ እፈልጋልሁ")

    elif message.text == "በንሰሀ መመለስ እፈልጋለሁ":
        start_mentor_request(message, "በንሰሀ መመለስ እፈልጋለሁ")
    
    elif message.text == "/yes":
        start_mentor_request(message, "ኢየሱስን እንደ ግል አዳኝ አድርጌ ለመቀበል")

    elif message.text == "ስለ ኢየሱስ ክርስቶስ በበለጠ ለማወቅ":
        explain_jesus_text = """ኢየሱስ ማነው? ወደ ሰላም የሚወስደውን መንገድ መረዳት!!

    1. ዓለማቀፋዊው እውነት

ምንም ዓይነት አስተዳደግ፣ ሀብት ወይም የኑሮ ደረጃ ቢኖረን፣ እያንዳንዱ የሰው ልጅ ያንኑ መሠረታዊ ጥያቄ ይጠይቃል፦ "ከሞት በኋላ ምን ይከሰታል?" መጽሐፍ ቅዱስ "መንግስተ ሰማያት" የሚባል የዘላለም ሰላም ስፍራ ቃል ይገባል፤ ነገር ግን በአሁኑ ወቅት ከእርሱ ተለይተን የምንገኝበትንም ምክንያት ያብራራል።

    2. ችግሩ፦ ኃጢአትና መለየት

እግዚአብሔር የፈጠረን ከእርሱ ጋር ህብረት እንድናደርግ ነበር፤ እኛ ግን የራሳችንን መንገድ መረጥን። ይህ "ኃጢአት" መጥፎ ነገር ማድረግ ብቻ አይደለም፤ ይልቁንም ከእግዚአብሔር ተለይቶ በራስ የመመራት ልብ ነው። እግዚአብሔር ፍጹም ቅዱስ ስለሆነ፣ ኃጢአትን በፊቱ አይፈቅድም። ሮሜ 6፡23 "የኃጢአት ደመወዝ ሞት ነው" በማለት ያስጠነቅቀናል። በራሳችን ጥረት የጠፋን ነን።

    3. መፍትሄው፦ የኢየሱስ መስዋዕትነት

እኛ ወደ እግዚአብሔር መድረስ ስላልቻልን፣ እግዚአብሔር ወደ እኛ ወረደ። ኢየሱስ ክርስቶስ፣ ፍጹም አምላክና ፍጹም ሰው በመሆን፣ እኛ መኖር ያልቻልነውን ፍጹም ሕይወት ኖረ። ከዚያም በመስቀል ላይ የእኛን ቦታ ተካ።
    • መከራው፦ የእኛን ውርደትና ሕመም ተቀበለ።
    • ሞቱ፦ ለእግዚአብሔር ፍትህ ያለብንን "የሕግ ዕዳ" ከፈለልን።
    • ትንሳኤው፦ አዲስ ሕይወት የመስጠት ሥልጣን እንዳለው በማረጋገጥ ከሙታን ተነሳ።

    4. ምላሻችን ምን መሆን አለበት?

ስለ ኢየሱስ ማወቅና ኢየሱስን በግል ማወቅ አንድ አይደሉም። ከእርሱ ጋር ግንኙነት እንዲኖርዎትና የመንግስተ ሰማያትን እርግጠኝነት ለማግኘት መጽሐፍ ቅዱስ ሦስት እርምጃዎችን ይጠቁማል፦
    • ንስሐ መግባት፦ ለራስ ከመኖር ተመልሰው ወደ እግዚአብሔር ፊት መቅረብ።
    • ማመን፦ የኢየሱስ ሞት በግል ለእርስዎ እንደሆነ መታመን።
    • መቀበል፦ ነፃ የሆነውን የድነት (የደህንነት) ስጦታ መቀበል። ይህ በበጎ ሥራ የሚገኝ ሳይሆን በእምነት የሚቀበሉት ነው።

ከእየሱስ ጋር በዘላቂነት ህብረት ማድረግ እሚፈልጉ ከሆነ 
"ኢየሱስን እንደ ግል አዳኝ አድርጌ ለመቀበል" የሚለውን ቁልፍ ይጫኑ።

ተጨማሪ መረጃ👇
https://www.churchofjesuschrist.org/comeuntochrist/believe/jesus/life-and-mission-of-jesus-christ

                         ❤️ ኢየሱስ ሁሉንም ይወዳል!!"""

        bot.send_message(message.chat.id, explain_jesus_text)

    elif message.text == "ኢየሱስን እንደ ግል አዳኝ አድርጌ ለመቀበል":
        accept_jesus_text = """🙏 እንደ ግል አዳኝ መቀበል እንዴት መቀበል ይችላሉ?
        
        1. ኃጢአተኛ መሆንዎን አምነው ይቀበሉ 
“ሁሉ ኃጢአትን ሠርተዋልና የእግዚአብሔርም ክብር ጎድሎአቸዋል”
        - ሮሜ 3:23

ኀጢያት የእግዚአብሔር ተዛዝ ላይ ማመጽ ነው። በዚሀም መሰረት መጽሐፍ ቅዱስ አንደሚያሰረዳን አኛ ሁላችን ኀጢያተኞች ነን። ታዲያ አንድ ሰው በሽተኛ መሆኑን አመኖ መቀበሉ መድሃኒት ለማገኘነት የመጀመሪያው ደረጃ ነው።ሰለዚህ አርሶም በዚች ሰዓት ሃቲያተኛ መሆኖን አምነው የሚከተለውን ፀሎት አንዲፀልዩ አናበረታታለን።

“ጌታ ሆይ እኔን ሰላገኘኸኝ አመሰግናለው ፥ አባት አግዚአብሔር ሆይ ደግሞ አኔ ካንተ መንገድ የራኩኝ ፥ በጨለማ አየተመላለስኩ ያለው ሰው ፥ አሁን በገልጥ ሃጥያተኛ መሆኔን አምናለው።” 

        2. ኢየሱስ ስለ ኃጢአትዎ እንደሞተ ይምኑ
“ነገር ግን ገና ኃጢአተኞች ሳለን ክርስቶስ ስለ እኛ ሞቶአልና እግዚአብሔር ለእኛ ያለውን የራሱን ፍቅር ያስረዳል።”
        - ሮሜ 5:8

መጽሀፍ ቅድስ አግዚአብሔር ኀጢያትን ሳይቀጣ አንደማያልፍ በገልጽ ይነገረናል(ናሆም 1፥3) ነገር ገን አግዚአብሔር እኛን እጅግ በጣም ስለሚወደን አንድ ልጁን ስለበደላችን አራሱ ተቀጣልን። ሸክማችንን ሁሉ ተሸክሞ በመስቀል ሞቶ ተቀጣልን። ይህ ፍቅር ልንረዳው ከምንችለው በላይ ትልቅ ነው።

ስለዚህ አየሱስ ሰለኛ ኀጢያት መሞቱን በማመን ሚከተለውን ፀሎት አንዲፀልዩ አናበረታታለን።

“ጌታ ሆይ አኔን ሰለወደድከኝ አመሰግናለሁ ደግሞም ለኔ ኀጢያት በኔ ቦታ ሰለተቀጣህልኝ አመሰግናለሁ። የአግዚአብሔር ልጅ እየሱስ በኔ ፈንታ መሞትህን አምናለሁ።”

        3. በኢየሱስ ክርስቶስ ትንሳኤ ማመን
“ኢየሱስም። ትንሣኤና ሕይወት እኔ ነኝ፤ የሚያምንብኝ ቢሞት እንኳ ሕያው ይሆናል፤”
        - ዮሐንስ 11:25

ያለ ትንሳኤ፣ ሞት አሁንም የመጨረሻው አሸናፊ ይሆን ነበር። ኢየሱስ ግን ትንሳኤ ስለሆነ፣ እኛን ከመቃብር የማውጣት ሥልጣን አለው። ትንሳኤው የኃጢአታችን ዕዳ ሙሉ በሙሉ መከፈሉን የሚያረጋግጥ የእግዚአብሔር 'ደረሰኝ' (ማረጋገጫ) ነው። በዮሐንስ 11:25 ላይ እንደተመለከተው፣ ሕይወት ሊገኝ የቻለው እርሱ የሞት መንስኤ የሆነውን ኃጢአትን ድል ስለነሳው ነው።

        ማጠቃለያ ፀሎት

"ጌታ ሆይ አኔን ሰለወደድከኝ አመሰግናለሁ። አሁን በገልጥ ሃጥያተኛ መሆኔን አምናለሁ። ደግሞም ለኔ ኀጢያት በኔ ቦታ ሰለተቀጣህልኝ አመሰግናለሁ ፣ የአግዚአብሔር ልጅ እየሱስ በኔ ፈንታ መሞትን ሞትን ድል አድርገህ በሶስተኛ ቀን መነሳህን አምናለሁ። ከእንግዲህ ወዲ ያንተ ልጅ ሆኜ ካንተ ጋር ህብረት እያደረኩ መኖር እፈልጋለሁ። አለምን እና ሰይጣንን ክዳለሁ ፣ ህይወቴን ተረከበኝ።"
            
🎉ይህንን ፀሎት ከልብ ከፀለዩ እንኳን ደስ አሎት አሁን የእግዚአብሔር ልጅ ሆነዋል🎉።

ከክርስቶስ ጋር በሚያደርጉት ጉዞ የሚያማክሮት እና የሚረዳዎት ጓደኛ ይፈልጋሉ?
        /yes - ጓደኛ እፈልጋልሁ
        /no - ጓደኛ አልፈልጋም
"""

        bot.send_message(message.chat.id, accept_jesus_text)

    elif message.text == "የመጽሐፍ ቅዱስ ጥናት እቅድ ለማግኘት":
        markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.row("የዮሐንስ ወንጌል (Gospel of John)")
        markup.row("Commmon Questions on christianity")
        markup.row("Back to Main Menu")
        bot.send_message(message.chat.id, "የትኛውን ጥናት መጀመር ይፈልጋሉ?", reply_markup=markup)

    elif message.text == "Commmon Questions on christianity":
        common_markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        common_markup.row("Common Muslim questions about Christianity?")
        common_markup.row("Common Only Jesus questions about Christianity")
        common_markup.row("Back to Main Menu")
        bot.send_message(message.chat.id, "የትኛውን ጥናት መጀመር ይፈልጋሉ?", reply_markup=common_markup)
    
    elif message.text == "Common Muslim questions about Christianity?":
        muslim_markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        muslim_markup.row("እኩል ስልጣን ካላቸው በ ዩሐ5 ለምን አብ ከእኔ ይበልጣል አለ?")# check
        muslim_markup.row("ሥላሴ ሚለው ቃል መፅሐፍ ቅዱስ ላይ አለ ወይ?")# check
        muslim_markup.row("አምላክ እንዴት ወደ አምላክ ይፀልያል?")# check
        muslim_markup.row("አምላክ እንዴት ይወልዳል?") # check
        muslim_markup.row("ስንት አምላክ ነው ያላቹ?")# check
        muslim_markup.row("አንድ አምላክ እንዴት የአንድ አምላክ ልጅ ይባላል?")# check
        muslim_markup.row("Back to Main Menu")
        bot.send_message(message.chat.id, "የትኛውን ጥናት መጀመር ይፈልጋሉ?", reply_markup=muslim_markup)

    elif message.text == "Common Only Jesus questions about Christianity":
        only_jesus_markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        only_jesus_markup.row("የውሃ ጥምቀት በኢየሱስ ክርስቶስ ስም")# check
        only_jesus_markup.row("ትምህርተ ሥላሴና የአረማውያኑ")# check
        only_jesus_markup.row("የኦንሊ ጂሰሱ_አብ ወልድና መንፈስ ቅዱስ")#check
        only_jesus_markup.row("አብ ፣ ወልድና መንፈስ ቅዱስ የተለያዩ አካላት አይደሉምን")#check
        only_jesus_markup.row("Back to Main Menu")
        bot.send_message(message.chat.id, "የትኛውን ጥናት መጀመር ይፈልጋሉ?", reply_markup=only_jesus_markup)
    
    elif message.text in STUDY_FILES_MAP:
        chat_id = message.chat.id
        file_id = STUDY_FILES_MAP[message.text] 
        
        try:
            bot.send_chat_action(chat_id, 'upload_document')
            bot.send_document(chat_id, file_id, caption=f"📄 {message.text}")
            
        except Exception as e:
            bot.send_message(chat_id, "⚠️ ፋይሉን ማግኘት አልተቻለም። እባክዎ አማካሪ ያነጋግሩ።")
            print(f"Transfer Error: {e}")
    elif message.text == "Back to Main Menu":
        bot.send_message(message.chat.id, "ዋና ማውጫ", reply_markup=reply_keyboard)

    elif message.text == "የዮሐንስ ወንጌል (Gospel of John)":
        # Call the function we just wrote
        start_bible_study(message)

    elif message.text == "በስህተት ነው የነካሁት":
        bot.send_message(message.chat.id, "ችግር የለም! 😊 አማራጮቹን እንደገና ለማየት ወይም የሚፈልጉትን ለመምረጥ በማንኛውም ጊዜ /start የሚለውን መጫን ይችላሉ።", reply_markup=reply_keyboard)
   
    else:
        bot.send_message(message.chat.id, "አልገባኝም። እባክዎ ከታች ካሉት አማራጮች አንዱን ይጫኑ ወይም አማራጮቹን ለማየት /start የሚለውን ይጠቀሙ", reply_markup=reply_keyboard)

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
                "Webhook mode requires fastapi, uvicorn, and starlette. Install them and retry."
            ) from exc
        return

    if BOT_MODE != "polling":
        print(f"Unknown BOT_MODE='{BOT_MODE}', defaulting to polling")

    print("Starting bot in polling mode")
    bot.remove_webhook()
    bot.infinity_polling()


if __name__ == "__main__":
    start_bot()
