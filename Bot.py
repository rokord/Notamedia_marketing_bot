import asyncio
import os
import json
from dataclasses import dataclass
from typing import List, Dict, Optional
from datetime import datetime

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.filters import CommandStart
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

# --- Загрузка окружения ---

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден в .env")

if not ADMIN_CHAT_ID:
    raise RuntimeError("ADMIN_CHAT_ID не найден в .env")

ADMIN_CHAT_ID = int(ADMIN_CHAT_ID)

# --- Пути для логов ---

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

COMPLETED_LOG = os.path.join(LOG_DIR, "quiz_completed.jsonl")
ABANDONED_LOG = os.path.join(LOG_DIR, "quiz_abandoned.jsonl")


def log_to_file(path: str, payload: dict) -> None:
    """Записать одну строку JSON в файл-лог."""
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"Ошибка записи лога в {path}: {e}")


# --- Описание структуры вопросов ---

@dataclass
class QuizQuestion:
    id: int
    key: str
    text: str
    qtype: str  # "text" или "choice"
    options: Optional[List[str]] = None
    scores: Optional[List[int]] = None  # для блока диагностики (0/1/2)
    category: Optional[str] = None      # для рекомендаций (analytics, product, ...)


QUESTIONS: List[QuizQuestion] = [
    # БЛОК 1. ДАННЫЕ О РЕСПОНДЕНТЕ
    QuizQuestion(1, "name", "1. Как вас зовут?", "text"),
    QuizQuestion(2, "company", "2. Какую компанию вы представляете?", "text"),
    QuizQuestion(3, "website", "3. Укажите сайт вашей компании", "text"),
    QuizQuestion(4, "contact", "4. Ваш телефон или Telegram @username для связи", "text"),
    QuizQuestion(
        5,
        "webinar",
        "5. Вы участвовали в вебинаре или смотрели запись?",
        "choice",
        options=[
            "Присутствовал(а) онлайн",
            "Смотрел(а) в записи",
            "Пока не смотрел(а), просто прохожу диагностику",
        ],
    ),

    # БЛОК 2. КВАЛИФИКАЦИЯ
    QuizQuestion(
        6,
        "status_international",
        "6. Какой сейчас статус выхода вашей компании на международный рынок?",
        "choice",
        options=[
            "Только изучаем тему",
            "Уже готовимся, в процессе анализа/разработки",
            "Готовы запускаться в ближайшие 3–6 месяцев",
            "Уже работаем на зарубежных рынках",
        ],
    ),
    QuizQuestion(
        7,
        "experience_new_markets",
        "7. Есть ли у вас опыт выхода на новые рынки?",
        "choice",
        options=[
            "Да, успешный опыт",
            "Пытались выходить, но были сложности",
            "Нет, планируем впервые",
            "Пока только изучаем тему",
        ],
    ),
    QuizQuestion(
        8,
        "target_markets",
        "8. На какие рынки вы планируете выходить?",
        "text",
    ),

    # БЛОК 3. ДИАГНОСТИКА ГОТОВНОСТИ
    QuizQuestion(
        9,
        "q9",
        "9. Оценивали ли вы ёмкость рынка, спрос и прогноз на 3–5 лет?",
        "choice",
        options=[
            "Да, есть глубокая аналитика",
            "Частично изучали",
            "Нет, не проводили анализ",
        ],
        scores=[2, 1, 0],
        category="analytics",
    ),
    QuizQuestion(
        10,
        "q10",
        "10. Понимаете ли вы конкурентное поле на целевом рынке?",
        "choice",
        options=[
            "Да, есть подробный конкурентный анализ",
            "Частично",
            "Нет, не анализировали",
        ],
        scores=[2, 1, 0],
        category="analytics",
    ),
    QuizQuestion(
        11,
        "q11",
        "11. Есть ли у вас сформированная стратегия входа на рынок?",
        "choice",
        options=[
            "Да, сформирована",
            "Есть черновик",
            "Пока нет стратегии",
        ],
        scores=[2, 1, 0],
        category="analytics",
    ),

    # Адаптация продукта (product)
    QuizQuestion(
        12,
        "q12",
        "12. Адаптирован ли ваш продукт под культурные особенности нового рынка?",
        "choice",
        options=[
            "Да",
            "Частично",
            "Нет",
        ],
        scores=[2, 1, 0],
        category="product",
    ),
    QuizQuestion(
        13,
        "q13",
        "13. Знаете ли вы локальные требования рынка? (сертификация, логистика, язык, платёжные системы, законодательство)",
        "choice",
        options=[
            "Да, полностью",
            "Частично",
            "Нет, пока не изучали",
        ],
        scores=[2, 1, 0],
        category="product",
    ),

    # Позиционирование и коммуникации (positioning)
    QuizQuestion(
        14,
        "q14",
        "14. Адаптировали ли вы позиционирование и ключевые сообщения под локальную культуру?",
        "choice",
        options=[
            "Да",
            "Частично",
            "Нет",
        ],
        scores=[2, 1, 0],
        category="positioning",
    ),
    QuizQuestion(
        15,
        "q15",
        "15. Анализировали ли вы культурные барьеры и локальные триггеры аудитории?",
        "choice",
        options=[
            "Да",
            "Частично",
            "Нет",
        ],
        scores=[2, 1, 0],
        category="positioning",
    ),

    # Визуал, бренд и сайт (visual)
    QuizQuestion(
        16,
        "q16",
        "16. Адаптирован ли визуальный стиль бренда под культурные коды нового рынка? (цвета, формы, композиции, шрифты)",
        "choice",
        options=[
            "Да",
            "Частично",
            "Нет",
        ],
        scores=[2, 1, 0],
        category="visual",
    ),
    QuizQuestion(
        17,
        "q17",
        "17. Локализован ли ваш сайт под требования рынка? (язык, визуал, структура, CTA, примеры, доверительные маркеры)",
        "choice",
        options=[
            "Да",
            "Частично",
            "Нет",
        ],
        scores=[2, 1, 0],
        category="visual",
    ),

    # UX/UI (ux)
    QuizQuestion(
        18,
        "q18",
        "18. Проводили ли вы аудит UX под локальные сценарии поведения?",
        "choice",
        options=[
            "Да",
            "Частично",
            "Нет",
        ],
        scores=[2, 1, 0],
        category="ux",
    ),
    QuizQuestion(
        19,
        "q19",
        "19. Понимаете ли вы цифровое поведение локальных пользователей? (паттерны, предпочтения, устройства, каналы входа)",
        "choice",
        options=[
            "Да",
            "Частично",
            "Нет",
        ],
        scores=[2, 1, 0],
        category="ux",
    ),

    # Маркетинг и каналы (marketing)
    QuizQuestion(
        20,
        "q20",
        "20. Есть ли у вас медиастратегия для выхода на выбранный рынок? (каналы, бюджеты, источники трафика, лидогенерация)",
        "choice",
        options=[
            "Да",
            "Черновой вариант",
            "Нет",
        ],
        scores=[2, 1, 0],
        category="marketing",
    ),

    # Локальные цифровые площадки (channels)
    QuizQuestion(
        21,
        "q21",
        "21. Насколько ваша компания готова работать с локальными цифровыми площадками (соцсети, маркетплейсы, рекламные сети)?",
        "choice",
        options=[
            "Готовы полностью (понимаем каналы, есть адаптация, контент и процессы)",
            "Частично готовы (понимаем каналы, но нет адаптации/контента/процессов)",
            "Не готовы (не знаем, какие каналы работают и что там делать)",
        ],
        scores=[2, 1, 0],
        category="channels",
    ),
]

