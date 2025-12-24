from html import escape


HEADER_TEMPLATE = "✦ Расписание для группы <b>{group}:</b>"
NEW_SCHEDULE_PREFIX_TEMPLATE = "<b>Новое расписание ({date})</b>"
UPDATED_SCHEDULE_PREFIX_TEMPLATE = "<b>Изменения в расписании ({date})</b>"
BIND_GROUP_TEMPLATE = "Группа <b>{group}</b> привязана к этому чату."
PIN_BUTTON_TEXT = "Закрепить"
GROUP_ADD_WELCOME_LINE1 = "привяжи бота к группе, напиши @rsphhw_bot <номер группы>"
GROUP_ADD_WELCOME_LINE2 = "Например @rsphhw_bot 158"
HELP_TEXT = (
    "\n"
    "⌜Помощь по командам⌟ ✦\n\n"
    "❭ /unsubscribe — включить/отключить уведомления о <i>изменении</i> расписания\n\n"
    "❭ /group &lt;группа&gt; — привязать или сменить группу для <i>этого</i> чата\n⛶ <u>/group 158</u>\n\n"
    "❭ /list — показать расписание для привязанной группы\n\n"
    "❭ /list &lt;группа&gt; — показать расписание указанной группы\n⛶ <u>/list 160</u>\n"
)

DAY_QUESTION_TEXT = "Какой день?"
DAY_BUTTON_TODAY = "Сегодня"
DAY_BUTTON_TOMORROW = "Завтра"
DAY_BUTTON_AFTER_TOMORROW = "Послезавтра"

PAIR_NUMBERS = {
    "1": "Первая",
    "1.0": "Первая",
    "2": "Вторая",
    "2.0": "Вторая",
    "3": "Третья",
    "3.0": "Третья",
    "4": "Четвёртая",
    "4.0": "Четвёртая",
    "5": "Пятая",
    "5.0": "Пятая",
    "6": "Шестая",
    "6.0": "Шестая",
}


def format_header(group: str) -> str:
    return HEADER_TEMPLATE.format(group=escape(group))


def format_bind_group(group: str) -> str:
    return BIND_GROUP_TEMPLATE.format(group=escape(group))


def format_new_schedule_prefix(date_str: str | None) -> str:
    if date_str:
        return NEW_SCHEDULE_PREFIX_TEMPLATE.format(date=escape(date_str))
    return "<b>Новое расписание</b>"


def format_updated_schedule_prefix(date_str: str | None) -> str:
    if date_str:
        return UPDATED_SCHEDULE_PREFIX_TEMPLATE.format(date=escape(date_str))
    return "<b>Изменения в расписании</b>"


def format_pair_header(pair: str, time: str, changed: bool) -> str:
    name = PAIR_NUMBERS.get(pair, pair)
    parts: list[str] = []
    if name:
        parts.append(f"<b>{escape(name)} пара</b>")
    if time:
        parts.append(f"({escape(time)})")
    text = " ".join(parts) if parts else ""
    if changed and text:
        text = f"<i>{text}</i>"
    return text or ""


def format_subject(subject: str, changed: bool) -> str:
    text = f"🗒 {escape(subject)}"
    if changed:
        text = f"<i>{text}</i>"
    return text


def format_teacher(teacher: str, changed: bool) -> str:
    text = f"📎 {escape(teacher)}"
    if changed:
        text = f"<i>{text}</i>"
    return text


def format_room(room: str, changed: bool) -> str:
    if room.endswith(".0"):
        room = room[:-2]
    text = f"🍒 Ауд. {escape(room)}"
    if changed:
        text = f"<i>{text}</i>"
    return text


def strike(text: str) -> str:
    return f"<s>{escape(text)}</s>"


def format_group_add_welcome() -> str:
    line1 = escape(GROUP_ADD_WELCOME_LINE1)
    line2 = escape(GROUP_ADD_WELCOME_LINE2)
    return f"{line1}\n\n<i>{line2}</i>"
