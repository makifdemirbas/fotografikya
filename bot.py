import logging
import requests
import os
import json
import re
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

TELEGRAM_TOKEN = "8952900507:AAGH_Veh5mz3zqZqX9oz8qvr_FCuOAii76s"
WP_API_URL = "https://fotografikya.net.tr/wp-json/wp/v2"
WP_USER = "fotografikya"
WP_APP_PASSWORD = "InZB IDmf a1AA Bm6j qcxA 2l2Q"
ADMIN_ID = 7649807507
USERS_FILE = "allowed_users.json"
LOG_CHANNEL_ID = -1004420671588

# ==========================================
# 🛑 AYARLAR BİTTİ - AŞAĞISINA DOKUNMA 🛑
# ==========================================

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Konuşma Durumları (State Machine)
(
    MAIN_MENU,
    ADMIN_MENU,
    WAIT_ADD_ID, WAIT_ADD_USERNAME, WAIT_ADD_PHONE,
    WAIT_REMOVE_ID, WAIT_REMOVE_USERNAME, WAIT_REMOVE_PHONE,
    PHOTO, TITLE, CONTENT, CATEGORY,
    WAIT_SUPPORT_MESSAGE
) = range(13)


# ==========================================
# 👥 KULLANICI YÖNETİMİ SİSTEMİ
# ==========================================

def load_users():
    """Kayıtlı kullanıcıları JSON dosyasından dict olarak yükler."""
    default_data = {"ids": [], "usernames": [], "phones": []}
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Eski sürümden (sadece liste) yeni sürüme (dict) geçiş kontrolü
                if isinstance(data, list):
                    return {"ids": data, "usernames": [], "phones": []}
                return data
        except Exception as e:
            logger.error(f"Kullanıcılar yüklenirken hata: {e}")
            return default_data
    return default_data

def save_users(users_data):
    """Kullanıcı verilerini JSON dosyasına kaydeder."""
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users_data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Kullanıcılar kaydedilirken hata: {e}")

