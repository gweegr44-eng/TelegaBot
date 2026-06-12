from Config import TG_BOT_TOKEN, DB_PATH
from Storage import Storage
from Handlers import setup_handlers
from Scheduler import start_scheduler
from telegram.ext import Application

def main():
    storage = Storage(DB_PATH)
    app = Application.builder().token(TG_BOT_TOKEN).build()
    handlers = setup_handlers(storage)
    app.add_handlers(handlers)
    start_scheduler(app.bot, storage)
    print("Бот запущен. Ожидаю команды...")
    app.run_polling()

if __name__ == '__main__':
    main()