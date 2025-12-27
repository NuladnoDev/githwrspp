from pathlib import Path
from datetime import date, datetime
import re

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from main import (
    STUDENTS_URL,
    download_file,
    fetch_page,
    find_schedule_links,
    read_excel_rows,
    parse_schedule_for_group,
)


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def select_daily_schedule_link(links: list[dict]) -> dict:
    for link in links:
        text = link.get("description", "").lower()
        if "уч год" in text:
            return link
    for link in links:
        text = link.get("description", "").lower()
        if "декабр" in text or "январ" in text:
            return link
    return links[-1] if links else None


def extract_schedule_date(link: dict) -> date | None:
    text = f"{link.get('filename', '')} {link.get('description', '')}"

    match = re.search(r"(\d{1,2})[.\-/](\d{1,2})", text)
    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        year = datetime.now().year
        try:
            return date(year, month, day)
        except ValueError:
            pass

    text_lower = text.lower()
    match = re.search(
        r"(\d{1,2})\s*(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)",
        text_lower,
    )
    if not match:
        return None

    day = int(match.group(1))
    month_name = match.group(2)

    months = {
        "января": 1,
        "февраля": 2,
        "марта": 3,
        "апреля": 4,
        "мая": 5,
        "июня": 6,
        "июля": 7,
        "августа": 8,
        "сентября": 9,
        "октября": 10,
        "ноября": 11,
        "декабря": 12,
    }

    month = months.get(month_name)
    if not month:
        return None

    year = datetime.now().year
    try:
        return date(year, month, day)
    except ValueError:
        return None


def get_near_schedule_links() -> dict[int, tuple[dict, date]]:
    html = fetch_page(STUDENTS_URL)
    links = find_schedule_links(html)
    today = date.today()
    result: dict[int, tuple[dict, date]] = {}
    for link in links:
        d = extract_schedule_date(link)
        if not d:
            continue
        offset = (d - today).days
        if 0 <= offset <= 2:
            result[offset] = (link, d)
    return result


def get_near_schedule_days() -> dict[int, str]:
    mapping = get_near_schedule_links()
    days: dict[int, str] = {}
    for offset, (_, d) in mapping.items():
        days[offset] = d.strftime("%d.%m")
    return days


def fetch_group_schedule(group: str) -> dict:
    html = fetch_page(STUDENTS_URL)
    links = find_schedule_links(html)
    if not links:
        raise HTTPException(status_code=500, detail="Не удалось найти файлы расписания")

    link = select_daily_schedule_link(links)
    if not link:
        raise HTTPException(
            status_code=500, detail="Не удалось выбрать файл расписания"
        )

    download_dir = Path("downloads")
    path = download_file(link, download_dir, force=False)
    rows = read_excel_rows(path)

    if not rows:
        raise HTTPException(
            status_code=500, detail="Файл расписания пуст или не распознан"
        )

    schedule = parse_schedule_for_group(rows, group)

    return {
        "group": group,
        "schedule": schedule,
        "file": path.name,
        "source": str(link.get("url")),
    }


def fetch_group_schedule_for_offset(group: str, offset: int) -> dict:
    mapping = get_near_schedule_links()
    entry = mapping.get(offset)
    if not entry:
        raise HTTPException(
            status_code=404, detail="Для выбранного дня расписание не найдено"
        )
    link, d = entry

    download_dir = Path("downloads")
    path = download_file(link, download_dir, force=False)
    rows = read_excel_rows(path)

    if not rows:
        raise HTTPException(
            status_code=500, detail="Файл расписания пуст или не распознан"
        )

    schedule = parse_schedule_for_group(rows, group)

    return {
        "group": group,
        "schedule": schedule,
        "file": path.name,
        "source": str(link.get("url")),
        "date": d.strftime("%d.%m"),
    }


@app.get("/api/schedule")
def get_schedule(group: str = Query(..., min_length=1)):
    return fetch_group_schedule(group)


@app.get("/api/schedule/by-offset")
def get_schedule_by_offset(
    group: str = Query(..., min_length=1),
    offset: int = Query(...),
):
    return fetch_group_schedule_for_offset(group, offset)