async def send_to_log_channel(context: ContextTypes.DEFAULT_TYPE, text: str):
    """Log kanalına bilgi mesajı gönderir."""
    try:
        await context.bot.send_message(chat_id=LOG_CHANNEL_ID, text=text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Log kanalına mesaj gönderilemedi: {e}")

def is_user_auth(user) -> bool:
    """Kullanıcının sisteme erişim yetkisi olup olmadığını kontrol eder."""
    # Ana yönetici her zaman girebilir
    if user.id == ADMIN_ID:
        return True

    users_data = load_users()
    
    # 1. ID Kontrolü
    if user.id in users_data.get("ids", []):
        return True
        
    # 2. Kullanıcı Adı Kontrolü
    if user.username:
        clean_username = user.username.lower().replace("@", "")
        saved_usernames = [u.lower().replace("@", "") for u in users_data.get("usernames", [])]
        if clean_username in saved_usernames:
            return True

    return False

# ==========================================
# 📱 MENÜ VE ARAYÜZ YÖNETİMİ
# ==========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Botu başlatır ve kişiselleştirilmiş ana menüyü gösterir."""
    user = update.effective_user
    
    # Kullanıcı ismi ile hitap
    first_name = user.first_name or ""
    last_name = user.last_name or ""
    full_name = f"{first_name} {last_name}".strip()

    msg = f"👋 Merhaba {full_name}!\n\n"
    keyboard = []

    if is_user_auth(user):
        msg += "Fotografikya İçerik Gönderme Botuna Hoş Geldin.\nLütfen yapmak istediğin işlemi aşağıdan seç:"
        keyboard.append([InlineKeyboardButton("📝 Yeni İçerik Ekle", callback_data="add_post")])
        
        # Sadece ana yöneticiye Kullanıcı Yönetimi butonunu göster
        if user.id == ADMIN_ID:
            keyboard.append([InlineKeyboardButton("👥 Kullanıcı Yönetimi", callback_data="user_mgmt")])
    else:
        msg += "⛔ Bu botu kullanma yetkiniz bulunmuyor.\nYetki talep etmek veya bizimle iletişime geçmek için aşağıdan destek talebi oluşturabilirsiniz."

    # Herkese destek talebi butonu gösterilir
    keyboard.append([InlineKeyboardButton("📞 Destek Talebi", callback_data="support_ticket")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(msg, reply_markup=reply_markup)
    else:
        await update.message.reply_text(msg, reply_markup=reply_markup)
        
    return MAIN_MENU

# --- YÖNETİCİ MENÜSÜ ---
async def show_user_management(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Kullanıcı Yönetimi ana menüsünü gösterir."""
    if update.effective_user.id != ADMIN_ID:
        await update.callback_query.answer("⛔ Bu alana sadece ana yönetici girebilir!", show_alert=True)
        return MAIN_MENU
        
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("➕ Yeni Kullanıcı Ekle", callback_data="admin_add")],
        [InlineKeyboardButton("➖ Kullanıcı Sil", callback_data="admin_remove")],
        [InlineKeyboardButton("📋 Yetkilileri Listele", callback_data="admin_list")],
        [InlineKeyboardButton("🔙 Ana Menüye Dön", callback_data="back_main")]
    ]
    await query.edit_message_text("👥 **Kullanıcı Yönetimi Paneli**\n\nLütfen bir işlem seçin:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return ADMIN_MENU

async def admin_list_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Kayıtlı tüm kullanıcıları listeler."""
    query = update.callback_query
    await query.answer()
    users_data = load_users()

    msg = "📋 **Güncel Yetkili Listesi**\n\n"
    
    msg += "🆔 **ID'ler:**\n"
    for uid in users_data.get("ids", []): msg += f"- `{uid}`\n"
    if not users_data.get("ids"): msg += "- Yok\n"

    msg += "\n👤 **Kullanıcı Adları:**\n"
    for uname in users_data.get("usernames", []): msg += f"- @{uname}\n"
    if not users_data.get("usernames"): msg += "- Yok\n"

    msg += "\n📱 **Telefon Numaraları:**\n"
    for phone in users_data.get("phones", []): msg += f"- {phone}\n"
    if not users_data.get("phones"): msg += "- Yok\n"

    keyboard = [[InlineKeyboardButton("🔙 Geri Dön", callback_data="user_mgmt")]]
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return ADMIN_MENU

async def show_add_method_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Kullanıcı ekleme yöntemini (ID, Username, Telefon) sorar."""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🆔 ID ile Ekle", callback_data="add_id")],
        [InlineKeyboardButton("👤 Kullanıcı Adı ile Ekle", callback_data="add_username")],
        [InlineKeyboardButton("📱 Telefon ile Ekle", callback_data="add_phone")],
        [InlineKeyboardButton("🔙 İptal / Geri Dön", callback_data="user_mgmt")]
    ]
    await query.edit_message_text("➕ Kullanıcıyı hangi yöntemle eklemek istersiniz?", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADMIN_MENU

async def show_remove_method_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Kullanıcı silme yöntemini sorar."""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🆔 ID ile Sil", callback_data="rem_id")],
        [InlineKeyboardButton("👤 Kullanıcı Adı ile Sil", callback_data="rem_username")],
        [InlineKeyboardButton("📱 Telefon ile Sil", callback_data="rem_phone")],
        [InlineKeyboardButton("🔙 İptal / Geri Dön", callback_data="user_mgmt")]
    ]
    await query.edit_message_text("➖ Kullanıcıyı hangi yöntemle silmek istersiniz?", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADMIN_MENU

# --- GİRİŞ BEKLEME İŞLEMLERİ ---
async def prompt_input(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt_msg: str, next_state: int) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(f"{prompt_msg}\n\n*(İşlemi iptal etmek için /iptal yazabilirsiniz)*")
    return next_state

# --- EKLEME VE SİLME İŞLEYİCİLERİ ---
async def process_user_change(update: Update, context: ContextTypes.DEFAULT_TYPE, key: str, is_add: bool, data_type: type = str) -> int:
    """Kullanıcı ekleme ve silme mantığını işler."""
    val = update.message.text.strip()
    
    try:
        if data_type == int:
            val = int(val)
    except ValueError:
        await update.message.reply_text("⚠️ Hatalı format. İşlem iptal edildi.\n/start ile menüye dönebilirsiniz.")
        return ConversationHandler.END

    users_data = load_users()
    
    if is_add:
        if val not in users_data[key]:
            users_data[key].append(val)
            msg = f"✅ Başarıyla eklendi: {val}"
            await send_to_log_channel(context, f"⚙️ **Yeni Kullanıcı Eklendi**\n👤 Yönetici: {update.effective_user.full_name}\n➕ Eklenen: `{val}`\n🗂 Tür: {key.upper()}")
        else:
            msg = f"⚠️ Zaten ekli: {val}"
    else:
        if val in users_data[key]:
            users_data[key].remove(val)
            msg = f"✅ Başarıyla silindi: {val}"
            await send_to_log_channel(context, f"⚙️ **Kullanıcı Silindi**\n👤 Yönetici: {update.effective_user.full_name}\n➖ Silinen: `{val}`\n🗂 Tür: {key.upper()}")
        else:
            msg = f"⚠️ Listede bulunamadı: {val}"

    save_users(users_data)
    
    keyboard = [[InlineKeyboardButton("🔙 Kullanıcı Yönetimi", callback_data="user_mgmt")]]
    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))
    return MAIN_MENU

# Fonksiyon sarmalayıcılar
async def handle_add_id(u: Update, c: ContextTypes.DEFAULT_TYPE): return await process_user_change(u, c, "ids", True, int)
async def handle_add_username(u: Update, c: ContextTypes.DEFAULT_TYPE): return await process_user_change(u, c, "usernames", True, str)
async def handle_add_phone(u: Update, c: ContextTypes.DEFAULT_TYPE): return await process_user_change(u, c, "phones", True, str)
async def handle_rem_id(u: Update, c: ContextTypes.DEFAULT_TYPE): return await process_user_change(u, c, "ids", False, int)
async def handle_rem_username(u: Update, c: ContextTypes.DEFAULT_TYPE): return await process_user_change(u, c, "usernames", False, str)
async def handle_rem_phone(u: Update, c: ContextTypes.DEFAULT_TYPE): return await process_user_change(u, c, "phones", False, str)


# ==========================================
# 📝 İÇERİK EKLEME SİHİRBAZI
# ==========================================

async def start_post_wizard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """İçerik sihirbazını başlatır."""
    if not is_user_auth(update.effective_user):
        await update.callback_query.answer("⛔ İçerik ekleme yetkiniz yok!", show_alert=True)
        return MAIN_MENU

    query = update.callback_query
    await query.answer()
    
    msg = (
        "📸 İçerik Sihirbazı Başlıyor...\n\n"
        "👉 Lütfen öne çıkan görsel yapmak istediğiniz **fotoğrafı gönderin**.\n"
        "*(İşlemi iptal etmek için /iptal yazabilirsiniz)*"
    )
    await query.edit_message_text(msg)
    return PHOTO

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Fotoğrafı alır ve hafızaya kaydeder, ardından başlığı ister."""
    photo_file = await update.message.photo[-1].get_file()
    file_path = "temp_image.jpg"
    await photo_file.download_to_drive(file_path)
    context.user_data['photo_path'] = file_path

    await update.message.reply_text("📸 Görsel alındı!\n\n📝 Şimdi lütfen yazının **BAŞLIĞINI** gönderin.")
    return TITLE

async def title_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Başlığı alır ve içeriği ister."""
    context.user_data['title'] = update.message.text.strip()
    await update.message.reply_text("✅ Başlık kaydedildi.\n\n✍️ Şimdi lütfen yazının **İÇERİĞİNİ** gönderin.")
    return CONTENT

async def content_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """İçeriği alır, WordPress'ten kategorileri çeker."""
    context.user_data['content'] = update.message.text.strip()
    msg = await update.message.reply_text("✅ İçerik kaydedildi. Kategoriler getiriliyor, lütfen bekleyin...")

    try:
        response = requests.get(f"{WP_API_URL}/categories", auth=(WP_USER, WP_APP_PASSWORD))
        response.raise_for_status()
        categories = response.json()
        
        keyboard = []
        for cat in categories:
            keyboard.append([InlineKeyboardButton(cat['name'], callback_data=str(cat['id']))])
        
        await msg.edit_text("📂 Lütfen bu yazı için bir **kategori seçin:**", reply_markup=InlineKeyboardMarkup(keyboard))
        return CATEGORY
    except Exception as e:
        logger.error(f"Kategori hatası: {e}")
        keyboard = [[InlineKeyboardButton("🔄 Ana Menüye Dön", callback_data="restart")]]
        await msg.edit_text("❌ Kategoriler çekilirken hata oluştu.", reply_markup=InlineKeyboardMarkup(keyboard))
        return MAIN_MENU

async def category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Görseli yükler ve yazıyı paylaşır."""
    query = update.callback_query
    await query.answer()
    
    category_id = int(query.data)
    title = context.user_data.get('title', '')
    content = context.user_data.get('content', '')
    photo_path = context.user_data.get('photo_path', '')

    await query.edit_message_text("⏳ İşlem başlatılıyor. Fotoğraf yüklenip içerik yayınlanıyor (Bu biraz sürebilir)...")

    try:
        # 1. Görseli Yükle
        media_url = f"{WP_API_URL}/media"
        headers = {'Content-Disposition': 'attachment; filename="telegram_gorsel.jpg"', 'Content-Type': 'image/jpeg'}
        with open(photo_path, 'rb') as f:
            media_res = requests.post(media_url, headers=headers, auth=(WP_USER, WP_APP_PASSWORD), data=f)
        media_res.raise_for_status()
        media_id = media_res.json().get('id')

        # 2. İçeriği Yayınla
        post_url = f"{WP_API_URL}/posts"
        post_data = {
            'title': title,
            'content': content,
            'status': 'publish', 
            'featured_media': media_id,
            'categories': [category_id]
        }
        post_res = requests.post(post_url, auth=(WP_USER, WP_APP_PASSWORD), json=post_data)
        post_res.raise_for_status()
        post_link = post_res.json().get('link')

        keyboard = [[InlineKeyboardButton("🔙 Ana Menüye Dön", callback_data="restart")]]
        await query.message.reply_text(f"✅ Yazı başarıyla yayınlandı!\n\n🔗 Link: {post_link}", reply_markup=InlineKeyboardMarkup(keyboard))

        # Log kanalına bildir
        await send_to_log_channel(
            context, 
            f"✅ **Yeni İçerik Yayınlandı!**\n"
            f"👤 Ekleyen: {update.effective_user.full_name} (@{update.effective_user.username})\n"
            f"📝 Başlık: {title}\n"
            f"🔗 [Yazıyı Görüntüle]({post_link})"
        )

    except Exception as e:
        logger.error(f"Yayınlama hatası: {e}")
        keyboard = [[InlineKeyboardButton("🔙 Ana Menüye Dön", callback_data="restart")]]
        await query.message.reply_text("❌ Yükleme sırasında bir hata oluştu.", reply_markup=InlineKeyboardMarkup(keyboard))
        await send_to_log_channel(context, f"❌ **İçerik Yükleme Hatası**\n👤 Kullanıcı: {update.effective_user.full_name}\n⚠️ Hata: {e}")
    finally:
        if os.path.exists(photo_path):
            os.remove(photo_path)

    return MAIN_MENU

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """İşlemi iptal eder ve ana menü butonunu gösterir."""
    if 'photo_path' in context.user_data and os.path.exists(context.user_data['photo_path']):
        os.remove(context.user_data['photo_path'])
        
    keyboard = [[InlineKeyboardButton("🔙 Ana Menüye Dön", callback_data="restart")]]
    await update.message.reply_text("🛑 İşlem iptal edildi.", reply_markup=InlineKeyboardMarkup(keyboard))
    return MAIN_MENU

# ==========================================
# 📞 DESTEK SİSTEMİ
# ==========================================

async def start_support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Destek talebi menüsünü başlatır."""
    query = update.callback_query
    await query.answer()
    
    keyboard = [[InlineKeyboardButton("🔙 İptal / Ana Menü", callback_data="restart")]]
    await query.edit_message_text(
        "📞 **Destek Talebi**\n\nLütfen yetkililere iletmek istediğiniz mesajı aşağıya yazın.\n\n*(İşlemi iptal etmek için butonu kullanabilir veya /iptal yazabilirsiniz)*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return WAIT_SUPPORT_MESSAGE

async def receive_support_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Kullanıcının destek mesajını alır ve log kanalına iletir."""
    user = update.effective_user
    message_text = update.message.text

    log_msg = (
        f"📢 **YENİ DESTEK TALEBİ**\n"
        f"👤 Gönderen: {user.full_name} (@{user.username})\n"
        f"🆔 ID: `{user.id}`\n\n"
        f"📝 Mesaj:\n{message_text}"
    )

    await send_to_log_channel(context, log_msg)

    keyboard = [[InlineKeyboardButton("🔙 Ana Menüye Dön", callback_data="restart")]]
    await update.message.reply_text(
        "✅ Mesajınız yetkililere başarıyla iletildi. En kısa sürede size dönüş yapılacaktır.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return MAIN_MENU

async def support_reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log kanalından gelen yanıtları asıl kullanıcıya iletir."""
    msg = update.effective_message
    
    # Eğer bir mesaja yanıt verilmiyorsa işlemi sonlandır
    if not msg or not msg.reply_to_message:
        return

    replied_text = msg.reply_to_message.text or msg.reply_to_message.caption
    if not replied_text:
        return

    # Yalnızca destek taleplerindeki ID'yi bulduğunda çalışır
    match = re.search(r"🆔 ID:\s*`?(\d+)`?", replied_text)
    if not match:
        return

    user_id = int(match.group(1))
    
    # Yetkilinin mesajı veya medyası var mı?
    reply_text = msg.text or msg.caption or "*(Destek ekibi size bir dosya/medya gönderdi)*"

    try:
        if msg.text:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"📞 **Destek Ekibinden Yanıt Geldi:**\n\n{reply_text}",
                parse_mode="Markdown"
            )
        else:
            # Medya (Fotoğraf vb.) dosyası ise doğrudan kopyala
            await context.bot.send_message(
                chat_id=user_id,
                text="📞 **Destek Ekibinden Yanıt Geldi:**",
                parse_mode="Markdown"
            )
            await msg.copy(chat_id=user_id)

        await msg.reply_text("✅ Yanıtınız kullanıcıya başarıyla iletildi.")
    except Exception as e:
        logger.error(f"Kullanıcıya yanıt iletilemedi: {e}")
        await msg.reply_text(f"❌ Yanıt iletilemedi. (Kullanıcı botu engellemiş veya ID hatalı olabilir)\nHata Detayı: {e}")

def main() -> None:
    """Botu çalıştırır."""
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Log kanalındaki mesaj yanıtlarını yakalayan handler (Sohbet döngüsünden bağımsız her zaman çalışır)
    application.add_handler(MessageHandler(
        filters.Chat(LOG_CHANNEL_ID) & filters.REPLY, 
        support_reply_handler
    ))

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start), CallbackQueryHandler(start, pattern="^restart$")],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(start_post_wizard, pattern="^add_post$"),
                CallbackQueryHandler(show_user_management, pattern="^user_mgmt$"),
                CallbackQueryHandler(start_support, pattern="^support_ticket$"),
            ],
            ADMIN_MENU: [
                CallbackQueryHandler(start, pattern="^back_main$"),
                CallbackQueryHandler(show_user_management, pattern="^user_mgmt$"),
                CallbackQueryHandler(admin_list_users, pattern="^admin_list$"),
                
                CallbackQueryHandler(show_add_method_menu, pattern="^admin_add$"),
                CallbackQueryHandler(show_remove_method_menu, pattern="^admin_remove$"),
                
                # Ekleme metotları seçimi
                CallbackQueryHandler(lambda u, c: prompt_input(u, c, "Lütfen eklenecek kişinin TELEGRAM ID'sini yazın:", WAIT_ADD_ID), pattern="^add_id$"),
                CallbackQueryHandler(lambda u, c: prompt_input(u, c, "Lütfen eklenecek kişinin KULLANICI ADINI (@ olmadan) yazın:", WAIT_ADD_USERNAME), pattern="^add_username$"),
                CallbackQueryHandler(lambda u, c: prompt_input(u, c, "Lütfen eklenecek kişinin TELEFON NUMARASINI (Örn: +90555...) yazın:", WAIT_ADD_PHONE), pattern="^add_phone$"),
                
                # Silme metotları seçimi
                CallbackQueryHandler(lambda u, c: prompt_input(u, c, "Lütfen silinecek kişinin TELEGRAM ID'sini yazın:", WAIT_REMOVE_ID), pattern="^rem_id$"),
                CallbackQueryHandler(lambda u, c: prompt_input(u, c, "Lütfen silinecek kişinin KULLANICI ADINI (@ olmadan) yazın:", WAIT_REMOVE_USERNAME), pattern="^rem_username$"),
                CallbackQueryHandler(lambda u, c: prompt_input(u, c, "Lütfen silinecek kişinin TELEFON NUMARASINI yazın:", WAIT_REMOVE_PHONE), pattern="^rem_phone$"),
            ],
            
            # Ekleme Girişleri
            WAIT_ADD_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_id)],
            WAIT_ADD_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_username)],
            WAIT_ADD_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_phone)],
            
            # Silme Girişleri
            WAIT_REMOVE_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_rem_id)],
            WAIT_REMOVE_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_rem_username)],
            WAIT_REMOVE_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_rem_phone)],

            # Destek Sistemi Girişi
            WAIT_SUPPORT_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_support_ticket)],

            # WordPress Sihirbazı
            PHOTO: [MessageHandler(filters.PHOTO, photo_handler)],
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, title_handler)],
            CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, content_handler)],
            CATEGORY: [CallbackQueryHandler(category_callback, pattern=r"^\d+$")],
        },
        fallbacks=[CommandHandler("iptal", cancel), CommandHandler("start", start)],
    )

    application.add_handler(conv_handler)
    
    print("✅ Bot başarıyla çalışıyor! Menü sistemini test etmek için telegram'a gidip /start yazın.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
