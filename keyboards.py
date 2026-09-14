from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)


def get_universities_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="РГРТУ")],
            [KeyboardButton(text="РГУ")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )


def get_faculties_kb(university: str = "РГРТУ"):
    from config import FACULTIES_RGRTU, FACULTIES_RGU

    if university == "РГУ":
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="ФЭСУ"), KeyboardButton(text="ИФМиКН")],
                [KeyboardButton(text="ИЕН"), KeyboardButton(text="ИИЯ")],
                [KeyboardButton(text="ФФКС"), KeyboardButton(text="ИИФПН")],
                [KeyboardButton(text="ФРФНК"), KeyboardButton(text="ИППСР")],
                [KeyboardButton(text="ЮИ")],
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
    else:
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="ФРТ"), KeyboardButton(text="ФВТ")],
                [KeyboardButton(text="ФАИТУ"), KeyboardButton(text="ИЭФ")],
                [KeyboardButton(text="ФЭ")],
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )


def get_schedule_menu_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📅 Сегодня"), KeyboardButton(text="📅 Завтра")],
            [KeyboardButton(text="📅 2 недели")],
            [KeyboardButton(text="🔙 Назад")],
        ],
        resize_keyboard=True
    )


def get_attendance_menu_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Сегодня"), KeyboardButton(text="✅ Завтра")],
            [KeyboardButton(text="🔙 Назад")],
        ],
        resize_keyboard=True
    )


def get_main_menu(is_admin=False, university=None):
    """
    Главное меню.
    is_admin — показывать ли кнопки старосты
    university — если "РГРТУ", добавляем кнопку «🔄 Обновить расписание»
    """
    buttons = [
        [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="📚 ДЗ")],
        [KeyboardButton(text="📅 Расписание"), KeyboardButton(text="✅ Посещение")],
    ]

    # Кнопка обновления расписания — ТОЛЬКО для РГРТУ
    if university == "РГРТУ":
        buttons.append([KeyboardButton(text="🔄 Обновить расписание")])

    buttons.append([KeyboardButton(text="📝 Задолженности"), KeyboardButton(text="ℹ️ Помощь")])

    if is_admin:
        buttons.append([KeyboardButton(text="👑 Панель старосты"), KeyboardButton(text="📊 Посещаемость")])

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def get_homework_actions_kb(homework_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="✅ Сделал", callback_data=f"hw_done_{homework_id}"),
            InlineKeyboardButton(text="❌ Не сделал", callback_data=f"hw_not_done_{homework_id}"),
        ]]
    )


def get_homework_starosta_kb(homework_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Сделал", callback_data=f"hw_done_{homework_id}"),
                InlineKeyboardButton(text="❌ Не сделал", callback_data=f"hw_not_done_{homework_id}"),
            ],
            [
                InlineKeyboardButton(text="🗑 Удалить ДЗ", callback_data=f"hw_delete_{homework_id}"),
            ]
        ]
    )


def get_homework_confirm_delete_kb(homework_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"hw_delete_yes_{homework_id}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"hw_delete_no_{homework_id}"),
        ]]
    )


def get_profile_edit_kb(notify_pairs: bool = True, notify_attendance: bool = True):
    pairs_text = "🔔 Пары: ВКЛ" if notify_pairs else "🔕 Пары: ВЫКЛ"
    attendance_text = "📋 Явка: ВКЛ" if notify_attendance else "📋 Явка: ВЫКЛ"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ ВУЗ", callback_data="edit_university"),
                InlineKeyboardButton(text="✏️ Факультет", callback_data="edit_faculty"),
            ],
            [
                InlineKeyboardButton(text="✏️ Группа", callback_data="edit_group_name"),
                InlineKeyboardButton(text="✏️ ФИО", callback_data="edit_full_name"),
            ],
            [InlineKeyboardButton(text=pairs_text, callback_data="toggle_notify_pairs")],
            [InlineKeyboardButton(text=attendance_text, callback_data="toggle_notify_attendance")],
            [InlineKeyboardButton(text="🔙 Закрыть", callback_data="edit_close")],
        ]
    )


