import logging
import requests
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

# ==========================================
# AYARLAR
# ==========================================
TELEGRAM_TOKEN = "8952900507:AAGH_Veh5mz3zqZqX9oz8qvr_FCuOAii76s"
WP_API_URL = "https://fotografikya.net.tr/wp-json/wp/v2"
WP_USER = "fotografikya"
WP_APP_PASSWORD = "InZB IDmf a1AA Bm6j qcxA 2l2Q"
ADMIN_ID = 7649807507

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

PHOTO, TITLE, CONTENT, CATEGORY = range(4)

async def check_admin(update: Update) -> bool:
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        if update.message: await update.message.reply_text("Bu botu kullanma yetkiniz yok.")
        return False
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await check_admin(update): return ConversationHandler.END
    msg = "👋 Merhaba! WordPress'e içerik gönderme sihirbazına hoş geldin.\n\n👉 Lütfen öne çıkan görsel yapmak istediğin **fotoğrafı gönder**."
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(msg)
    else:
        await update.message.reply_text(msg)
    return PHOTO

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    photo_file = await update.message.photo[-1].get_file()
    file_path = "temp_image.jpg"
    await photo_file.download_to_drive(file_path)
    context.user_data['photo_path'] = file_path
    await update.message.reply_text("📸 Harika! Görseli aldım.\n\n📝 Lütfen şimdi yazının **BAŞLIĞINI** gönder.")
    return TITLE

async def title_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['title'] = update.message.text.strip()
    await update.message.reply_text("✅ Başlık kaydedildi.\n\n✍️ Şimdi lütfen yazının **İÇERİĞİNİ** (metnini) gönder.")
    return CONTENT

async def content_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['content'] = update.message.text.strip()
    await update.message.reply_text("✅ İçerik kaydedildi. WordPress'ten kategoriler getiriliyor, lütfen bekle...")
    try:
        response = requests.get(f"{WP_API_URL}/categories", auth=(WP_USER, WP_APP_PASSWORD))
        response.raise_for_status()
        categories = response.json()
        keyboard = [[InlineKeyboardButton(cat['name'], callback_data=str(cat['id']))] for cat in categories]
        await update.message.reply_text("📂 Lütfen bu yazı için bir **kategori seç:**", reply_markup=InlineKeyboardMarkup(keyboard))
        return CATEGORY
    except Exception as e:
        logger.error(f"Kategori çekme hatası: {e}")
        keyboard = [[InlineKeyboardButton("🔄 Yeniden Başla", callback_data="restart")]]
        await update.message.reply_text("❌ Kategoriler çekilirken bir hata oluştu.", reply_markup=InlineKeyboardMarkup(keyboard))
        return ConversationHandler.END

async def category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    category_id = int(query.data)
    title = context.user_data['title']
    content = context.user_data['content']
    photo_path = context.user_data['photo_path']
    await query.edit_message_text("⏳ Seçim yapıldı! Yükleme işlemi başlatılıyor...")
    try:
        media_url = f"{WP_API_URL}/media"
        headers = {'Content-Disposition': 'attachment; filename="telegram_gorsel.jpg"', 'Content-Type': 'image/jpeg'}
        with open(photo_path, 'rb') as f:
            media_res = requests.post(media_url, headers=headers, auth=(WP_USER, WP_APP_PASSWORD), data=f)
        media_res.raise_for_status()
        media_id = media_res.json().get('id')
        post_url = f"{WP_API_URL}/posts"
        post_data = {'title': title, 'content': content, 'status': 'publish', 'featured_media': media_id, 'categories': [category_id]}
        post_res = requests.post(post_url, auth=(WP_USER, WP_APP_PASSWORD), json=post_data)
        post_res.raise_for_status()
        post_link = post_res.json().get('link')
        keyboard = [[InlineKeyboardButton("🔄 Yeniden Başla", callback_data="restart")]]
        await query.message.reply_text(f"✅ Yazın başarıyla yayınlandı!\n\n🔗 Linki: {post_link}", reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        logger.error(f"Yükleme hatası: {e}")
        keyboard = [[InlineKeyboardButton("🔄 Yeniden Başla", callback_data="restart")]]
        await query.message.reply_text("❌ Yükleme sırasında bir hata oluştu.", reply_markup=InlineKeyboardMarkup(keyboard))
    finally:
        if os.path.exists(photo_path): os.remove(photo_path)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [[InlineKeyboardButton("🔄 Yeniden Başla", callback_data="restart")]]
    await update.message.reply_text("🛑 İşlem iptal edildi.", reply_markup=InlineKeyboardMarkup(keyboard))
    if 'photo_path' in context.user_data and os.path.exists(context.user_data['photo_path']):
        os.remove(context.user_data['photo_path'])
    return ConversationHandler.END

def main() -> None:
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CallbackQueryHandler(start, pattern="^restart$")
        ],
        states={
            PHOTO: [MessageHandler(filters.PHOTO, photo_handler)],
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, title_handler)],
            CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, content_handler)],
            CATEGORY: [CallbackQueryHandler(category_callback, pattern=r"^\d+$")],
        },
        fallbacks=[CommandHandler("iptal", cancel)],
    )
    application.add_handler(conv_handler)
    print("✅ Bot çalışıyor!")
    application.run_polling()

if __name__ == "__main__":
    main()
