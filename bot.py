import logging
import requests
import os
import json
import re
import html
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
    WAIT_WP_USER, WAIT_WP_PASS, # Yeni eklenen WP bilgileri aşamaları
    PHOTO, TITLE, CONTENT, CATEGORY,
    WAIT_SUPPORT_MESSAGE
) = range(15)


# ==========================================
# 👥 KULLANICI YÖNETİMİ SİSTEMİ
# ==========================================

def load_users():
    """Kayıtlı kullanıcıları WP kimlik bilgileriyle birlikte dict olarak yükler."""
    default_data = {"ids": {}, "usernames": {}, "phones": {}}
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                
                # Eski sürümdeki list formatından yeni sözlük (dict) formatına otomatik taşıma
                if isinstance(data, list) or (isinstance(data, dict) and isinstance(data.get("ids", []), list)):
                    new_data = {"ids": {}, "usernames": {}, "phones": {}}
                    if isinstance(data, list):
                        for i in data: new_data["ids"][str(i)] = {"wp_user": WP_USER, "wp_pass": WP_APP_PASSWORD}
                    else:
                        for i in data.get("ids", []): new_data["ids"][str(i)] = {"wp_user": WP_USER, "wp_pass": WP_APP_PASSWORD}
                        for u in data.get("usernames", []): new_data["usernames"][u] = {"wp_user": WP_USER, "wp_pass": WP_APP_PASSWORD}
                        for p in data.get("phones", []): new_data["phones"][p] = {"wp_user": WP_USER, "wp_pass": WP_APP_PASSWORD}
                    return new_data
                    
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

def get_wp_creds(user):
    """Kullanıcının kimliğine göre kendine ait WP Kullanıcı Adı ve Şifresini getirir."""
    if user.id == ADMIN_ID:
        return WP_USER, WP_APP_PASSWORD
        
    users_data = load_users()
    
    if str(user.id) in users_data.get("ids", {}):
        creds = users_data["ids"][str(user.id)]
        return creds.get("wp_user", WP_USER), creds.get("wp_pass", WP_APP_PASSWORD)
        
    clean_username = user.username.lower().replace("@", "") if user.username else ""
    if clean_username in users_data.get("usernames", {}):
        creds = users_data["usernames"][clean_username]
        return creds.get("wp_user", WP_USER), creds.get("wp_pass", WP_APP_PASSWORD)
        
    return WP_USER, WP_APP_PASSWORD