MAX_SCORE = 30

LEVELS = [
    (0, 8, "🟧 0–8 баллов — БАЗОВЫЙ УРОВЕНЬ",
     "Вы только начинаете путь. Это отличная точка старта, чтобы выстроить базу: исследования, анализ спроса, сегментацию, базовое позиционирование, первичные гипотезы."),
    (9, 17, "🟨 9–17 баллов — СРЕДНИЙ УРОВЕНЬ",
     "У вас есть фундамент, но много критических зон роста. Важно усилить аналитику рынка, адаптацию продукта, UX, сайт и маркетинг."),
    (18, 24, "🟦 18–24 балла — ВЫСОКИЙ УРОВЕНЬ",
     "Вы двигаетесь в правильном направлении. Осталось адаптировать детали, провести UX/маркетинг-локализацию, собрать локальное MVP и протестировать офферы."),
    (25, 30, "🟩 25–30 баллов — ПОЧТИ ГОТОВЫ!",
     "У компании уже есть сильная база для масштабирования. Можно планировать пилоты, локальные тесты и запуск первых кампаний в выбранных странах."),
]

CATEGORY_TITLES = {
    "analytics": "Аналитика рынка",
    "product": "Адаптация продукта",
    "positioning": "Позиционирование и коммуникации",
    "visual": "Визуал, бренд и сайт",
    "ux": "UX/UI и пользовательский опыт",
    "marketing": "Маркетинг и каналы",
    "channels": "Работа с локальными цифровыми площадками",
}

