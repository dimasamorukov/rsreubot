import random
import asyncio
from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.types import CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest

from database import (
    get_user, get_game_stats, update_game_stat,
    get_user_xp, restore_db, DB_NAME,
)
from keyboards import (
    get_games_menu_kb,
    get_hangman_kb,
    get_tictactoe_kb,
    get_bulls_giveup_kb,
    get_mines_kb,
)
from config import (
    HANGMAN_WORDS, CITIES_DB, ADMIN_IDS,
)

router = Router()


# ============ ХРАНИЛИЩЕ АКТИВНЫХ ИГР ============
# key = user_id, value = dict с состоянием игры

HANGMAN_STATES: dict = {}
BULLS_STATES: dict = {}
TTT_STATES: dict = {}
MINES_STATES: dict = {}


class BullsStates(StatesGroup):
    waiting_number = State()


# ============ МЕНЮ ИГР ============

@router.message(F.text == "🎮 Игры")
async def games_menu(message: types.Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return

    await message.answer(
        "🎮 <b>Игры на перемене</b>\n\n"
        "Выбери игру:",
        parse_mode="HTML",
        reply_markup=get_games_menu_kb()
    )


@router.callback_query(F.data == "game_close")
async def game_close(callback: CallbackQuery):
    # чистим состояние игры
    uid = callback.from_user.id
    HANGMAN_STATES.pop(uid, None)
    BULLS_STATES.pop(uid, None)
    TTT_STATES.pop(uid, None)
    MINES_STATES.pop(uid, None)

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await callback.answer("Закрыто")


@router.callback_query(F.data == "game_stats")
async def game_stats(callback: CallbackQuery):
    uid = callback.from_user.id
    stats = get_game_stats(uid)

    (hangman_wins, hangman_games, bulls_wins, bulls_games,
     ttt_wins, ttt_games, mines_wins, mines_games) = stats

    text = (
        f"📊 <b>Твоя статистика игр</b>\n\n"
        f"🎯 Виселица: <b>{hangman_wins}</b> / {hangman_games} побед\n"
        f"🐂 Быки и коровы: <b>{bulls_wins}</b> / {bulls_games} побед\n"
        f"⭕❌ Крестики-нолики: <b>{ttt_wins}</b> / {ttt_games} побед\n"
        f"💣 Сапёр: <b>{mines_wins}</b> / {mines_games} побед\n"
    )

    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


# ============ ВИСЕЛИЦА ============

HANGMAN_HIDDEN = "⬜"
HANGMAN_STAGES = [
    "😀", "🙂", "😐", "😟", "😰", "😵", "💀"
]


@router.callback_query(F.data == "game_hangman")
async def hangman_start(callback: CallbackQuery):
    uid = callback.from_user.id
    user = get_user(uid)
    if not user:
        await callback.answer("Сначала /start", show_alert=True)
        return

    word = random.choice(HANGMAN_WORDS).upper()
    HANGMAN_STATES[uid] = {
        "word": word,
        "guessed": set(),
        "wrong": 0,
    }

    await _render_hangman(callback.message, uid, edit=False)
    await callback.answer()


async def _render_hangman(message, uid, edit=False):
    state = HANGMAN_STATES.get(uid)
    if not state:
        return

    word = state["word"]
    guessed = state["guessed"]
    wrong = state["wrong"]

    # отображаемое слово
    display = " ".join(
        letter if letter in guessed else "·" for letter in word
    )

    stage = HANGMAN_STAGES[min(wrong, len(HANGMAN_STAGES) - 1)]
    wrong_letters = "".join(sorted(l for l in guessed if l not in word))

    text = (
        f"🎯 <b>Виселица</b>\n\n"
        f"{stage}  Ошибок: <b>{wrong}/6</b>\n\n"
        f"📖 <b>{display}</b>\n"
    )
    if wrong_letters:
        text += f"❌ {wrong_letters}\n"

    kb = get_hangman_kb(word, guessed, wrong)

    if edit:
        try:
            await message.edit_text(text, parse_mode="HTML", reply_markup=kb)
            return
        except TelegramBadRequest:
            pass

    await message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "hangman_noop")
