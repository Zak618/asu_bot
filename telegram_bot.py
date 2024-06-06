import logging
import os
import uuid
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, CallbackContext
import mysql.connector
import config  # Импортируем файл конфигурации
import bcrypt

# Настройки для логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s', level=logging.INFO)

# Настройки базы данных из конфигурации
db_config = config.DB_CONFIG

# Путь для сохранения сертификатов
CERTIFICATE_PATH = "C:/Users/Rolan/Desktop/asu/images/certificates/"

# Команда для старта
async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text('👋 Добро пожаловать! Пожалуйста, введите ваш email для авторизации.')

# Обработчик сообщений
async def handle_message(update: Update, context: CallbackContext) -> None:
    user_step = context.user_data.get('step', 'email')
    if user_step == 'email':
        context.user_data['email'] = update.message.text
        context.user_data['step'] = 'password'
        await update.message.reply_text('🔐 Теперь введите ваш пароль для подтверждения.')
    elif user_step == 'password':
        password = update.message.text
        email = context.user_data.get('email')
        user = authenticate_user(email, password)
        if user:
            context.user_data['user_id'] = user['id']
            context.user_data['step'] = None
            await update.message.reply_text(f'🎉 Добро пожаловать, {user["first_name"]}! Ваш баланс: {user["balance"]} баллов.', reply_markup=main_menu())
        else:
            context.user_data['step'] = 'email'
            await update.message.reply_text('❌ Неверный email или пароль. Пожалуйста, попробуйте снова.')

# Обработчик загрузки фотографий
async def handle_photo(update: Update, context: CallbackContext) -> None:
    user_id = context.user_data.get('user_id')
    event_id = context.user_data.get('upload_event_id')
    place = context.user_data.get('place')
    
    if not user_id or not event_id or not place:
        await update.message.reply_text('❌ Произошла ошибка. Пожалуйста, попробуйте снова.')
        return
    
    photo = update.message.photo[-1]
    file = await photo.get_file()
    file_path = os.path.join(CERTIFICATE_PATH, f"{user_id}_{event_id}.jpg")
    
    if not os.path.exists(CERTIFICATE_PATH):
        os.makedirs(CERTIFICATE_PATH)
    
    await file.download_to_drive(file_path)
    
    upload_certificate(user_id, event_id, file_path, place)
    
    await update.message.reply_text('📄 Сертификат успешно загружен!')
    context.user_data['upload_event_id'] = None
    context.user_data['place'] = None
    
    # Возврат в главное меню после успешной загрузки сертификата
    await update.message.reply_text('📋 Главное меню', reply_markup=main_menu())

# Функция для аутентификации пользователя
def authenticate_user(email: str, password: str) -> dict:
    connection = mysql.connector.connect(**db_config)
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cursor.fetchone()
    cursor.close()
    connection.close()
    if user and bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
        return user
    return None

# Главное меню
def main_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📅 Посмотреть мероприятия", callback_data='view_events')],
        [InlineKeyboardButton("✅ Мои мероприятия", callback_data='my_events')],
        [InlineKeyboardButton("👤 Мой профиль", callback_data='my_profile')]
    ]
    return InlineKeyboardMarkup(keyboard)