class QuizState(StatesGroup):
    in_progress = State()


router = Router()


def build_choice_keyboard(question_index: int) -> InlineKeyboardMarkup:
    q = QUESTIONS[question_index]
    buttons = []
    for i, option in enumerate(q.options or []):
        callback_data = f"q:{question_index}:opt:{i}"
        buttons.append([InlineKeyboardButton(text=option, callback_data=callback_data)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def send_question(message: Message, state: FSMContext, question_index: int):
    if question_index >= len(QUESTIONS):
        await finish_quiz(message, state)
        return

    q = QUESTIONS[question_index]
    await state.update_data(current_index=question_index)

    if q.qtype == "text":
        await message.answer(q.text)
    elif q.qtype == "choice":
        kb = build_choice_keyboard(question_index)
        await message.answer(q.text, reply_markup=kb)


def get_level_description(score: int):
    for low, high, title, desc in LEVELS:
        if low <= score <= high:
            return title, desc
    return "Уровень не определён", "Не удалось определить уровень по шкале."


async def finish_quiz(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        answers: Dict[str, str] = data.get("answers", {})
        score: int = data.get("score", 0)
        category_scores: Dict[str, int] = data.get("category_scores", {})

        title, desc = get_level_description(score)

        strong_blocks = []
        growth_blocks = []

        for cat, total in category_scores.items():
            max_cat_score = 0
            for q in QUESTIONS:
                if q.category == cat and q.scores:
                    max_cat_score += max(q.scores)
            if max_cat_score == 0:
                continue
            if total >= max_cat_score * 0.75:
                strong_blocks.append(CATEGORY_TITLES.get(cat, cat))
            else:
                growth_blocks.append(CATEGORY_TITLES.get(cat, cat))

        strong_text = "— " + "\n— ".join(strong_blocks) if strong_blocks else \
            "— Пока не выделены — это тоже результат: есть куда расти."
        growth_text = "— " + "\n— ".join(growth_blocks) if growth_blocks else \
            "— Серьёзных зон роста по диагностике не выявлено."

        result_text = (
            "Готово! 🎉 Мы рассчитали вашу готовность к выходу на международный рынок.\n\n"
            f"Ваш результат: {score} из {MAX_SCORE} баллов\n"
            f"📊 Уровень готовности: {title}\n\n"
            f"{desc}\n\n"
            "🧭 Персональные рекомендации\n\n"
            "Ваши сильные стороны:\n"
            f"{strong_text}\n\n"
            "Зоны роста:\n"
            f"{growth_text}\n\n"
            "🎯 Подробный гайд по инструментам и книгам вы можете посмотреть по ссылке:\n"
            "👉 https://example.com/guide\n"
        )

        await message.answer(result_text)

        ask_btn = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Задать вопрос",
                        url="https://t.me/iam_sveta"
                    )
                ]
            ]
        )
        await message.answer(
            "Спасибо, что прошли диагностику! 🚀\nЕсли остались вопросы — нажмите кнопку ниже, чтобы задать вопрос напрямую.",
            reply_markup=ask_btn,
        )

        # логирование завершённой сессии
        user = message.from_user
        payload_completed = {
            "type": "completed",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "user_id": user.id if user else None,
            "username": user.username if user else None,
            "full_name": user.full_name if user else None,
            "score": score,
            "max_score": MAX_SCORE,
            "level_title": title,
            "level_description": desc,
            "answers": answers,
        }
        log_to_file(COMPLETED_LOG, payload_completed)

        # отправка в админ-чат
        try:
            username = f"@{user.username}" if user and user.username else "—"
            full_name = user.full_name if user else "—"
            user_id = user.id if user else "—"

            lines = [
                "📥 Новый результат диагностики",
                "",
                f"Пользователь: {full_name} (id={user_id}, {username})",
                "",
            ]

            contact_value = answers.get("contact")
            if contact_value:
                lines.append(f"Контакт (вопрос 4): {contact_value}")
                lines.append("")

            lines.append(f"Итоговый балл: {score} из {MAX_SCORE}")
            lines.append("")
            lines.append("Ответы пользователя:")

            for q in QUESTIONS:
                val = answers.get(q.key, "(нет ответа)")
                lines.append(f"{q.id}. {q.text}\nОтвет: {val}\n")

            admin_text = "\n".join(lines)

            await message.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_text)
        except Exception as e:
            print("Ошибка при отправке в админ-чат:", e)

    except Exception as e:
        print("Ошибка в finish_quiz:", e)
        await message.answer(
            "Произошла ошибка при формировании результатов, но ваши ответы сохранены. "
            "Пожалуйста, сообщите об этом организатору."
        )
    finally:
        await state.clear()


