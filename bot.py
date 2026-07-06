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
# 🛑 BİLGİLERİN EKLENDİ 🛑
# ==========================================

# 1. Telegram Bot Token
TELEGRAM_TOKEN = "8952900507:AAGH_Veh5mz3zqZqX9oz8qvr_FCuOAii76s"

# 2. WordPress Site Adresin
WP_API_URL = "https://fotografikya.net.tr/wp-json/wp/v2"

# 3. WordPress Kullanıcı Adın
WP_USER = "fotografikya"

# 4. WordPress Uygulama Şifresi
WP_APP_PASSWORD = "InZB IDmf a1AA Bm6j qcxA 2l2Q"

# Yalnızca senin kullanabilmen için kendi Telegram Kullanıcı ID'n
ADMIN_ID = 7649807507

# ==========================================
# 🛑 AYARLAR BİTTİ - AŞAĞISINA DOKUNMA 🛑
# ==========================================

# Loglama ayarları (Hataları görmek için)
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Konuşma durumları (Başlık ve İçerik ayrıldı)
PHOTO, TITLE, CONTENT, CATEGORY = range(4)

async def check_admin(update: Update) -> bool:
    """Sadece senin kullanmanı sağlayan güvenlik kontrolü."""
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        if update.message:
            await update.message.reply_text("Bu botu kullanma yetkiniz yok.")
        elif update.callback_query:
            await update.callback_query.answer("Bu botu kullanma yetkiniz yok.", show_alert=True)
        return False
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Botu başlatır ve fotoğraf ister."""
    if not await check_admin(update):
        return ConversationHandler.END

    msg = (
        "👋 Merhaba! WordPress'e içerik gönderme sihirbazına hoş geldin.\n\n"
        "👉 Lütfen öne çıkan görsel yapmak istediğin **fotoğrafı gönder**.\n"
        "*(İşlemi iptal etmek için /iptal yazabilirsin)*"
    )

    # Eğer buton ile tetiklendiyse message objesi callback_query içindedir
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(msg)
    else:
        await update.message.reply_text(msg)
        
    return PHOTO

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Fotoğrafı alır ve hafızaya kaydeder, ardından başlığı ister."""
    photo_file = await update.message.photo[-1].get_file()
    
    # Fotoğrafı geçici olarak indir
    file_path = "temp_image.jpg"
    await photo_file.download_to_drive(file_path)
    
    context.user_data['photo_path'] = file_path

    await update.message.reply_text(
        "📸 Harika! Görseli aldım.\n\n"
        "📝 Lütfen şimdi yazının **BAŞLIĞINI** gönder."
    )
    return TITLE

async def title_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Başlığı alır ve içeriği ister."""
    context.user_data['title'] = update.message.text.strip()
    
    await update.message.reply_text(
        "✅ Başlık kaydedildi.\n\n"
        "✍️ Şimdi lütfen yazının **İÇERİĞİNİ** (metnini) gönder."
    )
    return CONTENT

async def content_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """İçeriği alır, WordPress'ten kategorileri çekip buton olarak sunar."""
    context.user_data['content'] = update.message.text.strip()

    await update.message.reply_text("✅ İçerik kaydedildi. WordPress'ten kategoriler getiriliyor, lütfen bekle...")

    # WP'den kategorileri çek
    try:
        response = requests.get(f"{WP_API_URL}/categories", auth=(WP_USER, WP_APP_PASSWORD))
        response.raise_for_status()
        categories = response.json()
        
        keyboard = []
        for cat in categories:
            keyboard.append([InlineKeyboardButton(cat['name'], callback_data=str(cat['id']))])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("📂 Lütfen bu yazı için bir **kategori seç:**", reply_markup=reply_markup)
        return CATEGORY
    except Exception as e:
        logger.error(f"Kategori çekme hatası: {e}")
        
        # Hata durumunda yeniden başlama butonu sunalım
        keyboard = [[InlineKeyboardButton("🔄 Yeniden Başla", callback_data="restart")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("❌ Kategoriler çekilirken bir hata oluştu.", reply_markup=reply_markup)
        return ConversationHandler.END

async def category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Kategori seçildiğinde çalışır: Görseli yükler ve yazıyı paylaşır."""
    query = update.callback_query
    await query.answer()
    
    category_id = int(query.data)
    title = context.user_data['title']
    content = context.user_data['content']
    photo_path = context.user_data['photo_path']

    await query.edit_message_text("⏳ Seçim yapıldı! Yükleme işlemi başlatılıyor. (Bu biraz sürebilir)...")

    try:
        # 1. Görseli Yükle
        media_url = f"{WP_API_URL}/media"
        headers = {
            'Content-Disposition': 'attachment; filename="telegram_gorsel.jpg"',
            'Content-Type': 'image/jpeg'
        }
        with open(photo_path, 'rb') as f:
            media_res = requests.post(media_url, headers=headers, auth=(WP_USER, WP_APP_PASSWORD), data=f)
        media_res.raise_for_status()
        media_id = media_res.json().get('id')

        # 2. İçeriği Yayınla
        post_url = f"{WP_API_URL}/posts"
        post_data = {
            'title': title,
            'content': content,
            'status': 'publish', # Taslak yapmak istersen 'draft' yazabilirsin
            'featured_media': media_id,
            'categories': [category_id]
        }
        post_res = requests.post(post_url, auth=(WP_USER, WP_APP_PASSWORD), json=post_data)
        post_res.raise_for_status()
        post_link = post_res.json().get('link')

        # Başarılı olduğunda yeniden başlama butonu ekleyelim
        keyboard = [[InlineKeyboardButton("🔄 Yeniden Başla", callback_data="restart")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.reply_text(
            f"✅ Yazın başarıyla yayınlandı!\n\n🔗 Linki: {post_link}",
            reply_markup=reply_markup
        )

    except Exception as e:
        logger.error(f"Yükleme hatası: {e}")
        keyboard = [[InlineKeyboardButton("🔄 Yeniden Başla", callback_data="restart")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text("❌ Yükleme sırasında bir hata oluştu. Lütfen logları kontrol et.", reply_markup=reply_markup)
    finally:
        # Geçici fotoğrafı sil
        if os.path.exists(photo_path):
            os.remove(photo_path)

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """İşlemi iptal eder."""
    keyboard = [[InlineKeyboardButton("🔄 Yeniden Başla", callback_data="restart")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text("🛑 İşlem iptal edildi.", reply_markup=reply_markup)
    
    if 'photo_path' in context.user_data and os.path.exists(context.user_data['photo_path']):
        os.remove(context.user_data['photo_path'])
        
    return ConversationHandler.END

def main() -> None:
    """Botu çalıştırır."""
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CallbackQueryHandler(start, pattern="^restart$") # Yeniden başla butonunu yakalar
        ],
        states={
            PHOTO: [MessageHandler(filters.PHOTO, photo_handler)],
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, title_handler)],
            CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, content_handler)],
            # Kategori seçimi için yalnızca sayısal (ID) callback'leri yakalar
            CATEGORY: [CallbackQueryHandler(category_callback, pattern=r"^\d+$")],
        },
        fallbacks=[CommandHandler("iptal", cancel)],
    )

    application.add_handler(conv_handler)
    
    print("✅ Bot başarıyla çalışıyor! Telegram'a gidip /start yazabilirsin...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
