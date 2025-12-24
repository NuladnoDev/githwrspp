import asyncio
import hashlib
import json
import os
import re
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandStart
from dotenv import load_dotenv

from main import (
    STUDENTS_URL,
    download_file,
    fetch_page,
    find_schedule_links,
    parse_schedule_for_group,
    read_excel_rows,
)
from server import (
    fetch_group_schedule,
    fetch_group_schedule_for_offset,
    get_near_schedule_days,
    select_daily_schedule_link,
    extract_schedule_date,
)
from text_config import (
    HELP_TEXT,
    DAY_BUTTON_AFTER_TOMORROW,
    DAY_BUTTON_TODAY,
    DAY_BUTTON_TOMORROW,
    format_new_schedule_prefix,
    format_updated_schedule_prefix,
    DAY_QUESTION_TEXT,
    format_bind_group,
    format_group_add_welcome,
    format_header,
    format_pair_header,
    format_room,
    format_subject,
    format_teacher,
    PIN_BUTTON_TEXT,
)


load_dotenv()
router = Router()
STATE_PATH = Path("bot_state.json")


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {
            "chats": {},
            "last_schedule_file": None,
            "last_schedule_hash": None,
            "last_schedules_by_group": {},
        }
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    data.setdefault("chats", {})
    data.setdefault("last_schedule_file", None)
    data.setdefault("last_schedule_hash", None)
    data.setdefault("last_schedules_by_group", {})
    return data


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def save_chat_group(chat_id: int, group: str) -> None:
    state = load_state()
    chats = state.setdefault("chats", {})
    chats[str(chat_id)] = {"group": group, "notifications": True}
    save_state(state)


def get_chat_group(chat_id: int) -> str | None:
    state = load_state()
    chats = state.get("chats", {})
    cfg = chats.get(str(chat_id))
    if not cfg:
        return None
    group = cfg.get("group")
    return group


def toggle_chat_notifications(chat_id: int) -> tuple[bool, bool]:
    state = load_state()
    chats = state.setdefault("chats", {})
    cfg = chats.get(str(chat_id))
    if not cfg:
        return False, False
    current = cfg.get("notifications", True)
    new_value = not current
    cfg["notifications"] = new_value
    save_state(state)
    return True, new_value


def build_pin_keyboard() -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text=PIN_BUTTON_TEXT,
                    callback_data="pin_schedule",
                )
            ]
        ]
    )


def extract_group(text: str) -> str | None:
    match = re.search(r"(\d{2,4}\s*[а-яА-Яa-zA-Z]*)", text)
    if not match:
        return None
    return match.group(1).strip()


def format_schedule_text(group: str, payload: dict) -> str:
    schedule = payload.get("schedule") or []
    previous = payload.get("previous_schedule") or []
    if not schedule:
        return f"Для группы {group} ничего не найдено в последнем расписании."

    previous_by_pair = {
        str(item.get("pair", "")).strip(): item for item in previous
    }

    lines: list[str] = []
    lines.append(format_header(group))
    lines.append("")

    for item in schedule:
        pair = str(item.get("pair", "")).strip()
        time = str(item.get("time", "")).strip()
        subject = str(item.get("subject", "")).strip()
        teacher = str(item.get("teacher", "")).strip()
        room = str(item.get("room", "")).strip()

        if not subject and not teacher:
            continue

        old = previous_by_pair.get(pair)

        changed_time = False
        changed_subject = False
        changed_teacher = False
        changed_room = False

        if old:
            old_time = str(old.get("time", "")).strip()
            old_subject = str(old.get("subject", "")).strip()
            old_teacher = str(old.get("teacher", "")).strip()
            old_room = str(old.get("room", "")).strip()

            changed_time = old_time != time
            changed_subject = old_subject != subject
            changed_teacher = old_teacher != teacher
            changed_room = old_room != room

        header = format_pair_header(pair, time, changed_time)
        if header:
            lines.append(header)
        if subject:
            lines.append(format_subject(subject, changed_subject))
        if teacher:
            lines.append(format_teacher(teacher, changed_teacher))
        if room:
            lines.append(format_room(room, changed_room))
        lines.append("")

    return "\n".join(lines)


@router.message(CommandStart())
async def handle_start(message: types.Message) -> None:
    text = (
        "Бот активен.\n\n"
        "Для получения расписания отправь номер или название группы в личные сообщения, например:\n"
        "<code>158</code>\n\n"
        "В групповых чатах можно написать:\n"
        "<code>@rsphhw_bot 158</code>\n\n"
        "или использовать команду:\n"
        "<code>/list 158</code>"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("group"))
