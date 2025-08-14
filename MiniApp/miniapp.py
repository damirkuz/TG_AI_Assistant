from fastapi import FastAPI, Request, HTTPException, Depends, Form
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager
from telethon import TelegramClient  
from redis_service import redis_client_storage  
import logging
from environs import Env
from telethon import TelegramClient
from database.db_core import async_session_maker
from database.db_functions import get_user_db
from database.models import *
from datetime import datetime as dt
from sqlalchemy import select
from typing import Optional
from entity.SemanticMessage import *
from neural_networks.semantic_search.semantic_search import *
from tg_bot.services.telethon_fetch import iter_dialog_messages
# import hashlib
# import hmac

# Настройка логгера
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Загрузка переменных окружения
env = Env()
env.read_env()
BOT_TOKEN = env("BOT_TOKEN")
semantic_search_slow = SemanticSearch(SearchMode.SLOW)
semantic_search_fast = SemanticSearch(SearchMode.FAST)
semantic_search_hybrid = SemanticSearch(SearchMode.HYBRID)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    # Инициализация ресурсов при старте
    logger.info("Starting application...")
    # Здесь можно инициализировать соединения с БД, Redis и т.д.
    try:
        yield
    finally:
        # Очистка ресурсов при завершении
        logger.info("Shutting down application...")

app = FastAPI(lifespan=lifespan)

# Подключение статических файлов и шаблонов
app.mount("/static", StaticFiles(directory="MiniApp/static"), name="static")
templates = Jinja2Templates(directory="MiniApp/templates")

# Пример данных о чатах
chat_list = ["Общий чат", "Техподдержка", "Разработка", "Маркетинг"]

# Зависимость для получения сессии БД
async def get_db():
    async with async_session_maker() as session:
        yield session

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, telegram_user_id: Optional[int] = None):
    """Главная страница"""
    try:
        if telegram_user_id != None:
            user = await get_user_db(telegram_user_id)
            bot_id = user.id
            new_chat_list = await get_dialogs(bot_id)
            chats = []
            for chat in new_chat_list:
                chats.append(chat.name)
            return templates.TemplateResponse(
                "main_page.html",
                {
                    "request": request,
                    "chat_list": chats,
                    "title" : "TG Assistant"
                }
            )

        return templates.TemplateResponse(
            "auth.html",
            {
                "request": request,
            }
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail="No user ID provided")

@app.post("/", response_class=HTMLResponse)
async def analyze_chat(request: Request,
        chat_name: str = Form(...),
        start_date: str = Form(...),
        end_date: str = Form(...),
        user_query: str = Form(...),
        analysis_mode: str = Form(...),
        telegram_user_id: int = Form(...),):
    """Обработка формы анализа чата"""
    if telegram_user_id == None:
        raise HTTPException(status_code=400, detail="No user ID provided")
    user = await get_user_db(telegram_user_id)
    bot_id = user.id
    tg_client : TelegramClient = await redis_client_storage.get_client(bot_user_id=bot_id)
    chats = await get_dialogs(bot_id)
    chat_id = None
    for chat in chats:
        if chat.name == chat_name:
            chat_id = chat.id
            break
    startdt = dt.strptime(start_date, "%Y-%m-%d")
    enddt = dt.strptime(end_date, "%Y-%m-%d")
    msgs = iter_dialog_messages(client=tg_client, dialog=chat_id, start_date=startdt, end_date=enddt)
    messages = []
    all_chat_id_username = {}
    async for message in msgs:
        from_user_id = message.from_id
        if from_user_id == None:
            from_user_id = message.peer_id.user_id
        else:
            from_user_id = from_user_id.user_id
        name = await tg_client.get_entity(from_user_id)
        all_chat_id_username[from_user_id] = name.first_name
        if message.message != None:
            messages.append(SemanticMessage(message_id=message.id,
                                            date=message.date,
                                            date_unixtime=message.date.timestamp(),
                                            from_user=name.first_name,
                                            from_user_id=from_user_id,
                                            text=message.message,
                                            reply_to_message_id=message.reply_to))
    semantic_search = ""
    match analysis_mode:
        case "fast":
            semantic_search = semantic_search_fast
        case "slow":
            semantic_search = semantic_search_slow
        case "medium":
            semantic_search = semantic_search_hybrid
    correct_messages = semantic_search.get_semantic_matches(query=user_query, messages=messages, k=30)
    messages_for_form = []
    for i in correct_messages:
        if i.get_text() != None:
            messages_for_form.append({
                "user": i.get_from(),
                "text": i.get_text(),
                "time": str(i.get_date()),  # Формат: "YYYY-MM-DD HH:MM:SS"
            })
    

    # # print(chat_name, start_date, end_date, user_query, analysis_mode, telegram_user_id)
    # # form_data = await request.form()
    return templates.TemplateResponse(
        "result.html",{
        "request": request,
        "chat_title": chat_name + " запрос = " + user_query,
        "messages": messages_for_form,
        }
    )

class VerifyRequest(BaseModel):
    initData: str
    initDataUnsafe: dict

@app.post("/verify")
async def verify(
    request: VerifyRequest, 
    db=Depends(get_db)
):
    # print(request.initDataUnsafe)
    """Верификация данных Telegram WebApp"""
    try:
        logger.info("Starting verification process")
        
        # Валидация initData
        # if not validate_init_data(request.initData, BOT_TOKEN):
        #     logger.warning("Invalid initData received")
        #     raise HTTPException(status_code=403, detail="Invalid initData")
        # TODO : надо переделать 
        
        # Получение user_id
        user_id = extract_user_id(request.initDataUnsafe)
        if not user_id:
            logger.warning("No user ID found in initData")
            raise HTTPException(status_code=400, detail="No user ID provided")
        if not await isUserFromDB(user_id):
            logger.warning("No user in db")
            raise HTTPException(status_code=400, detail="No user ID provided")
        # else:
        #     print("All ok")
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Verification error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
    
async def isUserFromDB(telegram_id: int) -> bool:
    async with async_session_maker() as session:
        stmt = (
        select(BotUser.id)
        .where(BotUser.telegram_id == telegram_id)
        .limit(1)
        )
        user_id = await session.scalar(stmt)
        return user_id is not None


def extract_user_id(init_data: str) -> Optional[str]:
    """Извлекает user_id из initData"""
    try:
        
        user_str = init_data["user"]["id"]
        if user_str:
            return user_str
        return None
    except Exception as e:
        logger.error(f"Error extracting user ID: {str(e)}")
        return None

def validate_init_data(init_data: str, bot_token: str) -> bool:
    pass

async def get_dialogs(user_id: int):
    """Получение списка диалогов через Telethon"""
    try:
        
        tg_client: TelegramClient = await redis_client_storage.get_client(bot_user_id=user_id) 
        if not tg_client:
            raise HTTPException(status_code=404, detail="Telegram client not found")
        
        if not tg_client.is_connected():
            await tg_client.connect()
        chats = []
        async for chat in tg_client.iter_dialogs():  
            chats.append(chat) 
        return chats
    except Exception as e:
        logger.error(f"Error getting dialogs: {str(e)}")
        raise HTTPException(status_code=500, detail="Error retrieving dialogs")
    

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("MiniApp.miniapp:app", host="0.0.0.0", port=8000, reload=True)