from aiogram import Router, types, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime
from zoneinfo import ZoneInfo

from database import (
    get_user, get_starosta, update_user_field,
    get_notifications_enabled, set_notifications_enabled
)
from keyboards import get_profile_edit_kb

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
    
    user_id, university, faculty, group_name, full_name, role, registered_at, notifications_enabled = user
    
    starosta = get_starosta(university, faculty, group_name)
    if starosta:
        starosta_info = f"{starosta[1]} (ID: `{starosta[0]}`)"
    else:
        starosta_info = "не назначен"
    
    role_text = "👑 Староста" if role == "starosta" else "🎓 Студент"
    
    notif_text = "🔔 Включены" if notifications_enabled else "🔕 Отключены"
    
    now = datetime.now(ZoneInfo("Europe/Moscow"))
    date_str = now.strftime("%d.%m.%Y")
    weekday_str = [
        "Понедельник", "Вторник", "Среда",
        "Четверг", "Пятница", "Суббота", "Воскресенье"
    ][now.weekday()]
    time_str = now.strftime("%H:%M")
    
    text = (
        f"👤 **Мой профиль**\n\n"
        f"📅 Сегодня: **{date_str}** ({weekday_str})\n"
        f"🕐 Время: **{time_str}**\n\n"
        f"**ФИО:** {full_name}\n"
        f"**ВУЗ:** {university}\n"
        f"**Факультет:** {faculty}\n"
        f"**Группа:** {group_name}\n"
        f"**Роль:** {role_text}\n"
        f"**Староста группы:** {starosta_info}\n"
        f"**Уведомления:** {notif_text}\n"
    )
    
    await message.answer(
        text,
        parse_mode="Markdown",
        reply_markup=get_profile_edit_kb(notifications_enabled)
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

@router.callback_query(F.data == "toggle_notifications")
async def toggle_notifications(callback: CallbackQuery):
    """Переключает уведомления ВКЛ/ВЫКЛ"""
    user_id = callback.from_user.id

    current = get_notifications_enabled(user_id)
    new_state = not current

    set_notifications_enabled(user_id, new_state)

    await callback.message.edit_reply_markup(
        reply_markup=get_profile_edit_kb(new_state)
    )

    status = "включены 🔔" if new_state else "отключены 🔕"
    await callback.answer(f"Уведомления {status}", show_alert=False)