async def hangman_noop(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data.startswith("hangman_letter_"))
async def hangman_letter(callback: CallbackQuery):
    uid = callback.from_user.id
    state = HANGMAN_STATES.get(uid)
    if not state:
        await callback.answer("Игра не активна.", show_alert=True)
        return

    letter = callback.data.replace("hangman_letter_", "").upper()
    word = state["word"]
    guessed = state["guessed"]

    if letter in guessed:
        await callback.answer("Уже использована")
        return

    guessed.add(letter)

    if letter not in word:
        state["wrong"] += 1

    # проверка победы
    if all(l in guessed for l in word):
        update_game_stat(uid, "hangman", won=True)
        HANGMAN_STATES.pop(uid, None)
        await callback.message.edit_text(
            f"🎉 <b>Победа!</b>\n\n"
            f"Слово: <b>{word}</b>\n"
            f"Ошибок: {state['wrong']}",
            parse_mode="HTML"
        )
        await callback.answer("Победа!")
        return

    # проверка проигрыша
    if state["wrong"] >= 6:
        update_game_stat(uid, "hangman", won=False)
        HANGMAN_STATES.pop(uid, None)
        await callback.message.edit_text(
            f"💀 <b>Проигрыш!</b>\n\n"
            f"Слово было: <b>{word}</b>",
            parse_mode="HTML"
        )
        await callback.answer("Проигрыш")
        return

    await _render_hangman(callback.message, uid, edit=True)
    await callback.answer()


@router.callback_query(F.data == "hangman_giveup")
async def hangman_giveup(callback: CallbackQuery):
    uid = callback.from_user.id
    state = HANGMAN_STATES.pop(uid, None)
    if not state:
        await callback.answer("Игра не активна.", show_alert=True)
        return

    update_game_stat(uid, "hangman", won=False)
    await callback.message.edit_text(
        f"🏳️ <b>Сдался</b>\n\n"
        f"Слово было: <b>{state['word']}</b>",
        parse_mode="HTML"
    )
    await callback.answer("Сдался")


# ============ БЫКИ И КОРОВЫ ============

@router.callback_query(F.data == "game_bulls")
async def bulls_start(callback: CallbackQuery):
    uid = callback.from_user.id
    user = get_user(uid)
    if not user:
        await callback.answer("Сначала /start", show_alert=True)
        return

    # 4 уникальные цифры
    digits = list("0123456789")
    random.shuffle(digits)
    secret = "".join(digits[:4])

    BULLS_STATES[uid] = {
        "secret": secret,
        "attempts": 0,
    }

    await callback.message.answer(
        "🐂🐄 <b>Быки и коровы</b>\n\n"
        "Я загадал <b>4 цифры</b> (без повторов).\n\n"
        "Пришли 4-значное число.\n"
        "🐂 — цифра на своём месте\n"
        "🐄 — цифра есть, но не на месте\n\n"
        "<i>Отмена — /cancel</i>",
        parse_mode="HTML",
        reply_markup=get_bulls_giveup_kb()
    )
    await callback.answer()


