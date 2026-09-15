from aiogram import Router, types, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime
from zoneinfo import ZoneInfo

from database import (
    get_user, get_starosta, update_user_field,
    get_notify_pairs, set_notify_pairs,
    get_notify_attendance, set_notify_attendance,
    get_user_subgroup, set_user_subgroup,
)
from keyboards import get_profile_edit_kb, get_subgroup_choice_kb

router = Router()


class ProfileEdit(StatesGroup):
    waiting_value = State()


# ============ ПОКАЗ ПРОФИЛЯ ============

@router.message(F.text == "👤 Профиль")
async def show_profile(message: types.Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return

    user_id = user[0]
    university = user[1]
    faculty = user[2]
    group_name = user[3]
    full_name = user[4]
    role = user[5]

    # Подгруппа (только для РГУ)
    subgroup = user[11] if len(user) > 11 else 0

    starosta = get_starosta(university, faculty, group_name)
    if starosta:
        starosta_info = f"{starosta[1]} (ID: `{starosta[0]}`)"
    else:
        starosta_info = "не назначен"

    role_text = "👑 Староста" if role == "starosta" else "🎓 Студент"

    notify_pairs = get_notify_pairs(user_id)
    notify_attendance = get_notify_attendance(user_id)

    pairs_icon = "🔔" if notify_pairs else "🔕"
    att_icon = "📋" if notify_attendance else "📋"

    now = datetime.now(ZoneInfo("Europe/Moscow"))
    date_str = now.strftime("%d.%m.%Y")
    weekday_str = [
        "Понедельник", "Вторник", "Среда",
        "Четверг", "Пятница", "Суббота", "Воскресенье"
    ][now.weekday()]
    time_str = now.strftime("%H:%M")

    pairs_status = "включены" if notify_pairs else "выключены"
    att_status = "включены" if notify_attendance else "выключены"

    # Строка про подгруппу — только для РГУ
    subgroup_line = ""
    if university == "РГУ":
        sg_label = "не выбрана"
        if subgroup == 1:
            sg_label = "1"
        elif subgroup == 2:
            sg_label = "2"
        subgroup_line = f"**Подгруппа:** {sg_label}\n"

    text = (
        f"👤 **Мой профиль**\n\n"
        f"📅 Сегодня: **{date_str}** ({weekday_str})\n"
        f"🕐 Время: **{time_str}**\n\n"
        f"**ФИО:** {full_name}\n"
        f"**ВУЗ:** {university}\n"
        f"**Факультет:** {faculty}\n"
        f"**Группа:** {group_name}\n"
        f"{subgroup_line}"
        f"**Роль:** {role_text}\n"
        f"**Староста группы:** {starosta_info}\n\n"
        f"**Уведомления:**\n"
        f"{pairs_icon} Пары (за 30 мин): **{pairs_status}**\n"
        f"{att_icon} Явка (в 14:00): **{att_status}**\n"
    )

    await message.answer(
        text,
        parse_mode="Markdown",
        reply_markup=get_profile_edit_kb(
            notify_pairs=notify_pairs,
            notify_attendance=notify_attendance,
            university=university,
            subgroup=subgroup,
        )
    )


# ============ РЕДАКТИРОВАНИЕ ============

@router.callback_query(F.data == "edit_university")
async def edit_university(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введи новое название ВУЗа:")
    await state.set_state(ProfileEdit.waiting_value)
    await state.update_data(field="university", label="ВУЗ")
    await callback.answer()


@router.callback_query(F.data == "edit_faculty")
async def edit_faculty(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введи новый факультет:")
    await state.set_state(ProfileEdit.waiting_value)
    await state.update_data(field="faculty", label="Факультет")
    await callback.answer()


@router.callback_query(F.data == "edit_group_name")
async def edit_group(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введи новый номер группы:")
    await state.set_state(ProfileEdit.waiting_value)
    await state.update_data(field="group_name", label="Группа")
    await callback.answer()


@router.callback_query(F.data == "edit_full_name")
async def edit_full_name(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введи новое ФИО:")
    await state.set_state(ProfileEdit.waiting_value)
    await state.update_data(field="full_name", label="ФИО")
    await callback.answer()


@router.callback_query(F.data == "edit_close")
async def edit_close(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Закрыто")


# ============ ПРИЁМ НОВОГО ЗНАЧЕНИЯ ============

@router.message(ProfileEdit.waiting_value)
async def process_new_value(message: types.Message, state: FSMContext):
    data = await state.get_data()
    field = data.get("field")
    label = data.get("label", "Поле")

    new_value = message.text.strip()

    if not new_value:
        await message.answer("❌ Значение не может быть пустым. Попробуй ещё раз.")
        return

    if len(new_value) > 200:
        await message.answer("❌ Слишком длинное значение. Максимум 200 символов.")
        return

    try:
        update_user_field(message.from_user.id, field, new_value)
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
        await state.clear()
        return

    await state.clear()

    await message.answer(
        f"✅ {label} обновлён: **{new_value}**\n\n"
        f"Посмотреть профиль — кнопка «👤 Мой профиль».",
        parse_mode="Markdown"
    )


# ============ ПЕРЕКЛЮЧАТЕЛИ УВЕДОМЛЕНИЙ ============

@router.callback_query(F.data == "toggle_notify_pairs")
async def toggle_notify_pairs(callback: CallbackQuery):
    user_id = callback.from_user.id

    current = get_notify_pairs(user_id)
    new_state = not current

    set_notify_pairs(user_id, new_state)

    user = get_user(user_id)
    university = user[1] if user else None
    subgroup = user[11] if user and len(user) > 11 else 0
    notify_attendance = get_notify_attendance(user_id)

    await callback.message.edit_reply_markup(
        reply_markup=get_profile_edit_kb(
            notify_pairs=new_state,
            notify_attendance=notify_attendance,
            university=university,
            subgroup=subgroup,
        )
    )

    status = "включены 🔔" if new_state else "отключены 🔕"
    await callback.answer(f"Напоминания о парах {status}", show_alert=False)


@router.callback_query(F.data == "toggle_notify_attendance")
async def toggle_notify_attendance(callback: CallbackQuery):
    user_id = callback.from_user.id

    current = get_notify_attendance(user_id)
    new_state = not current

    set_notify_attendance(user_id, new_state)

    user = get_user(user_id)
    university = user[1] if user else None
    subgroup = user[11] if user and len(user) > 11 else 0
    notify_pairs = get_notify_pairs(user_id)

    await callback.message.edit_reply_markup(
        reply_markup=get_profile_edit_kb(
            notify_pairs=notify_pairs,
            notify_attendance=new_state,
            university=university,
            subgroup=subgroup,
        )
    )

    status = "включены 📋" if new_state else "отключены 📋"
    await callback.answer(f"Уведомления о явке {status}", show_alert=False)


# ============ ПОДГРУППА (РГУ) ============

@router.callback_query(F.data == "edit_subgroup")
async def edit_subgroup(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала зарегистрируйтесь: /start", show_alert=True)
        return

    if user[1] != "РГУ":
        await callback.answer("⛔ Подгруппа доступна только для РГУ.", show_alert=True)
        return

    current = user[11] if len(user) > 11 else 0

    await callback.message.edit_text(
        "👥 **Выбери свою подгруппу**\n\n"
        "Это влияет на:\n"
        "• Какие пары ты видишь в расписании\n"
        "• Какие пары приходят в рассылке «Отметь явку»\n"
        "• О каких парах напоминать за 30 минут\n\n"
        "**Для всех** — общие пары, они идут в расписание всем подгруппам.",
        parse_mode="Markdown",
        reply_markup=get_subgroup_choice_kb(current)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_subgroup_"))
async def set_subgroup_callback(callback: CallbackQuery):
    try:
        subgroup = int(callback.data.replace("set_subgroup_", ""))
    except ValueError:
        await callback.answer("Ошибка", show_alert=True)
        return

    if subgroup not in (0, 1, 2):
        await callback.answer("Ошибка", show_alert=True)
        return

    user = get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала зарегистрируйтесь: /start", show_alert=True)
        return

    if user[1] != "РГУ":
        await callback.answer("⛔ Только РГУ.", show_alert=True)
        return

    set_user_subgroup(callback.from_user.id, subgroup)

    await callback.message.edit_reply_markup(
        reply_markup=get_subgroup_choice_kb(subgroup)
    )

    label = "не выбрана" if subgroup == 0 else str(subgroup)
    await callback.answer(f"Подгруппа: {label}", show_alert=False)


@router.callback_query(F.data == "subgroup_close")
async def subgroup_close(callback: CallbackQuery):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Закрыто")