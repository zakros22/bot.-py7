from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard(lang: str = 'ar'):
    if lang == 'ar':
        buttons = [
            [InlineKeyboardButton("📝 إنشاء اختبار جديد", callback_data="new_quiz")],
            [InlineKeyboardButton("📊 إحصائياتي", callback_data="my_stats"),
             InlineKeyboardButton("🎁 دعوة أصدقاء", callback_data="referral")],
            [InlineKeyboardButton("💳 شراء محاولات", callback_data="buy_attempts"),
             InlineKeyboardButton("ℹ️ المساعدة", callback_data="help")],
            [InlineKeyboardButton("🌐 English", callback_data="toggle_lang")],
        ]
    else:
        buttons = [
            [InlineKeyboardButton("📝 Create New Quiz", callback_data="new_quiz")],
            [InlineKeyboardButton("📊 My Stats", callback_data="my_stats"),
             InlineKeyboardButton("🎁 Invite Friends", callback_data="referral")],
            [InlineKeyboardButton("💳 Buy Attempts", callback_data="buy_attempts"),
             InlineKeyboardButton("ℹ️ Help", callback_data="help")],
            [InlineKeyboardButton("🌐 العربية", callback_data="toggle_lang")],
        ]
    return InlineKeyboardMarkup(buttons)


def difficulty_keyboard(lang: str = 'ar'):
    if lang == 'ar':
        buttons = [[
            InlineKeyboardButton("🟢 سهل", callback_data="diff_easy"),
            InlineKeyboardButton("🟡 متوسط", callback_data="diff_medium"),
            InlineKeyboardButton("🔴 صعب", callback_data="diff_hard"),
        ]]
    else:
        buttons = [[
            InlineKeyboardButton("🟢 Easy", callback_data="diff_easy"),
            InlineKeyboardButton("🟡 Medium", callback_data="diff_medium"),
            InlineKeyboardButton("🔴 Hard", callback_data="diff_hard"),
        ]]
    return InlineKeyboardMarkup(buttons)


def question_count_keyboard(lang: str = 'ar'):
    auto_label = "🔄 تلقائي" if lang == 'ar' else "🔄 Auto"
    buttons = [
        [InlineKeyboardButton("5", callback_data="qcount_5"),
         InlineKeyboardButton("10", callback_data="qcount_10"),
         InlineKeyboardButton("20", callback_data="qcount_20")],
        [InlineKeyboardButton("30", callback_data="qcount_30"),
         InlineKeyboardButton("50", callback_data="qcount_50"),
         InlineKeyboardButton("100", callback_data="qcount_100")],
        [InlineKeyboardButton(auto_label, callback_data="qcount_auto")],
    ]
    return InlineKeyboardMarkup(buttons)


def question_type_keyboard(lang: str = 'ar', selected: list = None):
    if selected is None:
        selected = ['multiple_choice', 'true_false', 'fill_blank', 'qa']

    def _icon(t):
        return "✅" if t in selected else "⬜"

    if lang == 'ar':
        buttons = [
            [
                InlineKeyboardButton(f"{_icon('multiple_choice')} اختيار متعدد", callback_data="qtype_mc"),
                InlineKeyboardButton(f"{_icon('true_false')} صح / خطأ", callback_data="qtype_tf"),
            ],
            [
                InlineKeyboardButton(f"{_icon('fill_blank')} ملء الفراغات", callback_data="qtype_fb"),
                InlineKeyboardButton(f"{_icon('qa')} سؤال وجواب", callback_data="qtype_qa"),
            ],
            [InlineKeyboardButton("🚀 توليد الأسئلة الآن", callback_data="do_generate")],
            [InlineKeyboardButton("🏠 الرئيسية", callback_data="back_main")],
        ]
    else:
        buttons = [
            [
                InlineKeyboardButton(f"{_icon('multiple_choice')} Multiple Choice", callback_data="qtype_mc"),
                InlineKeyboardButton(f"{_icon('true_false')} True / False", callback_data="qtype_tf"),
            ],
            [
                InlineKeyboardButton(f"{_icon('fill_blank')} Fill in Blank", callback_data="qtype_fb"),
                InlineKeyboardButton(f"{_icon('qa')} Q & A", callback_data="qtype_qa"),
            ],
            [InlineKeyboardButton("🚀 Generate Questions Now", callback_data="do_generate")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")],
        ]
    return InlineKeyboardMarkup(buttons)


def quiz_start_keyboard(quiz_id: int, lang: str = 'ar'):
    if lang == 'ar':
        buttons = [
            [InlineKeyboardButton("🚀 ابدأ الاختبار الآن!", callback_data=f"start_quiz_{quiz_id}")],
            [InlineKeyboardButton("📤 تصدير الأسئلة PDF", callback_data=f"export_quiz_{quiz_id}")],
        ]
    else:
        buttons = [
            [InlineKeyboardButton("🚀 Start Quiz Now!", callback_data=f"start_quiz_{quiz_id}")],
            [InlineKeyboardButton("📤 Export Questions PDF", callback_data=f"export_quiz_{quiz_id}")],
        ]
    return InlineKeyboardMarkup(buttons)


def mc_answer_keyboard(options: list, q_idx: int):
    buttons = []
    for opt in options:
        if not opt:
            continue
        letter = opt[0] if opt else 'A'
        buttons.append([InlineKeyboardButton(opt, callback_data=f"ans_{q_idx}_{letter}")])
    return InlineKeyboardMarkup(buttons)


def tf_answer_keyboard(q_idx: int, lang: str = 'ar'):
    if lang == 'ar':
        buttons = [[
            InlineKeyboardButton("✅ صحيح", callback_data=f"ans_{q_idx}_True"),
            InlineKeyboardButton("❌ خطأ", callback_data=f"ans_{q_idx}_False"),
        ]]
    else:
        buttons = [[
            InlineKeyboardButton("✅ True", callback_data=f"ans_{q_idx}_True"),
            InlineKeyboardButton("❌ False", callback_data=f"ans_{q_idx}_False"),
        ]]
    return InlineKeyboardMarkup(buttons)


def payment_keyboard(lang: str = 'ar'):
    if lang == 'ar':
        buttons = [
            [InlineKeyboardButton("⭐ دفع بنجوم تيليجرام", callback_data="pay_stars")],
            [InlineKeyboardButton("💳 تواصل مع المالك", url="https://t.me/zakros22bot")],
            [InlineKeyboardButton("🏠 الرئيسية", callback_data="back_main")],
        ]
    else:
        buttons = [
            [InlineKeyboardButton("⭐ Pay with Telegram Stars", callback_data="pay_stars")],
            [InlineKeyboardButton("💳 Contact Owner", url="https://t.me/zakros22bot")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")],
        ]
    return InlineKeyboardMarkup(buttons)


def admin_keyboard():
    buttons = [
        [InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 المستخدمون", callback_data="admin_users"),
         InlineKeyboardButton("➕ إضافة محاولات", callback_data="admin_add_attempts")],
        [InlineKeyboardButton("⚙️ تعيين محاولات", callback_data="admin_set_attempts"),
         InlineKeyboardButton("⭐ إدارة النقاط", callback_data="admin_manage_points")],
        [InlineKeyboardButton("🚫 حظر مستخدم", callback_data="admin_ban"),
         InlineKeyboardButton("📢 رسالة جماعية", callback_data="admin_broadcast")],
    ]
    return InlineKeyboardMarkup(buttons)


def back_keyboard(lang: str = 'ar'):
    label = "🏠 الرئيسية" if lang == 'ar' else "🏠 Main Menu"
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data="back_main")]])
