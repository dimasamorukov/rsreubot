import asyncio
from aiogram import Router, types, F, Bot
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
    add_starosta_application,
    has_pending_application,
    get_user_xp,
    get_referral_count,
    use_promo_code,
)
from keyboards import (
    get_profile_edit_kb,
    get_subgroup_choice_kb,
    get_delete_profile_confirm_kb,
    get_promo_menu_kb,
    get_promo_cancel_kb,
)
from config import ADMIN_IDS, XP_PER_LEVEL

router = Router()


class ProfileEdit(StatesGroup):
    waiting_value = State()          # редактирование профиля
    waiting_application = State()    # подача заявки на старосту
    waiting_promo = State()          # ввод промокода


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

    # XP / уровень
    xp, level, streak = get_user_xp(user_id)
    xp_in_level = int(xp % XP_PER_LEVEL)
    progress = "▰" * xp_in_level + "▱" * (XP_PER_LEVEL - xp_in_level)

    # рефералы
    ref_count = get_referral_count(user_id)

    # pending заявка
    pending_id = has_pending_application(user_id)

    now = datetime.now(ZoneInfo("Europe/Moscow"))
    date_str = now.strftime("%d.%m.%Y")
    weekday_str = [
        "Понедельник", "Вторник", "Среда",
        "Четверг", "Пятница", "Суббота", "Воскресенье"
    ][now.weekday()]
    time_str = now.strftime("%H:%M")

    pairs_status = "включены" if notify_pairs else "выключены"
    att_status = "включены" if notify_attendance else "выключены"

    subgroup_line = ""
    if university == "РГУ":
        sg_label = "не выбрана"
        if subgroup == 1:
            sg_label = "1"
        elif subgroup == 2:
            sg_label = "2"
        subgroup_line = f"**Подгруппа:** {sg_label}\n"

    pending_line = ""
    if pending_id:
        pending_line = f"\n⏳ **Заявка на старосту #{pending_id}** на рассмотрении\n"

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
        f"**Староста группы:** {starosta_info}\n"
        f"{pending_line}\n"
        f"🎖 **Уровень {level}** | XP: **{int(xp)}**\n"
        f"{progress} {xp_in_level}/{XP_PER_LEVEL}\n"
        f"🔥 Streak: **{streak}**\n"
        f"👥 Приглашено друзей: **{ref_count}**\n\n"
        f"**Уведомления:**\n"
        f"{pairs_icon} Пары (за 10 мин): **{pairs_status}**\n"
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
            role=role,
            has_pending_app=bool(pending_id),
        )
    )


# ============ РЕДАКТИРОВАНИЕ ПРОФИЛЯ ============

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


# ============ ПРИЁМ НОВОГО ЗНАЧЕНИЯ ПРОФИЛЯ ============

