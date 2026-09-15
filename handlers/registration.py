from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import register_user, get_user, is_user_banned
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
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username

    if is_user_banned(user_id, username):
        await message.answer(
            "⛔ **Вы заблокированы.**\n\n"
            "Обратитесь к администратору бота.",
            parse_mode="Markdown"
        )
        return

    user = get_user(user_id)

    if user:
        is_admin = user[5] == 'starosta'
        await message.answer(
            f"С возвращением, {user[4]}!\n"
            f"ВУЗ: {user[1]} | Группа: {user[3]}",
            reply_markup=get_main_menu(is_admin, university=user[1])
        )
        return

    await state.clear()

    # Приветствие до регистрации
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

    register_user(
        user_id=message.from_user.id,
        university=data['university'],
        faculty=data['faculty'],
        group_name=data['group'],
        full_name=message.text.strip()
    )

    await message.answer(
        f"✅ Вы зарегистрированы!\n\n"
        f"ВУЗ: <b>{data['university']}</b>\n"
        f"Факультет: {data['faculty']}\n"
        f"Группа: {data['group']}\n"
        f"ФИО: {message.text.strip()}",
        parse_mode="HTML",
        reply_markup=get_main_menu(False, university=data['university'])
    )

    # Приветствие после регистрации
    await message.answer(WELCOME_TEXT)

    await state.clear()