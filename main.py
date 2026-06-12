import asyncio
from telegram.ext import ApplicationBuilder
from Config import TG_BOT_TOKEN, DB_PATH
from Storage import Storage
from Handlers import setup_handlers
from Scheduler import start_scheduler

async def main():
    storage = Storage(DB_PATH)
    app = ApplicationBuilder().token(TG_BOT_TOKEN).build()
    handlers = setup_handlers(storage)
    app.add_handlers(handlers)
    start_scheduler(app.bot, storage)
    print("Бот запущен. Ожидаю команды...")
    await app.run_polling()

if __name__ == '__main__':
    asyncio.run(main())