@router.message(ProfileEdit.waiting_value, F.text)
async def universal_waiting_text(message: types.Message, state: FSMContext):
    data = await state.get_data()

    field = data.get("field")
    label = data.get("label", "Поле")
    new_value = message.text.strip()

    if not new_value:
        await message.answer("❌ Значение не может быть пустым.")
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
        f"✅ {label} обновлён: <b>{new_value}</b>\n\n"
        f"Посмотреть профиль — «👤 Профиль».",
        parse_mode="HTML"
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
    role = user[5] if user else "student"
    notify_attendance = get_notify_attendance(user_id)
    pending_id = has_pending_application(user_id)

    await callback.message.edit_reply_markup(
        reply_markup=get_profile_edit_kb(
            notify_pairs=new_state,
            notify_attendance=notify_attendance,
            university=university,
            subgroup=subgroup,
            role=role,
            has_pending_app=bool(pending_id),
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
    role = user[5] if user else "student"
    notify_pairs = get_notify_pairs(user_id)
    pending_id = has_pending_application(user_id)

    await callback.message.edit_reply_markup(
        reply_markup=get_profile_edit_kb(
            notify_pairs=notify_pairs,
            notify_attendance=new_state,
            university=university,
            subgroup=subgroup,
            role=role,
            has_pending_app=bool(pending_id),
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
        "• О каких парах напоминать за 10 минут\n\n"
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


# ============ ПРОМОКОДЫ ============

@router.callback_query(F.data == "promo_menu")
async def promo_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    ref_count = get_referral_count(user_id)
    bot_username = (await callback.bot.me()).username
    invite_link = f"https://t.me/{bot_username}?start=ref_{user_id}"

    text = (
        f"🎁 <b>Промокоды и рефералы</b>\n\n"
        f"👥 Приглашено друзей: <b>{ref_count}</b>\n\n"
        f"🔗 Твоя ссылка:\n<code>{invite_link}</code>\n\n"
        f"За каждого друга — <b>+3 XP</b>!"
    )

    await callback.message.answer(
        text,
        parse_mode="HTML",
        reply_markup=get_promo_menu_kb()
    )
    await callback.answer()


@router.callback_query(F.data == "promo_enter")
async def promo_enter(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "🎁 <b>Введи промокод:</b>\n\n"
        "<i>Отмена — /cancel</i>",
        parse_mode="HTML",
        reply_markup=get_promo_cancel_kb()
    )
    await state.set_state(ProfileEdit.waiting_promo)
    await callback.answer()


@router.message(ProfileEdit.waiting_promo, F.text)
async def promo_process(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()

    status, reward = use_promo_code(message.from_user.id, code)

    if status == "not_found":
        await message.answer("❌ Такого промокода не существует.")
    elif status == "expired":
        await message.answer("❌ Промокод больше не действует.")
    elif status == "already_used":
        await message.answer("⚠️ Ты уже активировал этот промокод.")
    elif status == "ok":
        await message.answer(
            f"✅ Промокод активирован!\n"
            f"🎁 Получено: <b>+{reward} XP</b>",
            parse_mode="HTML"
        )

    await state.clear()


@router.callback_query(F.data == "promo_close")
async def promo_close(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Закрыто")


# ============ ПОДАЧА ЗАЯВКИ НА СТАРОСТУ ============

@router.callback_query(F.data == "starosta_apply_pending")
async def starosta_apply_pending(callback: CallbackQuery):
    user_id = callback.from_user.id
    pending_id = has_pending_application(user_id)
    if not pending_id:
        await callback.answer("Заявка уже обработана.", show_alert=True)
        return
    await callback.answer(
        f"⏳ Твоя заявка #{pending_id} на рассмотрении.",
        show_alert=True
    )


@router.callback_query(F.data == "starosta_apply_start")
async def starosta_apply_start(callback: CallbackQuery, state: FSMContext):
    user = get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала /start", show_alert=True)
        return
    if user[5] == "starosta":
        await callback.answer("👑 Ты уже староста.", show_alert=True)
        return

    pending_id = has_pending_application(callback.from_user.id)
    if pending_id:
        await callback.answer(
            f"⏳ У тебя уже есть заявка #{pending_id} на рассмотрении.",
            show_alert=True
        )
        return

    await callback.message.answer(
        "👑 <b>Заявка на старосту</b>\n\n"
        "Отправь <b>одним сообщением</b> текст заявки в <b>свободной форме</b> "
        "(ФИО, ВУЗ, факультет, группа) и, если есть, фото-подтверждение.\n\n"
        "Например:\n"
        "<i>Иванов Иван Иванович\n"
        "РГРТУ, ФВТ, группа 1234\n"
        "Староста с сентября 2025\n"
        "Прикладываю скрин из группы старост</i>\n\n"
        "📎 Фото — по желанию, можно без них.\n"
        "Если отправишь текст отдельно — заявка не подастся.\n\n"
        "Отмена: /cancel",
        parse_mode="HTML"
    )
    await state.set_state(ProfileEdit.waiting_application)
    await state.update_data(starosta_apply=True)


# ============ ПРИЁМ ЗАЯВКИ ============

_album_buffer: dict = {}
_album_tasks: dict = {}
_ALBUM_WAIT = 1.2


@router.message(ProfileEdit.waiting_application, F.media_group_id, F.photo)
async def starosta_album_collect(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    if not data.get("starosta_apply"):
        return

    gid = message.media_group_id
    entry = _album_buffer.setdefault(gid, {
        "photos": [],
        "caption": "",
        "user_id": message.from_user.id,
        "username": message.from_user.username,
    })
    entry["photos"].append(message.photo[-1].file_id)
    if message.caption and not entry["caption"]:
        entry["caption"] = message.caption

    old = _album_tasks.get(gid)
    if old:
        old.cancel()
    _album_tasks[gid] = asyncio.create_task(_finalize_album(gid, state, bot))


async def _finalize_album(gid: str, state: FSMContext, bot: Bot):
    try:
        await asyncio.sleep(_ALBUM_WAIT)
    except asyncio.CancelledError:
        return

    entry = _album_buffer.pop(gid, None)
    _album_tasks.pop(gid, None)
    if not entry:
        return

    await _process_application(
        bot=bot,
        state=state,
        user_id=entry["user_id"],
        username=entry["username"],
        caption=entry["caption"],
        photos=entry["photos"],
    )


@router.message(ProfileEdit.waiting_application, F.photo, ~F.media_group_id)
async def starosta_single_photo(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    if not data.get("starosta_apply"):
        return
    await _process_application(
        bot=bot,
        state=state,
        user_id=message.from_user.id,
        username=message.from_user.username,
        caption=message.caption or "",
        photos=[message.photo[-1].file_id],
    )


@router.message(ProfileEdit.waiting_application, F.text)
async def starosta_text_application(message: types.Message, state: FSMContext, bot: Bot):
    await _process_application(
        bot=bot,
        state=state,
        user_id=message.from_user.id,
        username=message.from_user.username,
        caption=message.text or "",
        photos=[],
    )


async def _process_application(bot: Bot, state: FSMContext, user_id: int,
                                username: str, caption: str, photos: list):
    pending_id = has_pending_application(user_id)
    if pending_id:
        await bot.send_message(
            user_id,
            f"⏳ У тебя уже есть заявка #{pending_id} на рассмотрении.\n"
            f"Дождись ответа администратора.",
            parse_mode="HTML"
        )
        await state.clear()
        return

    text = (caption or "").strip()
    if not text and not photos:
        await bot.send_message(
            user_id,
            "⚠️ Отправь текст заявки (можно с фото или без).",
            parse_mode="HTML"
        )
        return

    user = get_user(user_id)
    if not user:
        await bot.send_message(user_id, "Сначала /start")
        await state.clear()
        return

    first_line = ""
    for line in text.splitlines():
        line = line.strip()
        if line:
            first_line = line
            break

    fio = first_line[:100] if first_line else (user[4] or "без ФИО")

    photo_group_id = photos[0] if len(photos) > 0 else None
    photo_dean_id = photos[1] if len(photos) > 1 else None

    app_id = add_starosta_application(
        user_id=user_id,
        username=username,
        fio=fio,
        university=user[1],
        faculty=user[2],
        group_name=user[3],
        photo_group_id=photo_group_id,
        photo_dean_id=photo_dean_id,
    )

    await bot.send_message(
        user_id,
        f"✅ Заявка <b>#{app_id}</b> отправлена на проверку администратору.",
        parse_mode="HTML"
    )

    header = (
        f"🔔 <b>Новая заявка на старосту #{app_id}</b>\n\n"
        f"👤 @{username or '—'} (id: <code>{user_id}</code>)\n"
        f"🏛 {user[1]} | 🎓 {user[2]} | 👥 {user[3]}\n\n"
        f"<b>Текст заявки:</b>\n{text or '<i>(без текста)</i>'}"
    )

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, header, parse_mode="HTML")

            if photos:
                from aiogram.types import InputMediaPhoto
                media = [
                    InputMediaPhoto(media=pid, caption="📎 Подтверждение" if i == 0 else "")
                    for i, pid in enumerate(photos[:10])
                ]
                await bot.send_media_group(admin_id, media=media)
                for pid in photos[10:]:
                    await bot.send_photo(admin_id, pid)
            else:
                await bot.send_message(admin_id, "📎 Фото не приложены")

            await bot.send_message(admin_id, "Проверить: /applications", parse_mode="HTML")
        except Exception as e:
            print(f"[starosta] не смог уведомить админа {admin_id}: {e}")

    await state.clear()


# ============ УДАЛЕНИЕ ПРОФИЛЯ ============

@router.callback_query(F.data == "delete_profile_start")
async def delete_profile_start(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user:
        await callback.answer("Профиль уже удалён.", show_alert=True)
        return

    await callback.message.edit_text(
        "⚠️ <b>Удалить профиль?</b>\n\n"
        f"👤 ФИО: {user[4]}\n"
        f"🏛 {user[1]} | 👥 {user[3]}\n\n"
        "После удаления все твои данные (расписание, ДЗ, задолженности, отметки, XP) "
        "будут стёрты.\n\n"
        "<i>Действие нельзя отменить. Ты сможешь зарегистрироваться заново через /start.</i>",
        parse_mode="HTML",
        reply_markup=get_delete_profile_confirm_kb()
    )
    await callback.answer()


@router.callback_query(F.data == "delete_profile_no")
async def delete_profile_no(callback: CallbackQuery):
    await callback.message.edit_text("❌ Удаление отменено.")
    await callback.answer("Отменено")


@router.callback_query(F.data == "delete_profile_yes")
async def delete_profile_yes(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = get_user(user_id)
    if not user:
        await callback.answer("Профиль уже удалён.", show_alert=True)
        return

    from database import delete_user_completely
    ok = delete_user_completely(user_id)

    if not ok:
        await callback.message.edit_text("❌ Не удалось удалить профиль.")
        await callback.answer("Ошибка", show_alert=True)
        return

    await callback.message.edit_text(
        "✅ <b>Профиль удалён.</b>\n\n"
        "Чтобы продолжить пользоваться ботом, пройди регистрацию заново: /start",
        parse_mode="HTML"
    )

    await callback.message.answer(
        "👉 Отправь /start, чтобы зарегистрироваться заново.",
        parse_mode="HTML"
    )

    await callback.answer("Профиль удалён", show_alert=True)