def get_admin_panel_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ ДЗ"), KeyboardButton(text="➕ Пара")],
            [KeyboardButton(text="👥 Список группы"), KeyboardButton(text="📊 Посещаемость")],
            [KeyboardButton(text="📜 Логи посещаемости")],
            [KeyboardButton(text="🔙 Назад")],
        ],
        resize_keyboard=True
    )


def get_days_kb(prefix="day"):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Пн", callback_data=f"{prefix}_Понедельник"),
                InlineKeyboardButton(text="Вт", callback_data=f"{prefix}_Вторник"),
                InlineKeyboardButton(text="Ср", callback_data=f"{prefix}_Среда"),
            ],
            [
                InlineKeyboardButton(text="Чт", callback_data=f"{prefix}_Четверг"),
                InlineKeyboardButton(text="Пт", callback_data=f"{prefix}_Пятница"),
                InlineKeyboardButton(text="Сб", callback_data=f"{prefix}_Суббота"),
            ],
        ]
    )


def get_confirm_kb(prefix):
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="✅ Да", callback_data=f"{prefix}_yes"),
            InlineKeyboardButton(text="❌ Нет", callback_data=f"{prefix}_no"),
        ]]
    )


def get_debts_menu_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить", callback_data="debt_add")],
            [InlineKeyboardButton(text="🗑 Удалить", callback_data="debt_delete_menu")],
            [InlineKeyboardButton(text="🔙 Закрыть", callback_data="debt_close")],
        ]
    )


def get_debts_delete_kb(debts):
    rows = []
    for debt_id, subject, task in debts:
        short = f"{subject} — {task}" if task else subject
        if len(short) > 40:
            short = short[:37] + "..."
        rows.append([InlineKeyboardButton(text=f"❌ {short}", callback_data=f"debt_del_{debt_id}")])
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="debt_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_group_members_delete_kb(members):
    rows = []
    for user_id, full_name, role in members:
        if role == 'starosta':
            continue
        short = full_name if len(full_name) <= 35 else full_name[:32] + "..."
        rows.append([InlineKeyboardButton(text=f"❌ {short}", callback_data=f"del_member_{user_id}")])
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="del_member_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_group_list_actions_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Удалить студентов", callback_data="group_list_delete_menu")],
        ]
    )


def get_users_pagination_kb(page: int, total_pages: int):
    rows = []
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"users_page_{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"users_page_{page + 1}"))
    if nav_row:
        rows.append(nav_row)
    rows.append([InlineKeyboardButton(text="🔙 Закрыть", callback_data="users_close")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_user_info_kb(user_id: int, is_starosta: bool = False):
    rows = []

    if is_starosta:
        rows.append([
            InlineKeyboardButton(
                text="👑 Снять роль старосты",
                callback_data=f"user_remove_starosta_{user_id}"
            )
        ])

    rows.append([
        InlineKeyboardButton(
            text="🗑 Удалить пользователя",
            callback_data=f"user_delete_{user_id}"
        )
    ])
    rows.append([InlineKeyboardButton(text="🔙 Закрыть", callback_data="user_close")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_user_delete_confirm_kb(user_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"user_delete_yes_{user_id}"),
                InlineKeyboardButton(text="❌ Отмена", callback_data=f"user_delete_no_{user_id}"),
            ]
        ]
    )


def get_broadcast_confirm_kb(scope: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Отправить", callback_data=f"broadcast_yes_{scope}"),
                InlineKeyboardButton(text="❌ Отмена", callback_data=f"broadcast_no_{scope}"),
            ]
        ]
    )


def get_remove_starosta_confirm_kb(user_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, снять",
                    callback_data=f"user_remove_starosta_yes_{user_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data=f"user_remove_starosta_no_{user_id}"
                ),
            ]
        ]
    )


