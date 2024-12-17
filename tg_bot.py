import json
import os
import requests
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# Состояния для ConversationHandler
WAITING_FOR_CURRENCY = 1

# Файл для сохранения настроек
SETTINGS_FILE = "user_settings.json"

# Загрузка настроек из файла
def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as file:
            return json.load(file)
    return {}
# Сохранение настроек в файл
def save_settings(settings):
    with open(SETTINGS_FILE, "w") as file:
        json.dump(settings, file)
# Глобальная переменная для хранения настроек
user_settings = load_settings()

# Получение курса валют от Центробанка РФ
def get_exchange_rate(base_currency: str, target_currency: str):
    url = "https://www.cbr.ru/scripts/XML_daily.asp"
    response = requests.get(url)
    response.encoding = 'windows-1251'
    if response.status_code != 200:
        return None
    from xml.etree import ElementTree as ET
    tree = ET.fromstring(response.text)
    # Словарь для хранения курсов валют
    rates = {"RUB": 1.0}  # Добавляем рубль как базовую валюту
    # Извлечение данных из XML
    for valute in tree.findall("Valute"):
        char_code = valute.find("CharCode").text
        nominal = int(valute.find("Nominal").text)  # Номинал (например, 10 или 100)
        value = float(valute.find("Value").text.replace(",", "."))  # Курс для номинала
        rates[char_code] = value / nominal  # Курс за 1 единицу валюты
    # Проверка доступности валют
    if base_currency not in rates or target_currency not in rates:
        return None
    # Конвертация через рубль
    return rates[target_currency] / rates[base_currency]
# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привет! Я бот для конвертации валют. Введите команду /help, чтобы узнать, как меня использовать."
    )
# Команда /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Я могу помочь с конвертацией валют. Просто напишите запрос в формате:\n"
        "<Сумма> <Исходная валюта> в <Целевая валюта>\n"
        "Пример: 100 USD в RUB\n\n"
        "Доступные команды:\n"
        "/start - Начать работу\n"
        "/help - Информация о командах\n"
        "/settings - Настройка базовой валюты"
    )
# Команда /settings
async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        [KeyboardButton("USD"), KeyboardButton("EUR")],
        [KeyboardButton("RUB"), KeyboardButton("GBP")],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    await update.message.reply_text(
        "Выберите базовую валюту из предложенных или введите код валюты вручную:",
        reply_markup=reply_markup,
    )
    return WAITING_FOR_CURRENCY
# Обработка ответа пользователя на /settings
async def set_base_currency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = str(update.effective_user.id)
    currency = update.message.text.upper()
    if len(currency) == 3 and currency.isalpha():
        # Сохраняем базовую валюту
        user_settings[user_id] = {"base_currency": currency}
        save_settings(user_settings)
        await update.message.reply_text(
            f"Базовая валюта установлена: {currency}. Теперь при конвертации она будет использоваться по умолчанию."
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "Неверный код валюты. Попробуйте снова выбрать из предложенных или ввести код вручную:"
        )
        return WAITING_FOR_CURRENCY
# Обработка сообщений с запросами
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    try:
        user_id = str(update.effective_user.id)
        parts = text.split()
        
        # Если формат "100 DEFAULT в EUR"
        if len(parts) == 4 and parts[2].lower() == "в":
            amount = float(parts[0])
            base_currency = parts[1].upper()
            target_currency = parts[3].upper()
        # Если формат "100 в EUR" (базовая валюта используется по умолчанию)
        elif len(parts) == 3 and parts[1].lower() == "в":
            amount = float(parts[0])
            base_currency = user_settings.get(user_id, {}).get("base_currency", "RUB")
            target_currency = parts[2].upper()
        else:
            raise ValueError("Неверный формат")
        # Проверяем и выполняем конвертацию
        rate = get_exchange_rate(base_currency, target_currency)
        if rate is None:
            await update.message.reply_text("Не удалось найти указанные валюты. Проверьте код валюты.")
            return
        result = amount / rate
        await update.message.reply_text(f"{amount} {base_currency} = {result:.2f} {target_currency}")
    
    except ValueError:
        await update.message.reply_text(
            "Неверный формат запроса. Используйте:\n"
            "<Сумма> <Исходная валюта> в <Целевая валюта>\n"
            "Пример: 100 USD в RUB\n"
            "Или: 100 в EUR (с использованием базовой валюты)."
        )

with open('token.txt') as f:
    token = f.read()

# Основная функция
def main():
    application = Application.builder().token(token).build()
    # ConversationHandler для настройки базовой валюты
    settings_handler = ConversationHandler(
        entry_points=[CommandHandler("settings", settings)],
        states={
            WAITING_FOR_CURRENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_base_currency)],
        },
        fallbacks=[CommandHandler("settings", settings)],
    )
    # Регистрация обработчиков команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(settings_handler)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    # Запуск бота
    application.run_polling()
if __name__ == "__main__":
    main()