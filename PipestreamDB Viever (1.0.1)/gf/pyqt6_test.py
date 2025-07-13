import logging
import os
import tempfile
import cv2
import numpy as np
import pytesseract
import pymupdf
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from docx import Document
import xml.etree.ElementTree as ET
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from dotenv import load_dotenv
import asyncio

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Dictionary to store user data (e.g., extracted text)
user_data = {}

# Telegram bot token
BOT_TOKEN = "8151004630:AAEs_BD6CpxM3UsVN4dSNru9XJjaxKpUQMY"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command."""
    await update.message.reply_text(
        "Привет! Я бот для извлечения текста из изображений, PDF и XML файлов.\n"
        "Отправь мне изображение (PNG, JPG, JPEG, BMP, TIFF) или фото, и я сразу извлеку текст.\n"
        "Также поддерживаются PDF и XML файлы.\n"
        "После извлечения текста ты сможешь сохранить его как TXT, PDF или DOCX.\n"
        "Команда /paste не поддерживается, так как Telegram не позволяет вставку из буфера обмена."
    )

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming files (images, PDFs, XML) or photos."""
    user_id = update.effective_user.id
    file = None
    file_name = None
    is_photo = False

    # Check if the message contains a photo
    if update.message.photo:
        is_photo = True
        photo = update.message.photo[-1]  # Get the highest resolution photo
        file = await photo.get_file()
        file_name = "photo.jpg"  # Telegram photos are typically JPEG
    # Check if the message contains a document
    elif update.message.document:
        file = await update.message.document.get_file()
        file_name = update.message.document.file_name
    else:
        await update.message.reply_text(
            "Пожалуйста, отправь изображение, фото, PDF или XML файл."
        )
        return

    # Download file to a temporary location
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file_name)[1]) as temp_file:
        file_path = temp_file.name
        await file.download_to_drive(file_path)

    try:
        if is_photo or file_name.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.tiff')):
            await process_image(update, context, file_path, user_id)
        elif file_name.lower().endswith('.pdf'):
            await process_pdf(update, context, file_path, user_id)
        elif file_name.lower().endswith('.xml'):
            await process_xml(update, context, file_path, user_id)
        else:
            await update.message.reply_text(
                "Неподдерживаемый формат. Отправьте изображение (PNG, JPG, JPEG, BMP, TIFF), PDF или XML."
            )
    except Exception as e:
        logger.error(f"Error processing file for user {user_id}: {str(e)}")
        await update.message.reply_text(f"Ошибка обработки файла: {str(e)}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

async def process_image(update: Update, context: ContextTypes.DEFAULT_TYPE, file_path, user_id):
    """Process an image file or photo and extract text immediately."""
    try:
        image = cv2.imdecode(np.fromfile(file_path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            await update.message.reply_text("Не удалось загрузить изображение.")
            return

        # Preprocess and extract text
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
        extracted_text = pytesseract.image_to_string(
            binary,
            lang='eng+rus',
            config='--oem 3 --psm 6 -c preserve_interword_spaces=1 '
                   'tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzабвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ.,-/ '
        )

        user_data[user_id] = {'extracted_text': extracted_text}
        if extracted_text.strip():
            await update.message.reply_text(
                f"Текст извлечён из изображения:\n\n{extracted_text[:1000]}...\n\n"
                "Выбери формат для сохранения текста.",
                reply_markup=get_save_buttons()
            )
        else:
            await update.message.reply_text("Текст не обнаружен в изображении.")
    except Exception as e:
        logger.error(f"Error processing image for user {user_id}: {str(e)}")
        await update.message.reply_text(f"Ошибка обработки изображения: {str(e)}")

async def process_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE, file_path, user_id):
    """Process a PDF file and extract text or image."""
    try:
        doc = pymupdf.open(file_path)
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text = page.get_text("text")
            if text.strip():
                user_data[user_id] = {'extracted_text': text}
                await update.message.reply_text(
                    f"Текст извлечён из PDF:\n\n{text[:1000]}...\n\n"
                    "Выбери формат для сохранения текста.",
                    reply_markup=get_save_buttons()
                )
                return
            image_list = page.get_images(full=True)
            if image_list:
                xref = image_list[0][0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
                if image is None:
                    await update.message.reply_text("Не удалось извлечь изображение из PDF.")
                    return
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
                extracted_text = pytesseract.image_to_string(
                    binary,
                    lang='eng+rus',
                    config='--oem 3 --psm 6 -c preserve_interword_spaces=1 '
                           'tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzабвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ.,-/ '
                )
                user_data[user_id] = {'extracted_text': extracted_text}
                if extracted_text.strip():
                    await update.message.reply_text(
                        f"Текст извлечён из изображения в PDF:\n\n{extracted_text[:1000]}...\n\n"
                        "Выбери формат для сохранения текста.",
                        reply_markup=get_save_buttons()
                    )
                else:
                    await update.message.reply_text("Текст не обнаружен в изображении из PDF.")
                return
        await update.message.reply_text("В PDF не найдено текста или изображений.")
    except Exception as e:
        logger.error(f"Error processing PDF for user {user_id}: {str(e)}")
        await update.message.reply_text(f"Ошибка обработки PDF: {str(e)}")

async def process_xml(update: Update, context: ContextTypes.DEFAULT_TYPE, file_path, user_id):
    """Process an XML file and extract text."""
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        full_text = ""
        for page in root.findall('.//PAGE'):
            content = page.find('.//CONTENT_FROM_OCR')
            if content is not None and content.text:
                full_text += content.text.strip() + "\n"
        if full_text:
            user_data[user_id] = {'extracted_text': full_text.strip()}
            await update.message.reply_text(
                f"Текст извлечён из XML:\n\n{full_text[:1000]}...\n\n"
                "Выбери формат для сохранения текста.",
                reply_markup=get_save_buttons()
            )
        else:
            await update.message.reply_text("В XML не найдено текста.")
    except Exception as e:
        logger.error(f"Error processing XML for user {user_id}: {str(e)}")
        await update.message.reply_text(f"Ошибка обработки XML: {str(e)}")

async def paste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /paste command."""
    await update.message.reply_text(
        "В Telegram нельзя напрямую вставить изображение из буфера обмена. "
        "Пожалуйста, отправь изображение как файл или фото."
    )

def get_save_buttons():
    """Return inline keyboard with save options."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Сохранить как TXT", callback_data='save_txt'),
            InlineKeyboardButton("Сохранить как PDF", callback_data='save_pdf'),
            InlineKeyboardButton("Сохранить как DOCX", callback_data='save_docx'),
        ]
    ])

