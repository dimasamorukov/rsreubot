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
)
from keyboards import get_profile_edit_kb

router = Router()


class ProfileEdit(StatesGroup):
    waiting_value = State()

# ============ ПОКАЗ ПРОФИЛЯ ============

from database import (
    get_user, get_starosta, update_user_field,
    get_notify_pairs, set_notify_pairs,
    get_notify_attendance, set_notify_attendance,
)


@router.message(F.text == "👤 Профиль")
async def show_profile(message: types.Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return

    # user = (user_id, university, faculty, group_name, full_name, role,
    #         registered_at, notifications_enabled, notify_pairs, notify_attendance)
    user_id = user[0]
    university = user[1]
    faculty = user[2]
    group_name = user[3]
    full_name = user[4]
    role = user[5]
    registered_at = user[6]

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

    text = (
        f"👤 **Мой профиль**\n\n"
        f"📅 Сегодня: **{date_str}** ({weekday_str})\n"
        f"🕐 Время: **{time_str}**\n\n"
        f"**ФИО:** {full_name}\n"
        f"**ВУЗ:** {university}\n"
        f"**Факультет:** {faculty}\n"
        f"**Группа:** {group_name}\n"
        f"**Роль:** {role_text}\n"
        f"**Староста группы:** {starosta_info}\n\n"
        f"**Уведомления:**\n"
        f"{pairs_icon} Пары (за 30 мин): **{pairs_status}**\n"
        f"{att_icon} Явка (в 14:00): **{att_status}**\n"
    )

    await message.answer(
        text,
        parse_mode="Markdown",
        reply_markup=get_profile_edit_kb(notify_pairs, notify_attendance)
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

@router.callback_query(F.data == "toggle_notify_pairs")
async def toggle_notify_pairs(callback: CallbackQuery):
    """Переключает напоминания о парах (за 30 минут)."""
    user_id = callback.from_user.id

    current = get_notify_pairs(user_id)
    new_state = not current

    set_notify_pairs(user_id, new_state)

    # Пересобираем клавиатуру
    notify_attendance = get_notify_attendance(user_id)
    await callback.message.edit_reply_markup(
        reply_markup=get_profile_edit_kb(new_state, notify_attendance)
    )

    status = "включены 🔔" if new_state else "отключены 🔕"
    await callback.answer(f"Напоминания о парах {status}", show_alert=False)


@router.callback_query(F.data == "toggle_notify_attendance")
async def toggle_notify_attendance(callback: CallbackQuery):
    """Переключает уведомления о явке (рассылка в 14:00)."""
    user_id = callback.from_user.id

    current = get_notify_attendance(user_id)
    new_state = not current

    set_notify_attendance(user_id, new_state)

    # Пересобираем клавиатуру
    notify_pairs = get_notify_pairs(user_id)
    await callback.message.edit_reply_markup(
        reply_markup=get_profile_edit_kb(notify_pairs, new_state)
    )

    status = "включены 📋" if new_state else "отключены 📋"
    await callback.answer(f"Уведомления о явке {status}", show_alert=False)