async def handle_group_command(message: types.Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Нужно указать группу. Пример: <code>/group 158</code>",
            parse_mode="HTML",
        )
        return
    group_text = parts[1].strip()
    group = extract_group(group_text)
    if not group:
        await message.answer(
            "Не удалось распознать номер группы. Пример: <code>/group 158</code>",
            parse_mode="HTML",
        )
        return
    save_chat_group(message.chat.id, group)
    await message.answer(
        format_bind_group(group),
        parse_mode="HTML",
    )


@router.message(Command("unsubscribe"))
async def handle_unsubscribe_command(message: types.Message) -> None:
    exists, enabled = toggle_chat_notifications(message.chat.id)
    if not exists:
        await message.answer(
            "Для этого чата ещё не привязана группа.",
            parse_mode="HTML",
        )
        return
    if enabled:
        await message.answer(
            "Уведомления о новых расписаниях для этого чата включены.",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            "Рассылка о новых расписаниях для этого чата отключена.",
            parse_mode="HTML",
        )


@router.message(Command("help"))
async def handle_help_command(message: types.Message) -> None:
    await message.answer(HELP_TEXT, parse_mode="HTML")


@router.message(Command("list"))
async def handle_list_command(message: types.Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) > 1:
        group = extract_group(parts[1].strip())
        if not group:
            await message.answer(
                "Не удалось распознать номер группы. Пример: <code>/list 158</code>",
                parse_mode="HTML",
            )
            return
        await send_schedule_for_group(message, group)
        return

    group = get_chat_group(message.chat.id)
    if not group:
        await message.answer(
            "Для этого чата ещё не привязана группа. Сначала выполните <code>/group 158</code>.",
            parse_mode="HTML",
        )
        return
    await send_schedule_for_group(message, group)


@router.message()
async def handle_plain_group(message: types.Message) -> None:
    text = (message.text or "").strip()
    if not text:
        return
    stripped = text.lstrip()
    if stripped.startswith("@"):
        group = extract_group(stripped)
        if group:
            save_chat_group(message.chat.id, group)
            await message.answer(format_bind_group(group), parse_mode="HTML")
            await send_schedule_for_group(message, group)
        return

    lower = text.lower()
    if lower.startswith("расписание"):
        rest = text[len("Расписание") :].strip()
        if rest:
            group = extract_group(rest)
            if not group:
                await message.answer(
                    "Не удалось распознать номер группы. Пример: <code>Расписание 158</code>",
                    parse_mode="HTML",
                )
                return
            await send_schedule_for_group(message, group)
            return

        group = get_chat_group(message.chat.id)
        if not group:
            await message.answer(
                "Для этого чата ещё не привязана группа. Сначала выполните <code>/group 158</code>.",
                parse_mode="HTML",
            )
            return
        await send_schedule_for_group(message, group)
        return

    group = extract_group(text)
    if not group:
        return
    await send_schedule_for_group(message, group)


@router.message(F.new_chat_members)
async def handle_bot_added_to_group(message: types.Message, bot: Bot) -> None:
    if not message.new_chat_members:
        return
    for member in message.new_chat_members:
        if member.id == bot.id:
            await message.answer(
                format_group_add_welcome(),
                parse_mode="HTML",
            )
            break


@router.my_chat_member()
async def handle_bot_status_change(event: types.ChatMemberUpdated, bot: Bot) -> None:
    old_status = event.old_chat_member.status
    new_status = event.new_chat_member.status
    if old_status in {"left", "kicked"} and new_status in {"member", "administrator"}:
        await bot.send_message(
            chat_id=event.chat.id,
            text=format_group_add_welcome(),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("day:"))
async def handle_day_choice(callback: types.CallbackQuery) -> None:
    data = callback.data or ""
    parts = data.split(":")
    if len(parts) != 3:
        await callback.answer()
        return
    _, offset_str, group = parts
    try:
        offset = int(offset_str)
    except ValueError:
        await callback.answer()
        return

    if not callback.message:
        await callback.answer()
        return

    try:
        payload = fetch_group_schedule_for_offset(group, offset)
    except Exception:
        await callback.message.edit_text(
            "Не удалось получить расписание:( Свяжитесь с администратором",
            parse_mode="HTML",
        )
        await callback.answer()
        return

    text = format_schedule_text(group, payload)
    keyboard = build_pin_keyboard()
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


