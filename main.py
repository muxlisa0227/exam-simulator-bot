import asyncio
import os
import pandas as pd

from dotenv import load_dotenv
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    LabeledPrice,
    PreCheckoutQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    ChatJoinRequest,
)
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage


load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1003138772698"))
INVITE_LINK = os.getenv("INVITE_LINK", "https://t.me/+Gh6Fjd71Wbg0NzEx")

CARD_NUMBER = os.getenv("CARD_NUMBER", "8600 1104 1440 6946")
CARD_OWNER = os.getenv("CARD_OWNER", "Muxlisa Ibroximova")

PREMIUM_PRICE_STARS = 75
PREMIUM_PRICE_UZS = 15000

EXCEL_FILE = "questions.xlsx"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

premium_users = set()


class TestStates(StatesGroup):
    faculty = State()
    course = State()
    semester = State()
    subject = State()
    testing = State()


subjects = {
    "Xorijiy til va adabiyoti": {
        "2-kurs": {
            "4-semestr": [
                "Inklyuziv ta'lim",
                "Umumiy pedagogika",
                "Dinshunoslik",
            ]
        }
    }
}


async def health(request):
    return web.Response(text="Bot is running")


async def keep_alive():
    app = web.Application()
    app.router.add_get("/", health)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.getenv("PORT", "8080"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()


def subscription_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 Kanalga a’zo bo‘lish",
                    url=INVITE_LINK,
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ Tekshirish",
                    callback_data="check_subscription",
                )
            ],
        ]
    )


def main_menu():
    kb = ReplyKeyboardBuilder()
    kb.button(text="📚 Demo test")
    kb.button(text="💎 Premium")
    kb.button(text="📊 Natija")
    kb.button(text="🏆 Reyting")
    kb.button(text="🆘 Yordam")
    kb.adjust(2)
    return kb.as_markup(resize_keyboard=True)


def premium_menu():
    kb = ReplyKeyboardBuilder()
    kb.button(text="⭐ Telegram Stars")
    kb.button(text="💳 Click / Payme orqali")
    kb.button(text="⬅️ Orqaga")
    kb.adjust(1)
    return kb.as_markup(resize_keyboard=True)


def faculty_menu():
    kb = ReplyKeyboardBuilder()
    kb.button(text="Xorijiy til va adabiyoti")
    kb.button(text="Rus filologiyasi")
    kb.button(text="Ingliz filologiyasi")
    kb.button(text="Xalqaro Jurnalistika")
    kb.button(text="Tarjimonlik")
    kb.button(text="Sharq filologiyasi")
    kb.button(text="⬅️ Orqaga")
    kb.adjust(2)
    return kb.as_markup(resize_keyboard=True)


def course_menu():
    kb = ReplyKeyboardBuilder()
    kb.button(text="1-kurs")
    kb.button(text="2-kurs")
    kb.button(text="3-kurs")
    kb.button(text="4-kurs")
    kb.button(text="⬅️ Orqaga")
    kb.adjust(2)
    return kb.as_markup(resize_keyboard=True)


def semester_menu():
    kb = ReplyKeyboardBuilder()
    for i in range(1, 9):
        kb.button(text=f"{i}-semestr")
    kb.button(text="⬅️ Orqaga")
    kb.adjust(2)
    return kb.as_markup(resize_keyboard=True)


def subject_menu(faculty, course, semester):
    kb = ReplyKeyboardBuilder()
    subject_list = subjects.get(faculty, {}).get(course, {}).get(semester, [])

    for subject in subject_list:
        kb.button(text=subject)

    kb.button(text="⬅️ Orqaga")
    kb.adjust(1)
    return kb.as_markup(resize_keyboard=True)


