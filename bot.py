import logging
import requests
import os
import json
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
# 🛑 AYARLAR VE VERİTABANI BAŞLANGICI 🛑
# ==========================================

# Telegram Bot Token (GÜVENLİĞİN İÇİN DEĞİŞTİRMELİSİN)
TELEGRAM_TOKEN = "8952900507:AAGH_Veh5mz3zqZqX9oz8qvr_FCuOAii76s"
ADMIN_ID = 7649807507

# Kullanıcı bilgilerini tutacağımız JSON dosyası
DB_FILE = "users_db.json"

# Loglama ayarları
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Tüm menü ve konuşma durumları (State Machine)
(
    MENU_ROUTING,
    PHOTO, TITLE, CONTENT, CATEGORY,          # İçerik Yükleme Adımları
    ADD_TG_ID, ADD_WP_URL, ADD_WP_USER, ADD_WP_PASS, # Kullanıcı Ekleme Adımları
    DEL_TG_ID                                 # Kullanıcı Silme Adımı
) = range(10)

# --- VERİTABANI (JSON) FONKSİYONLARI ---

def load_db():
    """Kullanıcıları JSON'dan okur. Dosya yoksa oluşturur ve Admin'i ekler."""
    if not os.path.exists(DB_FILE):
        # Varsayılan Admin Ayarları ile DB'yi başlat
        default_db = {
            str(ADMIN_ID): {
                "wp_url": "https://fotografikya.net.tr/wp-json/wp/v2",
                "wp_user": "fotografikya",
                "wp_app_password": "InZB IDmf a1AA Bm6j qcxA 2l2Q"
            }
        }
        save_db(default_db)
        return default_db
    
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(data):
    """Kullanıcıları JSON'a kaydeder."""
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def get_user_wp_data(user_id):
    """Telegram ID'sine göre WordPress bilgilerini getirir."""
    db = load_db()
    return db.get(str(user_id))

# ==========================================
# 📱 MENÜ SİSTEMİ
# ==========================================

def get_main_menu(user_id):
    """Ana Menü butonlarını oluşturur."""
    keyboard = [[InlineKeyboardButton("✍️ Yeni İçerik Ekle", callback_data="menu_post")]]
    
    # Sadece Admin ekstra menüyü görür
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("👥 Kullanıcıları Yönet (Admin)", callback_data="menu_admin")])
        
    return InlineKeyboardMarkup(keyboard)

