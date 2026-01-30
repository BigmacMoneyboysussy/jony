import logging
from datetime import datetime, timedelta
from typing import Dict, List
import json
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
SELECT_DEPARTMENT, SELECT_DOCTOR, SELECT_DATE, SELECT_TIME, ENTER_NAME, ENTER_PHONE, CONFIRM = range(7)


# База данных (в реальном проекте используйте PostgreSQL/MySQL)
class Database:
    def __init__(self):
        self.file_path = "database.json"
        self.load_data()

    def load_data(self):
        if os.path.exists(self.file_path):
            with open(self.file_path, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
        else:
            self.data = {
                "departments": [
                    {"id": 1, "name": "Терапия"},
                    {"id": 2, "name": "Хирургия"},
                    {"id": 3, "name": "Неврология"},
                    {"id": 4, "name": "Кардиология"},
                    {"id": 5, "name": "Офтальмология"}
                ],
                "doctors": [
                    {"id": 1, "name": "Иванов И.И.", "department_id": 1},
                    {"id": 2, "name": "Петрова А.С.", "department_id": 1},
                    {"id": 3, "name": "Сидоров В.П.", "department_id": 2},
                    {"id": 4, "name": "Козлова Е.В.", "department_id": 3},
                    {"id": 5, "name": "Смирнов Д.А.", "department_id": 4}
                ],
                "appointments": [],
                "working_hours": {"start": "09:00", "end": "18:00"},
                "break_hours": {"start": "13:00", "end": "14:00"}
            }
            self.save_data()

    def save_data(self):
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def get_departments(self):
        return self.data["departments"]

    def get_doctors_by_department(self, department_id):
        return [doc for doc in self.data["doctors"] if doc["department_id"] == department_id]

    def get_doctor(self, doctor_id):
        for doc in self.data["doctors"]:
            if doc["id"] == doctor_id:
                return doc
        return None

    def get_available_times(self, doctor_id, date):
        """Получить доступное время для записи"""
        # Фиксируем рабочее время
        start_hour = int(self.data["working_hours"]["start"].split(":")[0])
        end_hour = int(self.data["working_hours"]["end"].split(":")[0])
        break_start = int(self.data["break_hours"]["start"].split(":")[0])
        break_end = int(self.data["break_hours"]["end"].split(":")[0])

        # Генерируем все возможные слоты
        all_slots = []
        for hour in range(start_hour, end_hour):
            if not (break_start <= hour < break_end):
                for minute in [0, 30]:
                    all_slots.append(f"{hour:02d}:{minute:02d}")

        # Ищем уже занятые слоты
        booked_slots = []
        for appointment in self.data["appointments"]:
            if (appointment["doctor_id"] == doctor_id and
                    appointment["date"] == date):
                booked_slots.append(appointment["time"])

        # Возвращаем свободные слоты
        return [slot for slot in all_slots if slot not in booked_slots]

    def add_appointment(self, user_id, doctor_id, date, time, patient_name, phone):
        appointment = {
            "id": len(self.data["appointments"]) + 1,
            "user_id": user_id,
            "doctor_id": doctor_id,
            "date": date,
            "time": time,
            "patient_name": patient_name,
            "phone": phone,
            "created_at": datetime.now().isoformat()
        }
        self.data["appointments"].append(appointment)
        self.save_data()
        return appointment

    def get_user_appointments(self, user_id):
        return [app for app in self.data["appointments"] if app["user_id"] == user_id]


# Инициализация базы данных
db = Database()


# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = f"""
👋 Здравствуйте, {user.first_name}!

Добро пожаловать в систему онлайн-записи к врачу!

Доступные команды:
/start - Начало работы
/record - Записаться на прием
/my_records - Мои записи
/cancel - Отмена текущего действия
    """

    keyboard = [
        [KeyboardButton("📅 Записаться на прием")],
        [KeyboardButton("📋 Мои записи")],
        [KeyboardButton("🏥 Отделения")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(welcome_text, reply_markup=reply_markup)
    return ConversationHandler.END


# Начало записи
async def start_record(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Сброс данных
    context.user_data.clear()

    # Получаем список отделений
    departments = db.get_departments()

    # Создаем клавиатуру с отделениями
    keyboard = []
    for dept in departments:
        keyboard.append([InlineKeyboardButton(dept["name"], callback_data=f"dept_{dept['id']}")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🏥 Выберите отделение:",
        reply_markup=reply_markup
    )

    return SELECT_DEPARTMENT


# Выбор отделения
async def select_department(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    department_id = int(query.data.split("_")[1])
    context.user_data["department_id"] = department_id

    # Получаем врачей отделения
    doctors = db.get_doctors_by_department(department_id)

    if not doctors:
        await query.edit_message_text("В этом отделении временно нет врачей. Выберите другое отделение.")
        return SELECT_DEPARTMENT

    keyboard = []
    for doc in doctors:
        keyboard.append([InlineKeyboardButton(doc["name"], callback_data=f"doc_{doc['id']}")])
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_dept")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "👨‍⚕️ Выберите врача:",
        reply_markup=reply_markup
    )

    return SELECT_DOCTOR


# Выбор врача
async def select_doctor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "back_to_dept":
        departments = db.get_departments()
        keyboard = []
        for dept in departments:
            keyboard.append([InlineKeyboardButton(dept["name"], callback_data=f"dept_{dept['id']}")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "🏥 Выберите отделение:",
            reply_markup=reply_markup
        )
        return SELECT_DEPARTMENT

    doctor_id = int(query.data.split("_")[1])
    context.user_data["doctor_id"] = doctor_id

    # Генерируем даты на 2 недели вперед
    keyboard = []
    today = datetime.now().date()
    for i in range(1, 15):  # 14 дней
        date = today + timedelta(days=i)
        if date.weekday() < 5:  # Только рабочие дни (пн-пт)
            keyboard.append([
                InlineKeyboardButton(
                    date.strftime("%d.%m.%Y (%a)"),
                    callback_data=f"date_{date.strftime('%Y-%m-%d')}"
                )
            ])

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_doctors")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    doctor = db.get_doctor(doctor_id)
    await query.edit_message_text(
        f"Выбран врач: {doctor['name']}\n\n📅 Выберите дату приема:",
        reply_markup=reply_markup
    )

    return SELECT_DATE


# Выбор даты
async def select_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "back_to_doctors":
        department_id = context.user_data.get("department_id")
        doctors = db.get_doctors_by_department(department_id)

        keyboard = []
        for doc in doctors:
            keyboard.append([InlineKeyboardButton(doc["name"], callback_data=f"doc_{doc['id']}")])
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_dept")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "👨‍⚕️ Выберите врача:",
            reply_markup=reply_markup
        )
        return SELECT_DOCTOR

    date = query.data.split("_")[1]
    context.user_data["date"] = date

    # Получаем доступное время
    doctor_id = context.user_data["doctor_id"]
    available_times = db.get_available_times(doctor_id, date)

    if not available_times:
        await query.edit_message_text(
            "На выбранную дату нет свободного времени. Пожалуйста, выберите другую дату."
        )
        return SELECT_DATE

    # Создаем клавиатуру со временем
    keyboard = []
    row = []
    for i, time in enumerate(available_times):
        row.append(InlineKeyboardButton(time, callback_data=f"time_{time}"))
        if len(row) == 3 or i == len(available_times) - 1:
            keyboard.append(row)
            row = []

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_dates")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "⏰ Выберите время приема:",
        reply_markup=reply_markup
    )

    return SELECT_TIME


# Выбор времени
async def select_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "back_to_dates":
        # Возвращаемся к выбору даты
        keyboard = []
        today = datetime.now().date()
        for i in range(1, 15):
            date = today + timedelta(days=i)
            if date.weekday() < 5:
                keyboard.append([
                    InlineKeyboardButton(
                        date.strftime("%d.%m.%Y (%a)"),
                        callback_data=f"date_{date.strftime('%Y-%m-%d')}"
                    )
                ])

        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_doctors")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        doctor = db.get_doctor(context.user_data["doctor_id"])
        await query.edit_message_text(
            f"Выбран врач: {doctor['name']}\n\n📅 Выберите дату приема:",
            reply_markup=reply_markup
        )
        return SELECT_DATE

    time = query.data.split("_")[1]
    context.user_data["time"] = time

    await query.edit_message_text(
        "👤 Введите ваше ФИО (полностью):\n\n"
        "Пример: Иванов Иван Иванович"
    )

    return ENTER_NAME


# Ввод ФИО
async def enter_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text
    if len(name.split()) < 2:
        await update.message.reply_text("Пожалуйста, введите ФИО полностью (минимум 2 слова)")
        return ENTER_NAME

    context.user_data["patient_name"] = name

    await update.message.reply_text(
        "📱 Введите ваш номер телефона:\n\n"
        "Пример: +79161234567"
    )

    return ENTER_PHONE


# Ввод телефона
async def enter_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text
    # Простая валидация телефона
    if not (phone.replace("+", "").replace(" ", "").isdigit() and len(phone.replace("+", "").replace(" ", "")) >= 10):
        await update.message.reply_text("Пожалуйста, введите корректный номер телефона")
        return ENTER_PHONE

    context.user_data["phone"] = phone

    # Формируем информацию для подтверждения
    doctor = db.get_doctor(context.user_data["doctor_id"])
    date_str = datetime.strptime(context.user_data["date"], "%Y-%m-%d").strftime("%d.%m.%Y")

    confirm_text = f"""
✅ Пожалуйста, подтвердите запись:

👨‍⚕️ Врач: {doctor['name']}
📅 Дата: {date_str}
⏰ Время: {context.user_data['time']}
👤 Пациент: {context.user_data['patient_name']}
📱 Телефон: {context.user_data['phone']}

Всё верно?
"""

    keyboard = [
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_yes"),
            InlineKeyboardButton("❌ Отменить", callback_data="confirm_no")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(confirm_text, reply_markup=reply_markup)

    return CONFIRM


# Подтверждение записи
async def confirm_appointment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "confirm_no":
        await query.edit_message_text("Запись отменена.")
        return ConversationHandler.END

    # Сохраняем запись
    appointment = db.add_appointment(
        user_id=update.effective_user.id,
        doctor_id=context.user_data["doctor_id"],
        date=context.user_data["date"],
        time=context.user_data["time"],
        patient_name=context.user_data["patient_name"],
        phone=context.user_data["phone"]
    )

    doctor = db.get_doctor(context.user_data["doctor_id"])
    date_str = datetime.strptime(context.user_data["date"], "%Y-%m-%d").strftime("%d.%m.%Y")

    success_text = f"""
🎉 Запись успешно создана!

Номер записи: #{appointment['id']}
👨‍⚕️ Врач: {doctor['name']}
📅 Дата: {date_str}
⏰ Время: {context.user_data['time']}
👤 Пациент: {context.user_data['patient_name']}

⚠️ Пожалуйста, приходите за 10 минут до назначенного времени.
"""

    await query.edit_message_text(success_text)

    # Отправляем напоминание за день до приема
    context.job_queue.run_once(
        send_reminder,
        when=datetime.strptime(context.user_data["date"], "%Y-%m-%d") - timedelta(days=1),
        data=update.effective_user.id,
        name=str(appointment['id'])
    )

    return ConversationHandler.END


# Отправка напоминания
async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.data
    await context.bot.send_message(
        chat_id=user_id,
        text="🔔 Напоминание: Завтра у вас запись к врачу!"
    )


# Просмотр своих записей
async def my_records(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    appointments = db.get_user_appointments(user_id)

    if not appointments:
        await update.message.reply_text("У вас нет активных записей.")
        return

    text = "📋 Ваши записи:\n\n"

    for app in sorted(appointments, key=lambda x: x["date"] + " " + x["time"]):
        doctor = db.get_doctor(app["doctor_id"])
        date_str = datetime.strptime(app["date"], "%Y-%m-%d").strftime("%d.%m.%Y")
        text += f"""
№{app['id']}
👨‍⚕️ Врач: {doctor['name']}
📅 Дата: {date_str}
⏰ Время: {app['time']}
👤 Пациент: {app['patient_name']}
📱 Телефон: {app['phone']}
-------------------
"""

    await update.message.reply_text(text)


# Отмена
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Действие отменено.")
    return ConversationHandler.END


# Главная функция
def main():
    # Токен вашего бота
    TOKEN = "YOUR_BOT_TOKEN_HERE"

    # Создаем Application
    application = Application.builder().token(TOKEN).build()

    # ConversationHandler для записи
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("record", start_record),
            MessageHandler(filters.Regex("^(📅 Записаться на прием)$"), start_record)
        ],
        states={
            SELECT_DEPARTMENT: [CallbackQueryHandler(select_department)],
            SELECT_DOCTOR: [CallbackQueryHandler(select_doctor)],
            SELECT_DATE: [CallbackQueryHandler(select_date)],
            SELECT_TIME: [CallbackQueryHandler(select_time)],
            ENTER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_name)],
            ENTER_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_phone)],
            CONFIRM: [CallbackQueryHandler(confirm_appointment)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("my_records", my_records))
    application.add_handler(MessageHandler(filters.Regex("^(📋 Мои записи)$"), my_records))

    # Обработчик для отображения отделений
    async def show_departments(update: Update, context: ContextTypes.DEFAULT_TYPE):
        departments = db.get_departments()
        text = "🏥 Отделения нашей больницы:\n\n"
        for dept in departments:
            text += f"• {dept['name']}\n"

        await update.message.reply_text(text)

    application.add_handler(MessageHandler(filters.Regex("^(🏥 Отделения)$"), show_departments))

    # Запуск бота
    print("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_UPDATES)


if __name__ == "__main__":
    main()