async def send_to_log_channel(context: ContextTypes.DEFAULT_TYPE, text: str):
    """Log kanalına HTML formatında bilgi mesajı gönderir."""
    try:
        await context.bot.send_message(chat_id=LOG_CHANNEL_ID, text=text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Log kanalına mesaj gönderilemedi: {e}")

def is_user_auth(user) -> bool:
    """Kullanıcının sisteme erişim yetkisi olup olmadığını kontrol eder."""
    if user.id == ADMIN_ID:
        return True

    users_data = load_users()
    if str(user.id) in users_data.get("ids", {}):
        return True
        
    if user.username:
        clean_username = user.username.lower().replace("@", "")
        if clean_username in users_data.get("usernames", {}):
            return True

    return False

# ==========================================
# 📱 MENÜ VE ARAYÜZ YÖNETİMİ
# ==========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Botu başlatır ve kişiselleştirilmiş ana menüyü gösterir."""
    user = update.effective_user
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()

    msg = f"👋 Merhaba {full_name}!\n\n"
    keyboard = []

    if is_user_auth(user):
        msg += "Fotografikya İçerik Gönderme Botuna Hoş Geldin.\nLütfen yapmak istediğin işlemi aşağıdan seç:"
        keyboard.append([InlineKeyboardButton("📝 Yeni İçerik Ekle", callback_data="add_post")])
        
        if user.id == ADMIN_ID:
            keyboard.append([InlineKeyboardButton("👥 Kullanıcı Yönetimi", callback_data="user_mgmt")])
    else:
        msg += "⛔ Bu botu kullanma yetkiniz bulunmuyor.\nYetki talep etmek veya bizimle iletişime geçmek için aşağıdan destek talebi oluşturabilirsiniz."

    keyboard.append([InlineKeyboardButton("📞 Destek Talebi", callback_data="support_ticket")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(msg, reply_markup=reply_markup)
    else:
        await update.message.reply_text(msg, reply_markup=reply_markup)
        
    return MAIN_MENU

async def show_user_management(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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
    query = update.callback_query
    await query.answer()
    users_data = load_users()

    msg = "📋 **Güncel Yetkili Listesi**\n\n"
    
    msg += "🆔 **ID'ler:**\n"
    for uid, creds in users_data.get("ids", {}).items(): 
        msg += f"- `{uid}` (WP: {creds.get('wp_user', 'Bilinmiyor')})\n"
    if not users_data.get("ids"): msg += "- Yok\n"

    msg += "\n👤 **Kullanıcı Adları:**\n"
    for uname, creds in users_data.get("usernames", {}).items(): 
        msg += f"- @{uname} (WP: {creds.get('wp_user', 'Bilinmiyor')})\n"
    if not users_data.get("usernames"): msg += "- Yok\n"

    msg += "\n📱 **Telefon Numaraları:**\n"
    for phone, creds in users_data.get("phones", {}).items(): 
        msg += f"- {phone} (WP: {creds.get('wp_user', 'Bilinmiyor')})\n"
    if not users_data.get("phones"): msg += "- Yok\n"

    keyboard = [[InlineKeyboardButton("🔙 Geri Dön", callback_data="user_mgmt")]]
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return ADMIN_MENU

async def show_add_method_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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

async def prompt_input(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt_msg: str, next_state: int) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(f"{prompt_msg}\n\n*(İşlemi iptal etmek için /iptal yazabilirsiniz)*")
    return next_state

# --- EKLEME VE WP BİLGİ ALMA İŞLEYİCİLERİ ---
async def handle_add_step1(update: Update, context: ContextTypes.DEFAULT_TYPE, key: str, data_type: type) -> int:
    """Kullanıcının ID/Username/Tel numarasını alır ve WP Kullanıcı adını sorar."""
    val = update.message.text.strip()
    try:
        if data_type == int:
            val = str(int(val))
        elif key == "usernames":
            val = val.lower().replace("@", "")
    except ValueError:
        await update.message.reply_text("⚠️ Hatalı format. İşlem iptal edildi.\n/start ile menüye dönebilirsiniz.")
        return ConversationHandler.END

    context.user_data['add_key'] = key
    context.user_data['add_val'] = val
    
    await update.message.reply_text(
        f"✅ Kullanıcı tanımlandı: {val}\n\n"
        "👤 Lütfen bu kullanıcının içerik yayınlarken kullanacağı **WordPress Kullanıcı Adını** girin:\n"
        "*(İşlemi iptal etmek için /iptal)*"
    )
    return WAIT_WP_USER

async def handle_add_wp_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """WP Kullanıcı adını alır ve şifreyi sorar."""
    context.user_data['add_wp_user'] = update.message.text.strip()
    await update.message.reply_text(
        "🔑 Lütfen bu kullanıcının **WordPress Uygulama Şifresini** girin:\n"
        "*(Boşluklu veya boşluksuz şekilde yapıştırabilirsiniz)*"
    )
    return WAIT_WP_PASS

async def handle_add_wp_pass(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """WP Şifresini alır ve tüm veriyi kaydeder."""
    wp_pass = update.message.text.strip()
    key = context.user_data['add_key']
    val = context.user_data['add_val']
    wp_user = context.user_data['add_wp_user']
    
    users_data = load_users()
    admin_name = html.escape(update.effective_user.full_name)
    val_safe = html.escape(str(val))
    
    # Kullanıcıyı WP bilgileriyle birlikte kaydet veya güncelle
    users_data[key][val] = {"wp_user": wp_user, "wp_pass": wp_pass}
    save_users(users_data)
    
    msg = f"✅ Kullanıcı başarıyla eklendi/güncellendi!\nTanım: {val}\nWP User: {wp_user}"
    await send_to_log_channel(
        context, 
        f"⚙️ <b>Kullanıcı Eklendi/Güncellendi</b>\n"
        f"👤 Yönetici: {admin_name}\n"
        f"➕ Tanım: <code>{val_safe}</code>\n"
        f"🗂 Tür: {key.upper()}\n"
        f"🌐 WP Hesabı: {html.escape(wp_user)}"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Kullanıcı Yönetimi", callback_data="user_mgmt")]]
    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))
    return MAIN_MENU

# Sarmalayıcılar (Add)
async def handle_add_id(u: Update, c: ContextTypes.DEFAULT_TYPE): return await handle_add_step1(u, c, "ids", int)
async def handle_add_username(u: Update, c: ContextTypes.DEFAULT_TYPE): return await handle_add_step1(u, c, "usernames", str)
async def handle_add_phone(u: Update, c: ContextTypes.DEFAULT_TYPE): return await handle_add_step1(u, c, "phones", str)

# --- SİLME İŞLEYİCİSİ ---
async def process_user_remove(update: Update, context: ContextTypes.DEFAULT_TYPE, key: str, data_type: type) -> int:
    val = update.message.text.strip()
    try:
        if data_type == int:
            val = str(int(val))
        elif key == "usernames":
            val = val.lower().replace("@", "")
    except ValueError:
        await update.message.reply_text("⚠️ Hatalı format. İşlem iptal edildi.")
        return ConversationHandler.END

    users_data = load_users()
    admin_name = html.escape(update.effective_user.full_name)
    val_safe = html.escape(str(val))
    
    if val in users_data[key]:
        del users_data[key][val]
        msg = f"✅ Başarıyla silindi: {val}"
        await send_to_log_channel(context, f"⚙️ <b>Kullanıcı Silindi</b>\n👤 Yönetici: {admin_name}\n➖ Silinen: <code>{val_safe}</code>\n🗂 Tür: {key.upper()}")
    else:
        msg = f"⚠️ Listede bulunamadı: {val}"

    save_users(users_data)
    keyboard = [[InlineKeyboardButton("🔙 Kullanıcı Yönetimi", callback_data="user_mgmt")]]
    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))
    return MAIN_MENU

# Sarmalayıcılar (Remove)
async def handle_rem_id(u: Update, c: ContextTypes.DEFAULT_TYPE): return await process_user_remove(u, c, "ids", int)
async def handle_rem_username(u: Update, c: ContextTypes.DEFAULT_TYPE): return await process_user_remove(u, c, "usernames", str)
async def handle_rem_phone(u: Update, c: ContextTypes.DEFAULT_TYPE): return await process_user_remove(u, c, "phones", str)


# ==========================================
# 📝 İÇERİK EKLEME SİHİRBAZI
# ==========================================

async def start_post_wizard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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
    photo_file = await update.message.photo[-1].get_file()
    file_path = "temp_image.jpg"
    await photo_file.download_to_drive(file_path)
    context.user_data['photo_path'] = file_path

    await update.message.reply_text("📸 Görsel alındı!\n\n📝 Şimdi lütfen yazının **BAŞLIĞINI** gönderin.")
    return TITLE

async def title_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['title'] = update.message.text.strip()
    await update.message.reply_text("✅ Başlık kaydedildi.\n\n✍️ Şimdi lütfen yazının **İÇERİĞİNİ** gönderin.")
    return CONTENT

async def content_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['content'] = update.message.text.strip()
    msg = await update.message.reply_text("✅ İçerik kaydedildi. Kategoriler getiriliyor, lütfen bekleyin...")

    # Dinamik API Yetkilerini Çekiyoruz
    wp_user, wp_pass = get_wp_creds(update.effective_user)

    try:
        response = requests.get(f"{WP_API_URL}/categories", auth=(wp_user, wp_pass))
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
        await msg.edit_text("❌ Kategoriler çekilirken hata oluştu. Hesabınızın yetkilerini kontrol edin.", reply_markup=InlineKeyboardMarkup(keyboard))
        return MAIN_MENU

async def category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    category_id = int(query.data)
    title = context.user_data.get('title', '')
    content = context.user_data.get('content', '')
    photo_path = context.user_data.get('photo_path', '')
    user = update.effective_user

    # Dinamik API Yetkilerini Çekiyoruz
    wp_user, wp_pass = get_wp_creds(user)

    await query.edit_message_text(f"⏳ İşlem başlatılıyor. İçerik {wp_user} hesabıyla yayınlanıyor...")

    try:
        # 1. Görseli Yükle
        media_url = f"{WP_API_URL}/media"
        headers = {'Content-Disposition': 'attachment; filename="telegram_gorsel.jpg"', 'Content-Type': 'image/jpeg'}
        with open(photo_path, 'rb') as f:
            media_res = requests.post(media_url, headers=headers, auth=(wp_user, wp_pass), data=f)
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
        post_res = requests.post(post_url, auth=(wp_user, wp_pass), json=post_data)
        post_res.raise_for_status()
        post_link = post_res.json().get('link')

        keyboard = [[InlineKeyboardButton("🔙 Ana Menüye Dön", callback_data="restart")]]
        await query.message.reply_text(f"✅ Yazı başarıyla yayınlandı!\n\n🔗 Link: {post_link}", reply_markup=InlineKeyboardMarkup(keyboard))

        await send_to_log_channel(
            context, 
            f"✅ <b>Yeni İçerik Yayınlandı!</b>\n"
            f"👤 Ekleyen: {html.escape(user.full_name)}\n"
            f"🌐 WP Hesabı: {html.escape(wp_user)}\n"
            f"📝 Başlık: {html.escape(title)}\n"
            f"🔗 <a href='{post_link}'>Yazıyı Görüntüle</a>"
        )

    except Exception as e:
        logger.error(f"Yayınlama hatası: {e}")
        keyboard = [[InlineKeyboardButton("🔙 Ana Menüye Dön", callback_data="restart")]]
        await query.message.reply_text("❌ Yükleme sırasında bir hata oluştu. (Yetkiler geçersiz olabilir)", reply_markup=InlineKeyboardMarkup(keyboard))
        
        await send_to_log_channel(context, f"❌ <b>İçerik Yükleme Hatası</b>\n👤 Kullanıcı: {html.escape(user.full_name)}\n🌐 WP Hesabı: {html.escape(wp_user)}\n⚠️ Hata: {html.escape(str(e))}")
    finally:
        if os.path.exists(photo_path):
            os.remove(photo_path)

    return MAIN_MENU

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if 'photo_path' in context.user_data and os.path.exists(context.user_data['photo_path']):
        os.remove(context.user_data['photo_path'])
        
    keyboard = [[InlineKeyboardButton("🔙 Ana Menüye Dön", callback_data="restart")]]
    await update.message.reply_text("🛑 İşlem iptal edildi.", reply_markup=InlineKeyboardMarkup(keyboard))
    return MAIN_MENU

# ==========================================
# 📞 DESTEK SİSTEMİ
# ==========================================

async def start_support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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
    user = update.effective_user
    message_text = update.message.text

    log_msg = (
        f"📢 <b>YENİ DESTEK TALEBİ</b>\n"
        f"👤 Gönderen: {html.escape(user.full_name)} (@{html.escape(user.username or 'Yok')})\n"
        f"🆔 ID: <code>{user.id}</code>\n\n"
        f"📝 Mesaj:\n{html.escape(message_text)}"
    )

    await send_to_log_channel(context, log_msg)

    keyboard = [[InlineKeyboardButton("🔙 Ana Menüye Dön", callback_data="restart")]]
    await update.message.reply_text(
        "✅ Mesajınız yetkililere başarıyla iletildi. En kısa sürede size dönüş yapılacaktır.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return MAIN_MENU

async def support_reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not is_user_auth(update.effective_user): return
    if not msg or not msg.reply_to_message: return
    
    replied_text = msg.reply_to_message.text or msg.reply_to_message.caption
    if not replied_text: return

    match = re.search(r"🆔 ID:\s*(\d+)", replied_text)
    if not match: return

    user_id = int(match.group(1))
    reply_text = msg.text or msg.caption or "*(Destek ekibi size bir dosya/medya gönderdi)*"

    try:
        if msg.text:
            await context.bot.send_message(chat_id=user_id, text=f"📞 <b>Destek Ekibinden Yanıt Geldi:</b>\n\n{html.escape(reply_text)}", parse_mode="HTML")
        else:
            await context.bot.send_message(chat_id=user_id, text="📞 <b>Destek Ekibinden Yanıt Geldi:</b>", parse_mode="HTML")
            await msg.copy(chat_id=user_id)
        await msg.reply_text("✅ Yanıtınız kullanıcıya başarıyla iletildi.")
    except Exception as e:
        logger.error(f"Kullanıcıya yanıt iletilemedi: {e}")
        await msg.reply_text(f"❌ Yanıt iletilemedi. (Kullanıcı botu engellemiş veya ID hatalı olabilir)\nHata Detayı: {e}")

def main() -> None:
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(MessageHandler(filters.REPLY, support_reply_handler))

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
                
                # Ekleme Metotları Başlangıcı
                CallbackQueryHandler(lambda u, c: prompt_input(u, c, "Lütfen eklenecek kişinin TELEGRAM ID'sini yazın:", WAIT_ADD_ID), pattern="^add_id$"),
                CallbackQueryHandler(lambda u, c: prompt_input(u, c, "Lütfen eklenecek kişinin KULLANICI ADINI (@ olmadan) yazın:", WAIT_ADD_USERNAME), pattern="^add_username$"),
                CallbackQueryHandler(lambda u, c: prompt_input(u, c, "Lütfen eklenecek kişinin TELEFON NUMARASINI (Örn: +90555...) yazın:", WAIT_ADD_PHONE), pattern="^add_phone$"),
                
                # Silme Metotları Başlangıcı
                CallbackQueryHandler(lambda u, c: prompt_input(u, c, "Lütfen silinecek kişinin TELEGRAM ID'sini yazın:", WAIT_REMOVE_ID), pattern="^rem_id$"),
                CallbackQueryHandler(lambda u, c: prompt_input(u, c, "Lütfen silinecek kişinin KULLANICI ADINI (@ olmadan) yazın:", WAIT_REMOVE_USERNAME), pattern="^rem_username$"),
                CallbackQueryHandler(lambda u, c: prompt_input(u, c, "Lütfen silinecek kişinin TELEFON NUMARASINI yazın:", WAIT_REMOVE_PHONE), pattern="^rem_phone$"),
            ],
            
            # Ekleme Girişleri ve WP Bilgi Alımları
            WAIT_ADD_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_id)],
            WAIT_ADD_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_username)],
            WAIT_ADD_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_phone)],
            WAIT_WP_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_wp_user)],
            WAIT_WP_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_wp_pass)],
            
            # Silme Girişleri
            WAIT_REMOVE_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_rem_id)],
            WAIT_REMOVE_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_rem_username)],
            WAIT_REMOVE_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_rem_phone)],

            WAIT_SUPPORT_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_support_ticket)],

            PHOTO: [MessageHandler(filters.PHOTO, photo_handler)],
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, title_handler)],
            CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, content_handler)],
            CATEGORY: [CallbackQueryHandler(category_callback, pattern=r"^\d+$")],
        },
        fallbacks=[CommandHandler("iptal", cancel), CommandHandler("start", start)],
    )

    application.add_handler(conv_handler)
    print("✅ Bot başarıyla çalışıyor! WP API yetkileri dinamik hale getirildi.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