@router.message(F.text.regexp(r"^\d{4}$"))
async def bulls_guess(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    game = BULLS_STATES.get(uid)
    if not game:
        return  # не в игре

    guess = message.text.strip()

    # проверка уникальности цифр
    if len(set(guess)) != 4:
        await message.answer("❌ Цифры не должны повторяться.")
        return

    secret = game["secret"]
    game["attempts"] += 1

    bulls = sum(1 for i in range(4) if guess[i] == secret[i])
    cows = sum(1 for d in guess if d in secret) - bulls

    if bulls == 4:
        update_game_stat(uid, "bulls", won=True)
        BULLS_STATES.pop(uid, None)
        await message.answer(
            f"🎉 <b>Победа!</b>\n\n"
            f"Число: <b>{secret}</b>\n"
            f"Попыток: {game['attempts']}",
            parse_mode="HTML"
        )
        return

    await message.answer(
        f"🐂 {bulls}  🐄 {cows}\n"
        f"Попытка №{game['attempts']}",
        reply_markup=get_bulls_giveup_kb()
    )


@router.callback_query(F.data == "bulls_giveup")
async def bulls_giveup(callback: CallbackQuery):
    uid = callback.from_user.id
    game = BULLS_STATES.pop(uid, None)
    if not game:
        await callback.answer("Игра не активна.", show_alert=True)
        return

    update_game_stat(uid, "bulls", won=False)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass
    await callback.message.answer(
        f"🏳️ <b>Сдался</b>\n\n"
        f"Число было: <b>{game['secret']}</b>",
        parse_mode="HTML"
    )
    await callback.answer("Сдался")


# ============ КРЕСТИКИ-НОЛИКИ ============

def _ttt_winner(board):
    """Возвращает 'X', 'O' или None."""
    lines = [
        (0, 1, 2), (3, 4, 5), (6, 7, 8),  # строки
        (0, 3, 6), (1, 4, 7), (2, 5, 8),  # столбцы
        (0, 4, 8), (2, 4, 6),             # диагонали
    ]
    for a, b, c in lines:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    return None


def _ttt_full(board):
    return all(cell for cell in board)


def _ttt_best_move(board):
    """Простой AI: победить → заблокировать → центр → угол → любая."""
    # 1. Победить
    for i in range(9):
        if not board[i]:
            board[i] = "O"
            if _ttt_winner(board) == "O":
                board[i] = ""
                return i
            board[i] = ""

    # 2. Заблокировать
    for i in range(9):
        if not board[i]:
            board[i] = "X"
            if _ttt_winner(board) == "X":
                board[i] = ""
                return i
            board[i] = ""

    # 3. Центр
    if not board[4]:
        return 4

    # 4. Углы
    corners = [0, 2, 6, 8]
    random.shuffle(corners)
    for i in corners:
        if not board[i]:
            return i

    # 5. Любая
    empty = [i for i in range(9) if not board[i]]
    return random.choice(empty) if empty else None


@router.callback_query(F.data == "game_tictactoe")
async def ttt_start(callback: CallbackQuery):
    uid = callback.from_user.id
    user = get_user(uid)
    if not user:
        await callback.answer("Сначала /start", show_alert=True)
        return

    board = [""] * 9
    TTT_STATES[uid] = board

    await callback.message.answer(
        "⭕❌ <b>Крестики-нолики</b>\n\n"
        "Ты — <b>X</b>. Я — <b>O</b>.\n"
        "Твой ход!",
        parse_mode="HTML",
        reply_markup=get_tictactoe_kb(board)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ttt_cell_"))
async def ttt_move(callback: CallbackQuery):
    uid = callback.from_user.id
    board = TTT_STATES.get(uid)
    if board is None:
        await callback.answer("Игра не активна.", show_alert=True)
        return

    try:
        idx = int(callback.data.replace("ttt_cell_", ""))
    except ValueError:
        await callback.answer("Ошибка", show_alert=True)
        return

    if board[idx]:
        await callback.answer("Занято", show_alert=True)
        return

    # ход игрока
    board[idx] = "X"

    # проверка победы игрока
    if _ttt_winner(board) == "X":
        update_game_stat(uid, "tictactoe", won=True)
        TTT_STATES.pop(uid, None)
        await callback.message.edit_text(
            "🎉 <b>Ты победил!</b>",
            parse_mode="HTML"
        )
        await callback.answer("Победа!")
        return

    if _ttt_full(board):
        update_game_stat(uid, "tictactoe", won=False)
        TTT_STATES.pop(uid, None)
        await callback.message.edit_text(
            "🤝 <b>Ничья!</b>",
            parse_mode="HTML"
        )
        await callback.answer("Ничья")
        return

    # ход бота
    bot_idx = _ttt_best_move(board)
    if bot_idx is not None:
        board[bot_idx] = "O"

    if _ttt_winner(board) == "O":
        update_game_stat(uid, "tictactoe", won=False)
        TTT_STATES.pop(uid, None)
        await callback.message.edit_text(
            "😢 <b>Я победил!</b>",
            parse_mode="HTML"
        )
        await callback.answer("Бот победил")
        return

    if _ttt_full(board):
        update_game_stat(uid, "tictactoe", won=False)
        TTT_STATES.pop(uid, None)
        await callback.message.edit_text(
            "🤝 <b>Ничья!</b>",
            parse_mode="HTML"
        )
        await callback.answer("Ничья")
        return

    await callback.message.edit_reply_markup(
        reply_markup=get_tictactoe_kb(board)
    )
    await callback.answer()


@router.callback_query(F.data == "ttt_giveup")
async def ttt_giveup(callback: CallbackQuery):
    uid = callback.from_user.id
    if uid not in TTT_STATES:
        await callback.answer("Игра не активна.", show_alert=True)
        return

    TTT_STATES.pop(uid, None)
    update_game_stat(uid, "tictactoe", won=False)
    await callback.message.edit_text("🏳️ <b>Ты сдался</b>", parse_mode="HTML")
    await callback.answer("Сдался")


# ============ САПЁР ============

MINES_SIZE = 5
MINES_COUNT = 5


def _mines_generate():
    """Возвращает (board_state, mines_set)."""
    total = MINES_SIZE * MINES_SIZE
    mines = set(random.sample(range(total), MINES_COUNT))
    board = ["hidden"] * total
    return board, mines


def _mines_count_around(idx, mines):
    """Сколько мин вокруг клетки idx."""
    row = idx // MINES_SIZE
    col = idx % MINES_SIZE
    count = 0
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            r, c = row + dr, col + dc
            if 0 <= r < MINES_SIZE and 0 <= c < MINES_SIZE:
                if r * MINES_SIZE + c in mines:
                    count += 1
    return count


@router.callback_query(F.data == "game_mines")
async def mines_start(callback: CallbackQuery):
    uid = callback.from_user.id
    user = get_user(uid)
    if not user:
        await callback.answer("Сначала /start", show_alert=True)
        return

    board, mines = _mines_generate()
    MINES_STATES[uid] = {
        "board": board,
        "mines": mines,
        "flag_mode": False,
    }

    await callback.message.answer(
        f"💣 <b>Сапёр</b> {MINES_SIZE}×{MINES_SIZE}\n\n"
        f"Мины: <b>{MINES_COUNT}</b>\n"
        f"Тыкай клетки — открывай.\n"
        f"Режим флажка — поставить 🚩\n\n"
        f"<i>Не наступи на 💣!</i>",
        parse_mode="HTML",
        reply_markup=get_mines_kb(board, MINES_SIZE)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("mines_open_"))
async def mines_open(callback: CallbackQuery):
    uid = callback.from_user.id
    state = MINES_STATES.get(uid)
    if not state:
        await callback.answer("Игра не активна.", show_alert=True)
        return

    try:
        idx = int(callback.data.replace("mines_open_", ""))
    except ValueError:
        await callback.answer("Ошибка", show_alert=True)
        return

    board = state["board"]
    mines = state["mines"]
    flag_mode = state["flag_mode"]

    if board[idx] in ("open", "mine"):
        await callback.answer("Уже открыто")
        return

    # режим флажка
    if flag_mode:
        if board[idx] == "flag":
            board[idx] = "hidden"
        else:
            board[idx] = "flag"
        await callback.message.edit_reply_markup(
            reply_markup=get_mines_kb(board, MINES_SIZE)
        )
        await callback.answer("🚩")
        return

    if board[idx] == "flag":
        await callback.answer("Тут флажок. Сними его.")
        return

    # открытие клетки
    if idx in mines:
        # проигрыш — открываем все мины
        for m in mines:
            board[m] = "mine"
        MINES_STATES.pop(uid, None)
        update_game_stat(uid, "mines", won=False)
        await callback.message.edit_text(
            "💥 <b>БУМ! Ты попал на мину.</b>",
            parse_mode="HTML"
        )
        await callback.answer("Проигрыш")
        return

    # открытие (пустая клетка или с числом)
    board[idx] = "open"

    # проверка победы: все не-мины открыты
    all_opened = all(
        board[i] == "open" for i in range(MINES_SIZE * MINES_SIZE)
        if i not in mines
    )
    if all_opened:
        for m in mines:
            board[m] = "flag"
        MINES_STATES.pop(uid, None)
        update_game_stat(uid, "mines", won=True)
        await callback.message.edit_text(
            "🎉 <b>Победа! Все мины найдены.</b>",
            parse_mode="HTML"
        )
        await callback.answer("Победа!")
        return

    await callback.message.edit_reply_markup(
        reply_markup=get_mines_kb(board, MINES_SIZE)
    )
    await callback.answer()


@router.callback_query(F.data == "mines_flag_mode")
async def mines_toggle_flag(callback: CallbackQuery):
    uid = callback.from_user.id
    state = MINES_STATES.get(uid)
    if not state:
        await callback.answer("Игра не активна.", show_alert=True)
        return

    state["flag_mode"] = not state["flag_mode"]
    mode = "🚩 Режим флажка: ВКЛ" if state["flag_mode"] else "⬜ Режим флажка: ВЫКЛ"
    await callback.answer(mode, show_alert=False)


@router.callback_query(F.data == "mines_giveup")
async def mines_giveup(callback: CallbackQuery):
    uid = callback.from_user.id
    state = MINES_STATES.pop(uid, None)
    if not state:
        await callback.answer("Игра не активна.", show_alert=True)
        return

    update_game_stat(uid, "mines", won=False)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass
    await callback.message.answer("🏳️ <b>Ты сдался</b>", parse_mode="HTML")
    await callback.answer("Сдался")


# ============ ВОССТАНОВЛЕНИЕ БД (для /restore) ============

@router.message(F.document)
async def handle_db_upload(message: types.Message, bot: Bot):
    """
    Ловит .db файл, загруженный админом (после /restore).
    """
    if message.from_user.id not in ADMIN_IDS:
        return

    doc = message.document
    if not doc.file_name or not doc.file_name.endswith(".db"):
        return

    # качаем во временный файл
    import os
    from config import BACKUP_DIR

    os.makedirs(BACKUP_DIR, exist_ok=True)
    tmp_path = os.path.join(BACKUP_DIR, f"restore_{message.from_user.id}.db")

    try:
        file = await bot.get_file(doc.file_id)
        await bot.download_file(file.file_path, tmp_path)
    except Exception as e:
        await message.answer(f"❌ Не удалось скачать файл: {e}")
        return

    # пробуем восстановить
    ok = restore_db(tmp_path)

    # удаляем временный файл
    try:
        os.remove(tmp_path)
    except Exception:
        pass

    if ok:
        await message.answer(
            "✅ <b>БД восстановлена!</b>\n\n"
            "⚠️ Рекомендуется перезапустить бота, чтобы все процессы подхватили новую БД.",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            "❌ Не удалось восстановить БД.\n"
            "Возможно, файл повреждён или не является .db."
        )