def get_attendance_kb(schedule_id, date_offset=0):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Буду", callback_data=f"att_will_{schedule_id}_{date_offset}_0"),
                InlineKeyboardButton(text="❌ Не приду", callback_data=f"att_absent_{schedule_id}_{date_offset}_0"),
            ],
            [
                InlineKeyboardButton(text="🤒 Заболел", callback_data=f"att_sick_{schedule_id}_{date_offset}_0"),
                InlineKeyboardButton(text="⏰ Задержусь", callback_data=f"att_late_{schedule_id}_{date_offset}_0"),
            ]
        ]
    )


def get_tomorrow_attendance_all_kb(pairs: list, user_answers: dict = None):
    user_answers = user_answers or {}
    rows = []
    for pair in pairs:
        schedule_id = pair[0]
        pair_num = pair[1]
        subject = pair[2]
        current = user_answers.get(schedule_id)

        short_subj = subject if len(subject) <= 20 else subject[:17] + "..."

        will_text   = "✅ Буду"      if current == "will"   else "Буду"
        absent_text = "❌ Не приду"  if current == "absent" else "Не приду"
        sick_text   = "🤒 Заболел"   if current == "sick"   else "Заболел"
        late_text   = "⏰ Задержусь" if current == "late"   else "Задержусь"

        rows.append([
            InlineKeyboardButton(
                text=f"{pair_num} пара · {short_subj}",
                callback_data="att_noop"
            ),
        ])
        rows.append([
            InlineKeyboardButton(text=will_text,   callback_data=f"att_will_{schedule_id}_1_1"),
            InlineKeyboardButton(text=absent_text, callback_data=f"att_absent_{schedule_id}_1_1"),
        ])
        rows.append([
            InlineKeyboardButton(text=sick_text,   callback_data=f"att_sick_{schedule_id}_1_1"),
            InlineKeyboardButton(text=late_text,   callback_data=f"att_late_{schedule_id}_1_1"),
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============ МАСТЕР ДОБАВЛЕНИЯ ПАРЫ v2 ============

def get_week_type_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔵 Числитель", callback_data="pw_num")],
            [InlineKeyboardButton(text="🟢 Знаменатель", callback_data="pw_den")],
            [InlineKeyboardButton(text="⚪ Каждую неделю", callback_data="pw_any")],
        ]
    )


def get_days_kb_full():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Пн", callback_data="pd_Понедельник"),
                InlineKeyboardButton(text="Вт", callback_data="pd_Вторник"),
                InlineKeyboardButton(text="Ср", callback_data="pd_Среда"),
            ],
            [
                InlineKeyboardButton(text="Чт", callback_data="pd_Четверг"),
                InlineKeyboardButton(text="Пт", callback_data="pd_Пятница"),
                InlineKeyboardButton(text="Сб", callback_data="pd_Суббота"),
            ],
        ]
    )


def get_lesson_type_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📖 Лекция", callback_data="lt_Лекция"),
                InlineKeyboardButton(text="🔬 Лабораторная", callback_data="lt_Лабораторная"),
            ],
            [
                InlineKeyboardButton(text="✏️ Практика", callback_data="lt_Практика"),
                InlineKeyboardButton(text="💬 Семинар", callback_data="lt_Семинар"),
            ],
            [
                InlineKeyboardButton(text="📝 Курсовая", callback_data="lt_Курсовая"),
            ],
        ]
    )


def get_subgroup_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="1 подгруппа", callback_data="sg_1"),
                InlineKeyboardButton(text="2 подгруппа", callback_data="sg_2"),
            ],
            [
                InlineKeyboardButton(text="Для всех (-)", callback_data="sg_0"),
            ],
        ]
    )


def get_period_end_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="До конца семестра (31.12)", callback_data="pe_semester")],
            [InlineKeyboardButton(text="До конца месяца", callback_data="pe_month")],
            [InlineKeyboardButton(text="Ввести дату вручную", callback_data="pe_manual")],
        ]
    )