async def send_schedule_for_group(message: types.Message, group: str) -> None:
    loading = await message.answer(
        f"Секунду. Расписание для группы {group}..", parse_mode="HTML"
    )
    try:
        days = get_near_schedule_days()
    except Exception:
        days = {}

    available_offsets = sorted(days.keys())

    if available_offsets and not (len(available_offsets) == 1 and available_offsets[0] == 0):
        buttons: list[list[types.InlineKeyboardButton]] = []
        row: list[types.InlineKeyboardButton] = []
        if 0 in days:
            row.append(
                types.InlineKeyboardButton(
                    text=f"{DAY_BUTTON_TODAY} ({days[0]})",
                    callback_data=f"day:0:{group}",
                )
            )
        if 1 in days:
            row.append(
                types.InlineKeyboardButton(
                    text=f"{DAY_BUTTON_TOMORROW} ({days[1]})",
                    callback_data=f"day:1:{group}",
                )
            )
        if row:
            buttons.append(row)
        row2: list[types.InlineKeyboardButton] = []
        if 2 in days:
            row2.append(
                types.InlineKeyboardButton(
                    text=f"{DAY_BUTTON_AFTER_TOMORROW} ({days[2]})",
                    callback_data=f"day:2:{group}",
                )
            )
        if row2:
            buttons.append(row2)

        keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
        await loading.edit_text(DAY_QUESTION_TEXT, reply_markup=keyboard, parse_mode="HTML")
        return

    try:
        if 0 in days:
            payload = fetch_group_schedule_for_offset(group, 0)
        else:
            payload = fetch_group_schedule(group)
    except Exception:
        await loading.edit_text(
            "Не удалось получить расписание:( Свяжитесь с администратором",
            parse_mode="HTML",
        )
        return

    text = format_schedule_text(group, payload)
    keyboard = build_pin_keyboard()
    await loading.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


async def schedule_watcher(bot: Bot) -> None:
    while True:
        try:
            state = load_state()
            html = fetch_page(STUDENTS_URL)
            links = find_schedule_links(html)
            if not links:
                await asyncio.sleep(300)
                continue

            link = select_daily_schedule_link(links)
            if not link:
                await asyncio.sleep(300)
                continue

            download_dir = Path("downloads")
            path = download_file(link, download_dir)
            content = path.read_bytes()
            file_hash = hashlib.sha256(content).hexdigest()

            last_file = state.get("last_schedule_file")
            last_hash = state.get("last_schedule_hash")

            is_new_file = file_hash != last_hash or path.name != last_file
            if not is_new_file:
                await asyncio.sleep(300)
                continue

            rows = read_excel_rows(path)
            if not rows:
                await asyncio.sleep(300)
                continue

            last_schedules_by_group = state.setdefault("last_schedules_by_group", {})
            chats = state.get("chats", {})

            for chat_id_str, cfg in chats.items():
                group = cfg.get("group")
                if not group:
                    continue
                if not cfg.get("notifications", True):
                    continue

                new_schedule = parse_schedule_for_group(rows, group)
                if not new_schedule:
                    continue

                old_schedule = last_schedules_by_group.get(group)
                payload = {"schedule": new_schedule}
                if old_schedule is not None:
                    payload["previous_schedule"] = old_schedule

                body = format_schedule_text(group, payload)

                schedule_date = extract_schedule_date(link)
                date_str = schedule_date.strftime("%d.%m") if schedule_date else None

                if old_schedule is None:
                    prefix = format_new_schedule_prefix(date_str)
                else:
                    prefix = format_updated_schedule_prefix(date_str)

                text = prefix + "\n\n" + body

                await bot.send_message(
                    chat_id=int(chat_id_str),
                    text=text,
                    parse_mode="HTML",
                    reply_markup=build_pin_keyboard(),
                )

                last_schedules_by_group[group] = new_schedule

            state["last_schedule_file"] = path.name
            state["last_schedule_hash"] = file_hash
            save_state(state)
        except Exception:
            pass

        await asyncio.sleep(300)


async def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Переменная окружения TELEGRAM_BOT_TOKEN не задана.")
        return

    bot = Bot(token=token, default=DefaultBotProperties(parse_mode="HTML"))
    dispatcher = Dispatcher()
    dispatcher.include_router(router)

    asyncio.create_task(schedule_watcher(bot))

    await dispatcher.start_polling(bot)


@router.callback_query(F.data == "pin_schedule")
async def handle_pin_schedule(callback: types.CallbackQuery, bot: Bot) -> None:
    if not callback.message:
        await callback.answer()
        return
    try:
        await bot.pin_chat_message(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
        )
        await callback.answer("Сообщение закреплено")
    except Exception:
        await callback.answer(
            "Не удалось закрепить. Нужны права на закрепление сообщений.",
            show_alert=True,
        )


if __name__ == "__main__":
    asyncio.run(main())
