from aiogram import Router, types, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import (
    register_user, get_user, is_user_banned,
    add_referral, get_referrer_for_user,
)
from keyboards import get_universities_kb, get_faculties_kb, get_main_menu
from config import UNIVERSITIES, FACULTIES_RGRTU, FACULTIES_RGU

router = Router()


class Registration(StatesGroup):
    waiting_university = State()
    waiting_faculty = State()
    waiting_group = State()
    waiting_name = State()


WELCOME_TEXT = (
    "📌 Это учебный бот 📌\n\n"
    "Подробнее о функционале — /help\n"
    "При обновлении бота — /start\n"
    "Если ты староста, пиши в поддержку — @hiloetc"
)


@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext,
                    command: CommandObject = None):
    user_id = message.from_user.id
    username = message.from_user.username

    if is_user_banned(user_id, username):
        await message.answer(
            "⛔ **Вы заблокированы.**\n\n"
            "Обратитесь к администратору бота.",
            parse_mode="Markdown"
        )
        return

    # ===== РЕФЕРАЛЬНАЯ ССЫЛКА =====
    referred_by = None
    if command and command.args and command.args.startswith("ref_"):
        try:
            referrer_id = int(command.args.replace("ref_", ""))
            referred_by = referrer_id
        except ValueError:
            pass

    user = get_user(user_id)

    if user:
        is_starosta = user[5] == "starosta"

        if is_starosta:
            text = (
                f"👑 <b>Ты староста!</b>\n\n"
                f"С возвращением, {user[4]}!\n"
                f"ВУЗ: {user[1]} | Группа: {user[3]}\n\n"
                f"Кнопка <b>«👑 Панель старосты»</b> — в меню ниже."
            )
        else:
            text = (
                f"С возвращением, {user[4]}!\n"
                f"ВУЗ: {user[1]} | Группа: {user[3]}"
            )

        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=get_main_menu(is_starosta, university=user[1])
        )
        return

    await state.clear()

    # сохраняем пригласившего в state — применим при регистрации
    if referred_by:
        await state.update_data(referred_by=referred_by)

    await message.answer(WELCOME_TEXT)

    await message.answer(
        "Добро пожаловать! Давай зарегистрируемся.\n\n"
        "В каком вы ВУЗе?",
        reply_markup=get_universities_kb()
    )
    await state.set_state(Registration.waiting_university)


@router.message(Registration.waiting_university)
async def process_university(message: types.Message, state: FSMContext):
    if is_user_banned(message.from_user.id, message.from_user.username):
        await state.clear()
        await message.answer("⛔ Вы заблокированы.")
        return

    text = message.text.strip()

    if text not in UNIVERSITIES:
        await message.answer("❌ Выбери ВУЗ из списка: РГРТУ или РГУ.")
        return

    await state.update_data(university=text)
    await message.answer(
        f"ВУЗ: <b>{text}</b>\n\n"
        f"Теперь выбери факультет:",
        parse_mode="HTML",
        reply_markup=get_faculties_kb(text)
    )
    await state.set_state(Registration.waiting_faculty)


@router.message(Registration.waiting_faculty)
async def process_faculty(message: types.Message, state: FSMContext):
    if is_user_banned(message.from_user.id, message.from_user.username):
        await state.clear()
        await message.answer("⛔ Вы заблокированы.")
        return

    data = await state.get_data()
    university = data.get("university", "РГРТУ")
    text = message.text.strip()

    valid_faculties = FACULTIES_RGU if university == "РГУ" else FACULTIES_RGRTU
    if text not in valid_faculties:
        await message.answer(f"❌ Выбери факультет из списка.")
        return

    await state.update_data(faculty=text)
    await message.answer("Впиши номер группы (например, 5110):")
    await state.set_state(Registration.waiting_group)


@router.message(Registration.waiting_group)
async def process_group(message: types.Message, state: FSMContext):
    if is_user_banned(message.from_user.id, message.from_user.username):
        await state.clear()
        await message.answer("⛔ Вы заблокированы.")
        return

    await state.update_data(group=message.text.strip())
    await message.answer("Напиши свое ФИО (полностью):")
    await state.set_state(Registration.waiting_name)


@router.message(Registration.waiting_name)
async def process_name(message: types.Message, state: FSMContext):
    if is_user_banned(message.from_user.id, message.from_user.username):
        await state.clear()
        await message.answer("⛔ Вы заблокированы.")
        return

    data = await state.get_data()
    referred_by = data.get("referred_by")

    register_user(
        user_id=message.from_user.id,
        university=data['university'],
        faculty=data['faculty'],
        group_name=data['group'],
        full_name=message.text.strip(),
        username=message.from_user.username,
        referred_by=referred_by,
    )

    # ===== НАЧИСЛЕНИЕ XP РЕФЕРЕРУ =====
    if referred_by and referred_by != message.from_user.id:
        # проверяем, что реферер зарегистрирован и ещё не получал бонус
        referrer = get_user(referred_by)
        existing = get_referrer_for_user(message.from_user.id)

        if referrer and not existing:
            add_referral(referred_by, message.from_user.id)

            # начисляем +3 XP рефереру
            try:
                from database import get_user_xp
                from datetime import datetime
                from zoneinfo import ZoneInfo
                import sqlite3
                from database import DB_NAME
                MSK = ZoneInfo("Europe/Moscow")

                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                cursor.execute("SELECT xp FROM user_xp WHERE user_id = ?", (referred_by,))
                row = cursor.fetchone()

                bonus = 3.0
                if row:
                    new_xp = row[0] + bonus
                    new_level = 1 + int(new_xp // 10)
                    cursor.execute(
                        "UPDATE user_xp SET xp = ?, level = ? WHERE user_id = ?",
                        (new_xp, new_level, referred_by)
                    )
                else:
                    cursor.execute(
                        "INSERT INTO user_xp (user_id, xp, level) VALUES (?, ?, 1)",
                        (referred_by, bonus)
                    )
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"[referral] не смог начислить XP: {e}")

            # уведомляем реферера
            try:
                await message.bot.send_message(
                    referred_by,
                    f"🎉 <b>По твоей ссылке зарегистрировался друг!</b>\n\n"
                    f"👤 {message.text.strip()}\n"
                    f"🎁 Тебе начислено: <b>+3 XP</b>",
                    parse_mode="HTML"
                )
            except Exception as e:
                print(f"[referral] не смог уведомить {referred_by}: {e}")

    await message.answer(
        f"✅ Вы зарегистрированы!\n\n"
        f"ВУЗ: <b>{data['university']}</b>\n"
        f"Факультет: {data['faculty']}\n"
        f"Группа: {data['group']}\n"
        f"ФИО: {message.text.strip()}",
        parse_mode="HTML",
        reply_markup=get_main_menu(False, university=data['university'])
    )

    await message.answer(WELCOME_TEXT)

    await state.clear()