async def save_file_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle save file button clicks."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id not in user_data or not user_data[user_id].get('extracted_text'):
        await query.message.reply_text("Нет текста для сохранения.")
        return

    extracted_text = user_data[user_id]['extracted_text']
    file_type = query.data.split('_')[1]
    try:
        with tempfile.NamedTemporaryFile(suffix=f'.{file_type}', delete=False) as temp_file:
            if file_type == 'txt':
                with open(temp_file.name, 'w', encoding='utf-8') as f:
                    f.write(extracted_text)
            elif file_type == 'pdf':
                doc = SimpleDocTemplate(temp_file.name, pagesize=letter)
                story = [Paragraph(extracted_text, style=None), Spacer(1, 12)]
                doc.build(story)
            elif file_type == 'docx':
                doc = Document()
                doc.add_paragraph(extracted_text)
                doc.save(temp_file.name)

            await query.message.reply_document(
                document=open(temp_file.name, 'rb'),
                filename=f"extracted_text.{file_type}",
                caption=f"Файл сохранён как extracted_text.{file_type}"
            )
        os.remove(temp_file.name)
    except Exception as e:
        logger.error(f"Error saving file for user {user_id}: {str(e)}")
        await query.message.reply_text(f"Ошибка сохранения файла: {str(e)}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors."""
    logger.error(f"Update {update} caused error {context.error}")
    if update and update.effective_message:
        await update.effective_message.reply_text("Произошла ошибка. Попробуй снова.")

async def main():
    """Run the bot with webhook or polling."""
    application = Application.builder().token(BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("paste", paste))
    application.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))
    application.add_handler(CallbackQueryHandler(save_file_callback, pattern='^save_(txt|pdf|docx)$'))
    application.add_error_handler(error_handler)

    try:
        if os.getenv('RENDER'):
            port = int(os.getenv('PORT', 10000))
            webhook_url = f"{os.getenv('RENDER_EXTERNAL_URL')}/{BOT_TOKEN}"
            await application.initialize()
            await application.bot.set_webhook(webhook_url)
            await application.start()
            await application.updater.start_webhook(
                listen="0.0.0.0",
                port=port,
                url_path=BOT_TOKEN,
                webhook_url=webhook_url
            )
            await asyncio.Event().wait()  # Keep running until interrupted
        else:
            await application.initialize()
            await application.start()
            await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
            await asyncio.Event().wait()  # Keep running until interrupted
    except Exception as e:
        logger.error(f"Error in main: {str(e)}")
        raise
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()

if __name__ == '__main__':
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
    except Exception as e:
        logger.error(f"Error running bot: {str(e)}")
    finally:
        if not loop.is_closed():
            loop.close()