def question_keyboard(question: dict):
    icons = {
        "A": "🅰️",
        "B": "🅱️",
        "C": "🇨",
        "D": "🇩",
    }

    rows = []

    for key, value in question["options"].items():
        rows.append([
            InlineKeyboardButton(
                text=f"{icons.get(key, key)} {value}",
                callback_data=f"answer:{key}",
            )
        ])

    rows.append([
        InlineKeyboardButton(
            text="🏁 Testni tugatish",
            callback_data="finish_test",
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


async def is_subscribed(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        print("SUBSCRIPTION ERROR:", e)
        return False


async def require_subscription(message: Message) -> bool:
    if await is_subscribed(message.from_user.id):
        return True

    await message.answer(
        "🔒 Botdan foydalanish uchun avval kanalga a’zo bo‘ling.\n\n"
        "A’zo bo‘lgach pastdagi ✅ Tekshirish tugmasini bosing.",
        reply_markup=subscription_keyboard(),
    )
    return False


def load_questions_from_excel(subject_name: str, is_premium: bool = False):
    if not os.path.exists(EXCEL_FILE):
        return []

    df = pd.read_excel(EXCEL_FILE)

    required_columns = [
        "subject",
        "question",
        "option_a",
        "option_b",
        "option_c",
        "option_d",
        "correct",
        "is_demo",
    ]

    for col in required_columns:
        if col not in df.columns:
            raise ValueError(f"Excel faylda '{col}' ustuni yo‘q")

    df["subject"] = df["subject"].astype(str).str.strip()
    df = df[df["subject"] == subject_name.strip()]

    if not is_premium:
        df = df[
            df["is_demo"]
            .astype(str)
            .str.upper()
            .isin(["TRUE", "1", "HA", "YES"])
        ]

    questions = []

    for _, row in df.iterrows():
        correct = str(row["correct"]).strip().upper()

        if correct not in ["A", "B", "C", "D"]:
            continue

        questions.append({
            "question": str(row["question"]).strip(),
            "options": {
                "A": str(row["option_a"]).strip(),
                "B": str(row["option_b"]).strip(),
                "C": str(row["option_c"]).strip(),
                "D": str(row["option_d"]).strip(),
            },
            "correct": correct,
        })

    return questions


async def send_question(message: Message, state: FSMContext):
    data = await state.get_data()

    questions = data.get("questions", [])
    question_index = data.get("question_index", 0)
    score = data.get("score", 0)

    if question_index >= len(questions):
        is_premium_mode = data.get("is_premium_mode", False)

        if not is_premium_mode:
            await state.update_data(pending_continue=True)

            await message.answer(
                f"✅ Demo test tugadi!\n\n"
                f"📊 Natija: {score} / {len(questions)}\n\n"
                "🔒 51-savoldan davom etish uchun Premium kerak.",
                reply_markup=premium_menu(),
            )
            return

        await state.clear()

        await message.answer(
            f"✅ Test tugadi!\n\n"
            f"📊 Natija: {score} / {len(questions)}",
            reply_markup=main_menu(),
        )
        return

    q = questions[question_index]

    text = (
        f"❓ {question_index + 1}-savol\n\n"
        f"{q['question']}\n\n"
        f"📊 Ball: {score}"
    )

    await message.answer(
        text,
        reply_markup=question_keyboard(q),
    )


async def edit_question(callback: CallbackQuery, state: FSMContext, feedback: str = ""):
    data = await state.get_data()

    questions = data.get("questions", [])
    question_index = data.get("question_index", 0)
    score = data.get("score", 0)

    if question_index >= len(questions):
        is_premium_mode = data.get("is_premium_mode", False)

        if not is_premium_mode:
            await state.update_data(pending_continue=True)

            await callback.message.edit_text(
                f"✅ Demo test tugadi!\n\n"
                f"📊 Natija: {score} / {len(questions)}\n\n"
                "🔒 51-savoldan davom etish uchun Premium kerak."
            )

            await callback.message.answer(
                "💎 Davom etish uchun to‘lov turini tanlang:",
                reply_markup=premium_menu(),
            )
            return

        await state.clear()

        await callback.message.edit_text(
            f"✅ Test tugadi!\n\n"
            f"📊 Natija: {score} / {len(questions)}"
        )

        await callback.message.answer(
            "🏠 Asosiy menyu:",
            reply_markup=main_menu(),
        )
        return

    q = questions[question_index]

    text = (
        f"{feedback}"
        f"❓ {question_index + 1}-savol\n\n"
        f"{q['question']}\n\n"
        f"📊 Ball: {score}"
    )

    await callback.message.edit_text(
        text,
        reply_markup=question_keyboard(q),
    )


@dp.chat_join_request()
async def approve_join_request(join_request: ChatJoinRequest):
    try:
        await join_request.approve()
    except Exception as e:
        print("JOIN APPROVE ERROR:", e)
        return

    try:
        await bot.send_message(
            join_request.from_user.id,
            "✅ Kanalga qabul qilindingiz!\n\n"
            "Endi botga qaytib ✅ Tekshirish tugmasini bosing.",
        )
    except Exception:
        pass


@dp.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    await state.clear()

    if not await require_subscription(message):
        return

    await message.answer(
        "Assalomu alaykum!\n\n"
        "Univer quiz botga xush kelibsiz.",
        reply_markup=main_menu(),
    )


@dp.callback_query(F.data == "check_subscription")
async def check_subscription_callback(callback: CallbackQuery):
    subscribed = await is_subscribed(callback.from_user.id)

    if subscribed:
        try:
            await callback.message.delete()
        except Exception:
            pass

        await callback.message.answer(
            "🏠 Asosiy menyu:",
            reply_markup=main_menu(),
        )

        await callback.answer()
    else:
        await callback.answer(
            "❌ Siz hali kanalga a’zo bo‘lmagansiz.",
            show_alert=True,
        )


@dp.message(F.text == "📚 Demo test")
async def demo_test(message: Message, state: FSMContext):
    if not await require_subscription(message):
        return

    await state.clear()
    await state.update_data(is_premium_mode=False)
    await state.set_state(TestStates.faculty)

    await message.answer("🏛 Fakultetni tanlang:", reply_markup=faculty_menu())


@dp.message(F.text == "💎 Premium")
async def premium_handler(message: Message, state: FSMContext):
    if not await require_subscription(message):
        return

    if message.from_user.id in premium_users:
        await state.clear()
        await state.update_data(is_premium_mode=True)
        await state.set_state(TestStates.faculty)

        await message.answer(
            "💎 Sizda Premium mavjud.\n\n"
            "🏛 Fakultetni tanlang:",
            reply_markup=faculty_menu(),
        )
        return

    await message.answer(
        "💎 Premium test\n\n"
        f"⭐ Telegram Stars: {PREMIUM_PRICE_STARS} Stars\n"
        f"💳 Click / Payme: {PREMIUM_PRICE_UZS:,} so‘m\n\n"
        "To‘lov turini tanlang:",
        reply_markup=premium_menu(),
    )


@dp.message(F.text == "⭐ Telegram Stars")
async def pay_with_stars(message: Message):
    await message.answer_invoice(
        title="💎 Premium test",
        description="51-savoldan 301-savolgacha premium savollar ochiladi.",
        payload="premium_stars",
        provider_token="",
        currency="XTR",
        prices=[
            LabeledPrice(
                label="Premium access",
                amount=PREMIUM_PRICE_STARS,
            )
        ],
    )


@dp.message(F.text == "💳 Click / Payme orqali")
async def manual_payment(message: Message):
    await message.answer(
        "💳 Click yoki Payme orqali quyidagi kartaga to‘lov qiling:\n\n"
        f"💰 Summa: {PREMIUM_PRICE_UZS:,} so‘m\n"
        f"💳 Karta: `{CARD_NUMBER}`\n"
        f"👤 Egasi: {CARD_OWNER}\n\n"
        "✅ To‘lov qilgandan keyin chek rasmini shu botga yuboring.\n"
        "Admin tekshirgandan keyin Premium ochiladi.",
    )


@dp.message(F.photo)
async def receipt_handler(message: Message):
    user = message.from_user

    if ADMIN_ID == 0:
        await message.answer("⚠️ Admin ID sozlanmagan.")
        return

    await message.forward(ADMIN_ID)

    username = f"@{user.username}" if user.username else "username yo‘q"

    await bot.send_message(
        ADMIN_ID,
        "🧾 Yangi to‘lov cheki keldi.\n\n"
        f"👤 User: {user.full_name}\n"
        f"🔗 Username: {username}\n"
        f"🆔 User ID: `{user.id}`\n\n"
        f"Premium ochish uchun:\n"
        f"`/premium_add {user.id}`",
    )

    await message.answer(
        "✅ Chekingiz adminga yuborildi.\n"
        "Tekshirilgandan keyin Premium ochiladi.",
    )


@dp.message(Command("premium_add"))
async def premium_add_handler(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Bu buyruq faqat admin uchun.")
        return

    parts = message.text.split()

    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Format: /premium_add USER_ID")
        return

    user_id = int(parts[1])
    premium_users.add(user_id)

    await message.answer(f"✅ Premium ochildi: {user_id}")

    try:
        await bot.send_message(
            user_id,
            "✅ To‘lov tasdiqlandi!\n\n"
            "💎 Sizga Premium test ochildi.\n"
            "Endi botda 💎 Premium tugmasini bosing.",
        )
    except Exception:
        pass


@dp.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)


@dp.message(F.successful_payment)
async def successful_payment_handler(message: Message, state: FSMContext):
    payment = message.successful_payment

    if payment.invoice_payload != "premium_stars":
        return

    premium_users.add(message.from_user.id)

    data = await state.get_data()
    pending_continue = data.get("pending_continue", False)
    subject_name = data.get("subject")
    old_score = data.get("score", 0)

    if pending_continue and subject_name:
        try:
            questions = load_questions_from_excel(
                subject_name=subject_name,
                is_premium=True,
            )
        except Exception as e:
            await message.answer(f"⚠️ Excel xatosi:\n{e}")
            return

        if len(questions) > 50:
            await state.update_data(
                is_premium_mode=True,
                questions=questions,
                question_index=50,
                score=old_score,
                pending_continue=False,
            )
            await state.set_state(TestStates.testing)

            await message.answer("✅ Premium ochildi! 51-savoldan davom etamiz.")
            await send_question(message, state)
            return

    await state.clear()
    await state.update_data(is_premium_mode=True)
    await state.set_state(TestStates.faculty)

    await message.answer(
        "✅ To‘lov muvaffaqiyatli amalga oshirildi!\n\n"
        "💎 Premium test ochildi.\n\n"
        "🏛 Fakultetni tanlang:",
        reply_markup=faculty_menu(),
    )


@dp.message(F.text == "⬅️ Orqaga")
async def back_to_main_from_menu(message: Message, state: FSMContext):
    current_state = await state.get_state()

    if current_state is None:
        await message.answer("🏠 Asosiy menyu:", reply_markup=main_menu())


@dp.message(TestStates.faculty, F.text == "⬅️ Orqaga")
async def back_from_faculty(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🏠 Asosiy menyuga qaytdingiz.", reply_markup=main_menu())


@dp.message(TestStates.course, F.text == "⬅️ Orqaga")
async def back_from_course(message: Message, state: FSMContext):
    await state.set_state(TestStates.faculty)
    await message.answer("🏛 Fakultetni tanlang:", reply_markup=faculty_menu())


@dp.message(TestStates.semester, F.text == "⬅️ Orqaga")
async def back_from_semester(message: Message, state: FSMContext):
    await state.set_state(TestStates.course)
    await message.answer("📘 Kursni tanlang:", reply_markup=course_menu())


@dp.message(TestStates.subject, F.text == "⬅️ Orqaga")
async def back_from_subject(message: Message, state: FSMContext):
    await state.set_state(TestStates.semester)
    await message.answer("📚 Semestrni tanlang:", reply_markup=semester_menu())


@dp.message(TestStates.faculty)
async def faculty_selected(message: Message, state: FSMContext):
    if message.text not in subjects:
        await message.answer(
            "⚠️ Iltimos, menyudan fakultet tanlang.",
            reply_markup=faculty_menu(),
        )
        return

    await state.update_data(faculty=message.text)
    await state.set_state(TestStates.course)

    await message.answer(
        f"✅ Tanlangan fakultet: {message.text}\n\n"
        "📘 Endi kursni tanlang:",
        reply_markup=course_menu(),
    )


@dp.message(TestStates.course)
async def course_selected(message: Message, state: FSMContext):
    data = await state.get_data()
    faculty = data["faculty"]

    if message.text not in subjects.get(faculty, {}):
        await message.answer(
            "⚠️ Bu kurs uchun fanlar hali qo‘shilmagan.",
            reply_markup=course_menu(),
        )
        return

    await state.update_data(course=message.text)
    await state.set_state(TestStates.semester)

    await message.answer(
        f"✅ Tanlangan kurs: {message.text}\n\n"
        "📚 Endi semestrni tanlang:",
        reply_markup=semester_menu(),
    )


@dp.message(TestStates.semester)
async def semester_selected(message: Message, state: FSMContext):
    data = await state.get_data()

    faculty = data["faculty"]
    course = data["course"]
    semester = message.text

    subject_list = subjects.get(faculty, {}).get(course, {}).get(semester, [])

    if not subject_list:
        await message.answer(
            "⚠️ Bu semestr uchun fanlar hali qo‘shilmagan.",
            reply_markup=semester_menu(),
        )
        return

    await state.update_data(semester=semester)
    await state.set_state(TestStates.subject)

    await message.answer(
        f"✅ Tanlangan semestr: {semester}\n\n"
        "📚 Endi fanni tanlang:",
        reply_markup=subject_menu(faculty, course, semester),
    )


@dp.message(TestStates.subject)
async def subject_selected(message: Message, state: FSMContext):
    data = await state.get_data()

    faculty = data["faculty"]
    course = data["course"]
    semester = data["semester"]

    subject_list = subjects.get(faculty, {}).get(course, {}).get(semester, [])

    if message.text not in subject_list:
        await message.answer(
            "⚠️ Iltimos, menyudan fan tanlang.",
            reply_markup=subject_menu(faculty, course, semester),
        )
        return

    is_premium_mode = data.get("is_premium_mode", False)

    try:
        selected_questions = load_questions_from_excel(
            subject_name=message.text,
            is_premium=is_premium_mode,
        )
    except Exception as e:
        await message.answer(f"⚠️ Excel xatosi:\n{e}")
        return

    if not selected_questions:
        await message.answer(
            "⚠️ Bu fan uchun savollar topilmadi.\n\n"
            "Excel fayldagi subject nomi botdagi fan nomi bilan bir xil bo‘lishi kerak.",
            reply_markup=subject_menu(faculty, course, semester),
        )
        return

    await state.update_data(
        subject=message.text,
        questions=selected_questions,
        question_index=0,
        score=0,
        pending_continue=False,
    )

    await state.set_state(TestStates.testing)

    mode_text = "Premium test" if is_premium_mode else "Demo test"

    await message.answer(
        f"✅ Test boshlandi!\n\n"
        f"📖 Fan: {message.text}\n"
        f"🧪 Rejim: {mode_text}\n"
        f"📌 Savollar soni: {len(selected_questions)}"
    )

    await send_question(message, state)


@dp.callback_query(TestStates.testing, F.data == "finish_test")
async def finish_test_callback(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()

    score = data.get("score", 0)
    questions = data.get("questions", [])

    await state.clear()

    await callback.message.edit_text(
        f"🏁 Test yakunlandi.\n\n"
        f"📊 Natija: {score} / {len(questions)}"
    )

    await callback.message.answer(
        "🏠 Asosiy menyu:",
        reply_markup=main_menu(),
    )

    await callback.answer()


@dp.callback_query(TestStates.testing, F.data.startswith("answer:"))
async def answer_callback(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()

    questions = data.get("questions", [])
    question_index = data.get("question_index", 0)
    score = data.get("score", 0)

    if question_index >= len(questions):
        await state.clear()
        await callback.message.edit_text("✅ Test tugagan.")
        await callback.message.answer("🏠 Asosiy menyu:", reply_markup=main_menu())
        await callback.answer()
        return

    selected_answer = callback.data.split(":")[1]
    q = questions[question_index]

    if selected_answer == q["correct"]:
        score += 1
        feedback = "✅ To‘g‘ri!\n\n"
    else:
        correct_text = q["options"].get(q["correct"], "")
        feedback = f"❌ Xato!\n✅ To‘g‘ri javob: {q['correct']}) {correct_text}\n\n"

    await state.update_data(
        question_index=question_index + 1,
        score=score,
    )

    await edit_question(callback, state, feedback=feedback)
    await callback.answer()


@dp.message(TestStates.testing)
async def block_text_while_testing(message: Message):
    await message.answer("⚠️ Javobni savol tagidagi tugmalardan tanlang.")


@dp.message(F.text == "📊 Natija")
async def result_handler(message: Message):
    await message.answer("📊 Natijalar bo‘limi keyin PostgreSQL bilan ishlaydi.")


@dp.message(F.text == "🏆 Reyting")
async def ranking_handler(message: Message):
    await message.answer("🏆 Reyting bo‘limi keyin database orqali qo‘shiladi.")


@dp.message(F.text == "🆘 Yordam")
async def help_handler(message: Message):
    await message.answer(
        "🆘 Yordam\n\n"
        "📚 Demo test — bepul 50 ta savol.\n"
        "💎 Premium — 51-savoldan 301-savolgacha.\n"
        "💳 Click/Payme orqali to‘lov qilsangiz chek rasmini yuboring.",
    )


async def main():
    await keep_alive()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())