async def process_answer_common(obj, state: FSMContext, answer_text: str):
    data = await state.get_data()
    question_index = data.get("current_index", 0)
    answers: Dict[str, str] = data.get("answers", {})
    score: int = data.get("score", 0)
    category_scores: Dict[str, int] = data.get("category_scores", {})

    q = QUESTIONS[question_index]
    answers[q.key] = answer_text

    if q.scores is not None and q.category:
        if q.options:
            try:
                option_index = q.options.index(answer_text)
            except ValueError:
                option_index = None
        else:
            option_index = None

        if option_index is not None and 0 <= option_index < len(q.scores):
            gained = q.scores[option_index]
            score += gained
            category_scores[q.category] = category_scores.get(q.category, 0) + gained

    await state.update_data(
        answers=answers,
        score=score,
        category_scores=category_scores,
    )

    next_index = question_index + 1
    if isinstance(obj, Message):
        await send_question(obj, state, next_index)
    elif isinstance(obj, CallbackQuery):
        await obj.message.edit_reply_markup(reply_markup=None)
        await send_question(obj.message, state, next_index)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state == QuizState.in_progress.state:
        data = await state.get_data()
        answers: Dict[str, str] = data.get("answers", {})
        score: int = data.get("score", 0)
        current_index: int = data.get("current_index", 0)

        if len(answers) >= 5:
            user = message.from_user
            last_question = QUESTIONS[current_index].id if 0 <= current_index < len(QUESTIONS) else None

            payload_abandoned = {
                "type": "abandoned",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "user_id": user.id if user else None,
                "username": user.username if user else None,
                "full_name": user.full_name if user else None,
                "score_so_far": score,
                "last_question_index": current_index,
                "last_question_id": last_question,
                "answers": answers,
            }
            log_to_file(ABANDONED_LOG, payload_abandoned)
            print("Незавершённая сессия залогирована в quiz_abandoned.jsonl")

        await state.clear()

    text = (
        "Привет! 👋 Это диагностика готовности компании к выходу на международный рынок.\n\n"
        "Она поможет понять, насколько вы готовы к масштабированию в другие страны — и что нужно улучшить.\n\n"
        "Диагностика состоит из 21 вопроса и займет 3–4 минуты. В конце вы получите результат готовности и персональные рекомендации.\n\n"
        "Готовы начать?"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Да, начать ✅", callback_data="start_quiz")]
        ]
    )
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "start_quiz")
async def start_quiz(callback: CallbackQuery, state: FSMContext):
    await state.set_state(QuizState.in_progress)
    await state.update_data(
        current_index=0,
        answers={},
        score=0,
        category_scores={},
    )

    explanation = (
        "Отлично!\n\n"
        "Сначала — несколько вопросов о вашей компании и статусе выхода на рынок. "
        "Затем — короткая диагностика по ключевым направлениям: аналитика, продукт, UX, маркетинг, позиционирование, сайт, визуал.\n\n"
        "После этого вы увидите ваш уровень готовности и рекомендации, что улучшить.\n\n"
        "Начнём 👇"
    )
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(explanation)
    await send_question(callback.message, state, 0)


@router.message(QuizState.in_progress)
async def handle_text_answer(message: Message, state: FSMContext):
    data = await state.get_data()
    question_index = data.get("current_index", 0)
    q = QUESTIONS[question_index]

    if q.qtype != "text":
        await message.answer("Пожалуйста, выберите вариант с помощью кнопок ниже 👇")
        return

    answer_text = message.text.strip()
    await process_answer_common(message, state, answer_text)


@router.callback_query(QuizState.in_progress, F.data.startswith("q:"))
async def handle_choice_answer(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    if len(parts) != 4:
        await callback.answer("Некорректные данные.")
        return

    _, q_index_str, _, opt_index_str = parts
    try:
        q_index = int(q_index_str)
        opt_index = int(opt_index_str)
    except ValueError:
        await callback.answer("Некорректные данные.")
        return

    data = await state.get_data()
    current_index = data.get("current_index", 0)

    if q_index != current_index:
        await callback.answer("Этот вопрос уже был обработан.")
        return

    q = QUESTIONS[q_index]

    if not q.options or not (0 <= opt_index < len(q.options)):
        await callback.answer("Некорректный вариант.")
        return

    answer_text = q.options[opt_index]
    await callback.answer()
    await process_answer_common(callback, state, answer_text)


async def main():
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    print("Бот запущен. Нажми /start в личке или в группе.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