def get_admin_menu():
    """Yönetici Menüsü butonlarını oluşturur."""
    keyboard = [
        [InlineKeyboardButton("➕ Kullanıcı Ekle", callback_data="admin_add_user")],
        [InlineKeyboardButton("➖ Kullanıcı Sil", callback_data="admin_del_user")],
        [InlineKeyboardButton("📋 Kullanıcı Listesi", callback_data="admin_list_users")],
        [InlineKeyboardButton("🔙 Ana Menüye Dön", callback_data="menu_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_cancel_menu():
    """İptal/Geri dön butonu."""
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ İşlemi İptal Et", callback_data="menu_main")]])

# ==========================================
# 🚀 BAŞLANGIÇ VE YÖNLENDİRİCİ
# ==========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Bot /start komutu ile ana menüyü açar."""
    user_id = update.effective_user.id
    wp_data = get_user_wp_data(user_id)

    if not wp_data and user_id != ADMIN_ID:
        await update.message.reply_text("⛔ Bu botu kullanma yetkiniz yok.")
        return ConversationHandler.END

    msg = "👋 Merhaba! Fotografikya İçerik Gönderme Botuna hoş geldin.\n\nLütfen bir işlem seçin:"
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(msg, reply_markup=get_main_menu(user_id))
    else:
        await update.message.reply_text(msg, reply_markup=get_main_menu(user_id))
        
    return MENU_ROUTING

async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Buton tıklamalarını ilgili durumlara yönlendirir."""
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    if data == "menu_main":
        await query.edit_message_text("🏠 Ana Menü:", reply_markup=get_main_menu(user_id))
        return MENU_ROUTING

    elif data == "menu_post":
        await query.edit_message_text("📸 Lütfen öne çıkan görsel yapmak istediğiniz fotoğrafı gönderin.", reply_markup=get_cancel_menu())
        return PHOTO

    # --- ADMIN YÖNLENDİRMELERİ ---
    elif user_id == ADMIN_ID:
        if data == "menu_admin":
            await query.edit_message_text("⚙️ Yönetici Paneli\nNe yapmak istersiniz?", reply_markup=get_admin_menu())
            return MENU_ROUTING
            
        elif data == "admin_list_users":
            db = load_db()
            text = "📋 **Kayıtlı Kullanıcılar:**\n\n"
            for t_id, info in db.items():
                role = "(👑 Admin)" if int(t_id) == ADMIN_ID else ""
                text += f"👤 TG ID: `{t_id}` {role}\n🌐 Site: {info['wp_url'].split('/wp-json')[0]}\n\n"
            await query.edit_message_text(text, reply_markup=get_admin_menu(), parse_mode='Markdown')
            return MENU_ROUTING
            
        elif data == "admin_add_user":
            await query.edit_message_text("➕ Kullanıcı Ekleme\nLütfen eklenecek kişinin Telegram User ID'sini gönderin:", reply_markup=get_cancel_menu())
            return ADD_TG_ID
            
        elif data == "admin_del_user":
            await query.edit_message_text("➖ Kullanıcı Silme\nLütfen silinecek kişinin Telegram User ID'sini gönderin:", reply_markup=get_cancel_menu())
            return DEL_TG_ID

    return MENU_ROUTING

# ==========================================
# ✍️ İÇERİK EKLEME AKIŞI (POST FLOW)
# ==========================================

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    photo_file = await update.message.photo[-1].get_file()
    file_path = f"temp_{update.effective_user.id}.jpg"
    await photo_file.download_to_drive(file_path)
    context.user_data['photo_path'] = file_path

    await update.message.reply_text("✅ Görsel alındı.\n📝 Lütfen şimdi yazının 'BAŞLIĞINI' gönderin:", reply_markup=get_cancel_menu())
    return TITLE

async def title_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['title'] = update.message.text.strip()
    await update.message.reply_text("✅ Başlık kaydedildi.\n✍️ Şimdi lütfen yazının 'İÇERİĞİNİ' gönderin:", reply_markup=get_cancel_menu())
    return CONTENT

async def content_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['content'] = update.message.text.strip()
    user_id = update.effective_user.id
    wp_data = get_user_wp_data(user_id)
    
    await update.message.reply_text("⏳ WordPress'ten kategoriler çekiliyor...")

    try:
        response = requests.get(f"{wp_data['wp_url']}/categories", auth=(wp_data['wp_user'], wp_data['wp_app_password']))
        response.raise_for_status()
        categories = response.json()
        
        keyboard = []
        for cat in categories:
            keyboard.append([InlineKeyboardButton(cat['name'], callback_data=f"cat_{cat['id']}")])
        keyboard.append([InlineKeyboardButton("❌ İptal", callback_data="menu_main")])
        
        await update.message.reply_text("📂 Lütfen bir kategori seçin:", reply_markup=InlineKeyboardMarkup(keyboard))
        return CATEGORY
    except Exception as e:
        logger.error(f"Kategori çekme hatası: {e}")
        await update.message.reply_text("❌ Kategoriler çekilemedi. Site adresi, kullanıcı adı veya şifreyi kontrol edin.", reply_markup=get_main_menu(user_id))
        return MENU_ROUTING

async def category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    wp_data = get_user_wp_data(user_id)
    
    # Callback verisinden kategori ID'yi al (örnek: "cat_15")
    category_id = int(query.data.split("_")[1])
    
    title = context.user_data.get('title')
    content = context.user_data.get('content')
    photo_path = context.user_data.get('photo_path')

    await query.edit_message_text("⏳ Seçim yapıldı! Yazı WordPress'e yükleniyor...")

    try:
        # 1. Görseli Yükle
        media_url = f"{wp_data['wp_url']}/media"
        headers = {'Content-Disposition': f'attachment; filename="bot_gorsel_{user_id}.jpg"', 'Content-Type': 'image/jpeg'}
        with open(photo_path, 'rb') as f:
            media_res = requests.post(media_url, headers=headers, auth=(wp_data['wp_user'], wp_data['wp_app_password']), data=f)
        media_res.raise_for_status()
        media_id = media_res.json().get('id')

        # 2. İçeriği Yayınla
        post_url = f"{wp_data['wp_url']}/posts"
        post_data = {
            'title': title,
            'content': content,
            'status': 'publish',
            'featured_media': media_id,
            'categories': [category_id]
        }
        post_res = requests.post(post_url, auth=(wp_data['wp_user'], wp_data['wp_app_password']), json=post_data)
        post_res.raise_for_status()
        post_link = post_res.json().get('link')

        await query.message.reply_text(f"✅ **Yazı başarıyla yayınlandı!**\n\n🔗 [Yazıyı Görüntüle]({post_link})", reply_markup=get_main_menu(user_id), parse_mode='Markdown', disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"Yükleme hatası: {e}")
        await query.message.reply_text("❌ Yükleme sırasında bir hata oluştu.", reply_markup=get_main_menu(user_id))
    finally:
        if photo_path and os.path.exists(photo_path):
            os.remove(photo_path)
            context.user_data.pop('photo_path', None)

    return MENU_ROUTING

# ==========================================
# 👥 ADMİN KULLANICI EKLEME AKIŞI
# ==========================================

async def admin_add_tg_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_user'] = {"tg_id": update.message.text.strip()}
    await update.message.reply_text("🌐 Şimdi yeni kullanıcının **WordPress Site Adresini** gönderin:\n*(Örn: https://site.com)*", reply_markup=get_cancel_menu())
    return ADD_WP_URL

async def admin_add_wp_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw_url = update.message.text.strip().rstrip('/')
    
    # URL YAZIM HATALARINI OTOMATİK DÜZELTME BÖLÜMÜ (3. YÖNTEM İÇİN EKLENDİ)
    if not raw_url.endswith("/wp-json/wp/v2"):
        if "/wp-json" in raw_url:
            # wp-json var ama v2 eksik veya yanlışsa temizleyip doğru ekle
            base_url = raw_url.split("/wp-json")[0]
            fixed_url = f"{base_url}/wp-json/wp/v2"
        else:
            # Sadece site adresi girildiyse (örn: https://site.com)
            fixed_url = f"{raw_url}/wp-json/wp/v2"
    else:
        fixed_url = raw_url
        
    context.user_data['new_user']['wp_url'] = fixed_url
    await update.message.reply_text(f"✅ URL otomatik algılandı: `{fixed_url}`\n\n👤 Şimdi WordPress **Kullanıcı Adını** gönderin:", parse_mode="Markdown", reply_markup=get_cancel_menu())
    return ADD_WP_USER

async def admin_add_wp_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_user']['wp_user'] = update.message.text.strip()
    await update.message.reply_text("🔑 Son olarak WordPress **Uygulama Şifresini** gönderin:", reply_markup=get_cancel_menu())
    return ADD_WP_PASS

async def admin_add_wp_pass(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    wp_pass = update.message.text.strip()
    new_user = context.user_data['new_user']
    
    db = load_db()
    db[new_user['tg_id']] = {
        "wp_url": new_user['wp_url'],
        "wp_user": new_user['wp_user'],
        "wp_app_password": wp_pass
    }
    save_db(db)
    
    context.user_data.pop('new_user', None)
    await update.message.reply_text(f"✅ Kullanıcı `{new_user['tg_id']}` sisteme başarıyla eklendi!", reply_markup=get_admin_menu(), parse_mode='Markdown')
    return MENU_ROUTING

# ==========================================
# 🗑️ ADMİN KULLANICI SİLME AKIŞI
# ==========================================

async def admin_del_tg_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    target_id = update.message.text.strip()
    
    if target_id == str(ADMIN_ID):
        await update.message.reply_text("⚠️ Kendinizi (Admin) silemezsiniz!", reply_markup=get_admin_menu())
        return MENU_ROUTING
        
    db = load_db()
    if target_id in db:
        del db[target_id]
        save_db(db)
        await update.message.reply_text(f"✅ `{target_id}` ID'li kullanıcı silindi.", reply_markup=get_admin_menu(), parse_mode='Markdown')
    else:
        await update.message.reply_text("❌ Böyle bir kullanıcı bulunamadı.", reply_markup=get_admin_menu())
        
    return MENU_ROUTING

# ==========================================
# 🛑 ANA FONKSİYON VE YAPI
# ==========================================

def main() -> None:
    # Veritabanını ilk kez kontrol et/oluştur
    load_db()

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Tek, kapsayıcı bir ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CallbackQueryHandler(start, pattern="^menu_main$")
        ],
        states={
            MENU_ROUTING: [CallbackQueryHandler(menu_router)],
            
            # İçerik Ekleme Adımları
            PHOTO: [MessageHandler(filters.PHOTO, photo_handler)],
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, title_handler)],
            CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, content_handler)],
            CATEGORY: [CallbackQueryHandler(category_callback, pattern="^cat_\d+$")],
            
            # Kullanıcı Ekleme Adımları
            ADD_TG_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_tg_id)],
            ADD_WP_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_wp_url)],
            ADD_WP_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_wp_user)],
            ADD_WP_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_wp_pass)],
            
            # Kullanıcı Silme Adımı
            DEL_TG_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_del_tg_id)],
        },
        fallbacks=[
            CommandHandler("start", start),
            CallbackQueryHandler(menu_router, pattern="^menu_main$") # İptal butonları için fallback
        ],
    )

    application.add_handler(conv_handler)
    
    print("✅ Bot başarıyla çalışıyor! Telegram'a gidip /start yazabilirsin...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