# Обработчик команд
async def button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    user_id = context.user_data.get('user_id')

    if query.data == 'view_events':
        events = get_events()
        keyboard = [[InlineKeyboardButton(event["title"], callback_data=f'event_{event["id"]}')] for event in events]
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='main_menu')])
        await query.edit_message_text(text='📅 Текущие мероприятия:', reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data.startswith('event_'):
        event_id = int(query.data.split('_')[1])
        event = get_event_details(event_id)
        participation_status = check_participation(user_id, event_id)
        if participation_status:
            keyboard = [
                [InlineKeyboardButton("❌ Отменить участие", callback_data=f'cancel_{event_id}')],
                [InlineKeyboardButton("📄 Загрузить сертификат", callback_data=f'upload_{event_id}')],
                [InlineKeyboardButton("🔙 Назад", callback_data='view_events')]
            ]
        else:
            keyboard = [
                [InlineKeyboardButton("✅ Участвую", callback_data=f'participate_{event_id}')],
                [InlineKeyboardButton("🔙 Назад", callback_data='view_events')]
            ]
        await query.edit_message_text(
            text=f"📅 Название: {event['title']}\n📝 Описание: {event['description']}\n📅 Дата: {event['start_date']} - {event['end_date']}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif query.data == 'my_events':
        events = get_user_events(user_id)
        if not events:
            await query.edit_message_text(text='❌ Вы не участвуете ни в одном мероприятии.', reply_markup=main_menu())
        else:
            keyboard = [[InlineKeyboardButton(event["title"], callback_data=f'my_event_{event["id"]}')] for event in events]
            keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='main_menu')])
            await query.edit_message_text(text='✅ Ваши мероприятия:', reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data.startswith('my_event_'):
        event_id = int(query.data.split('_')[2])
        event = get_event_details(event_id)
        keyboard = [
            [InlineKeyboardButton("❌ Отменить участие", callback_data=f'cancel_{event_id}')],
            [InlineKeyboardButton("📄 Загрузить сертификат", callback_data=f'upload_{event_id}')],
            [InlineKeyboardButton("🔙 Назад", callback_data='my_events')]
        ]
        await query.edit_message_text(
            text=f"📅 Название: {event['title']}\n📝 Описание: {event['description']}\n📅 Дата: {event['start_date']} - {event['end_date']}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif query.data == 'my_profile':
        user = get_user_profile(user_id)
        keyboard = [
            [InlineKeyboardButton("🔙 Назад", callback_data='main_menu')]
        ]
        await query.edit_message_text(
            text=f'👤 Имя: {user["first_name"]} {user["last_name"]}\n💰 Баланс: {user["balance"]} баллов\n📧 Email: {user["email"]}',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif query.data == 'main_menu':
        await query.edit_message_text(text='📋 Главное меню', reply_markup=main_menu())
    elif query.data.startswith('participate_'):
        event_id = int(query.data.split('_')[1])
        participate_in_event(user_id, event_id)
        await query.edit_message_text(text='✅ Вы успешно записались на мероприятие!', reply_markup=main_menu())
    elif query.data.startswith('cancel_'):
        event_id = int(query.data.split('_')[1])
        cancel_participation(user_id, event_id)
        await query.edit_message_text(text='❌ Вы успешно отменили участие в мероприятии!', reply_markup=main_menu())
    elif query.data.startswith('upload_'):
        event_id = int(query.data.split('_')[1])
        context.user_data['upload_event_id'] = event_id
        keyboard = [
            [InlineKeyboardButton("🏅 Участник", callback_data=f'place_participant')],
            [InlineKeyboardButton("🥈 Призер", callback_data=f'place_prize')],
            [InlineKeyboardButton("🥇 Победитель", callback_data=f'place_winner')],
            [InlineKeyboardButton("🔙 Назад", callback_data=f'event_{event_id}')]
        ]
        await query.edit_message_text(text='Выберите место, которое вы заняли на мероприятии:', reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data.startswith('place_'):
        place = query.data.split('_')[1]
        context.user_data['place'] = place
        await query.edit_message_text(text='📸 Пожалуйста, загрузите фото вашего сертификата.')

# Функция для получения мероприятий
def get_events() -> list:
    connection = mysql.connector.connect(**db_config)
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT id, title, description, start_date, end_date FROM event")
    events = cursor.fetchall()
    cursor.close()
    connection.close
    return events

def get_event_details(event_id: int) -> dict:
    connection = mysql.connector.connect(**db_config)
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT id, title, description, start_date, end_date FROM event WHERE id = %s", (event_id,))
    event = cursor.fetchone()
    cursor.close()
    connection.close()
    return event

# Функция для проверки участия
def check_participation(user_id: int, event_id: int) -> bool:
    connection = mysql.connector.connect(**db_config)
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM event_participation WHERE student_id = %s AND event_id = %s", (user_id, event_id))
    result = cursor.fetchone()
    cursor.close()
    connection.close()
    return result is not None

# Функция для получения мероприятий пользователя
def get_user_events(user_id: int) -> list:
    connection = mysql.connector.connect(**db_config)
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        "SELECT e.id, e.title, e.description, e.start_date, e.end_date, ep.participation_date FROM event e JOIN event_participation ep ON e.id = ep.event_id WHERE ep.student_id = %s",
        (user_id,)
    )
    events = cursor.fetchall()
    cursor.close()
    connection.close()
    return events

# Функция для получения профиля пользователя
def get_user_profile(user_id: int) -> dict:
    connection = mysql.connector.connect(**db_config)
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT first_name, last_name, email, balance FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    cursor.close()
    connection.close()
    return user

# Функция для участия в мероприятии
def participate_in_event(user_id: int, event_id: int) -> None:
    connection = mysql.connector.connect(**db_config)
    cursor = connection.cursor()
    cursor.execute("INSERT INTO event_participation (student_id, event_id, participation_date) VALUES (%s, %s, NOW())", (user_id, event_id))
    connection.commit()
    cursor.close()
    connection.close()

# Функция для отмены участия в мероприятии
def cancel_participation(user_id: int, event_id: int) -> None:
    connection = mysql.connector.connect(**db_config)
    cursor = connection.cursor()
    cursor.execute("DELETE FROM event_participation WHERE student_id = %s AND event_id = %s", (user_id, event_id))
    connection.commit()
    cursor.close()
    connection.close()

# Функция для добавления сертификатов
def upload_certificate(user_id: int, event_id: int, file_path: str, place: str) -> None:
    guid = uuid.uuid4().hex[:12]  # Генерация случайного GUID
    connection = mysql.connector.connect(**db_config)
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO certificate (event_id, user_id, upload_date, file_path, guid, place) VALUES (%s, %s, NOW(), %s, %s, %s)",
        (event_id, user_id, file_path, guid, place)
    )
    connection.commit()
    cursor.close()
    connection.close()

def main() -> None:
    # Токен вашего бота из конфигурации
    token = config.TELEGRAM_BOT_TOKEN

    application = ApplicationBuilder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(CallbackQueryHandler(button))

    application.run_polling()

if __name__ == '__main__':
    main()
