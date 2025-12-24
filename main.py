import re
from pathlib import Path

import openpyxl
import requests
import urllib3
import xlrd
from bs4 import BeautifulSoup

# Отключаем предупреждения о небезопасном соединении (так как мы будем игнорировать проверку SSL)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


BASE_URL = "https://spo35-kaduienrgycol.gosuslugi.ru"
STUDENTS_URL = f"{BASE_URL}/studentam/"


def fetch_page(url: str) -> str:
    # Упрощаем до минимума, как было раньше
    response = requests.get(url, timeout=30, verify=False)
    response.raise_for_status()
    return response.text


def find_schedule_links(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")

    links: list[dict] = []

    for item in soup.select("div.gw-document-item"):
        download_link = item.select_one("a.gw-document-item__download-link[href]")
        if not download_link:
            continue

        href = download_link["href"]
        href_lower = href.lower()
        if ".xls" not in href_lower and ".xlsx" not in href_lower:
            continue

        title_element = item.select_one(".gw-document-item__overview")
        if title_element:
            description = title_element.get_text(" ", strip=True)
        else:
            description = download_link.get_text(" ", strip=True)

        filename_match = re.search(r"[^/]+$", href)
        filename = filename_match.group(0) if filename_match else "schedule.xls"

        absolute_url = href if href.startswith("http") else f"{BASE_URL}{href}"

        links.append(
            {
                "url": absolute_url,
                "filename": filename,
                "description": description or filename,
            }
        )

    if links:
        return links

    for a in soup.find_all("a", href=True):
        href = a["href"]
        href_lower = href.lower()
        if ".xls" not in href_lower and ".xlsx" not in href_lower:
            continue

        text = a.get_text(" ", strip=True)
        parts = [text]
        current = a
        for _ in range(3):
            parent = current.parent
            if not parent:
                break
            parent_text = parent.get_text(" ", strip=True)
            parts.append(parent_text)
            current = parent

        context_text = " ".join(dict.fromkeys(" ".join(parts).split()))

        filename_match = re.search(r"[^/]+$", href)
        filename = filename_match.group(0) if filename_match else "schedule.xls"

        absolute_url = href if href.startswith("http") else f"{BASE_URL}{href}"

        links.append(
            {
                "url": absolute_url,
                "filename": filename,
                "description": context_text or filename,
            }
        )

    return links


def choose_link(links: list[dict]) -> dict | None:
    if not links:
        return None

    print("Найдено файлов расписания:")
    for idx, info in enumerate(links, start=1):
        print(f"{idx}. {info['description']} -> {info['url']}")

    while True:
        raw = input(
            "\nВведите номер файла, который скачать (или пусто чтобы выйти): "
        ).strip()
        if not raw:
            return None
        if not raw.isdigit():
            print("Нужно ввести число.")
            continue

        index = int(raw)
        if not 1 <= index <= len(links):
            print("Нет файла с таким номером.")
            continue

        return links[index - 1]


def download_file(file_info: dict, target_dir: Path, force: bool = True) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / file_info["filename"]

    if not force and target_path.exists():
        print(f"\nФайл уже скачан, повторная загрузка не требуется: {target_path}")
        return target_path

    print(f"\nСкачиваю файл: {file_info['url']}")
    response = requests.get(file_info["url"], timeout=60, verify=False)
    response.raise_for_status()

    target_path.write_bytes(response.content)
    print(f"Файл сохранён в: {target_path}")

    return target_path


def read_excel_rows(path: Path) -> list[list[str]]:
    suffix = path.suffix.lower()
    rows: list[list[str]] = []

    if suffix in (".xlsx", ".xlsm"):
        workbook = openpyxl.load_workbook(path, data_only=True)
        sheet = workbook.active
        for row in sheet.iter_rows(values_only=True):
            rows.append(
                [str(cell).strip() if cell is not None else "" for cell in row]
            )
    elif suffix == ".xls":
        book = xlrd.open_workbook(str(path))
        sheet = book.sheet_by_index(0)
        for row_idx in range(sheet.nrows):
            row_values = sheet.row_values(row_idx)
            rows.append(
                [str(cell).strip() if cell is not None else "" for cell in row_values]
            )
    else:
        print("Неизвестное расширение файла, не могу прочитать.")

    return rows


def parse_schedule_for_group(rows: list[list[str]], group_query: str) -> list[dict]:
    group_query = group_query.lower().strip()

    def normalize_group(text: str) -> str:
        return re.sub(r"\s+", "", text.lower())

    def parse_pair_index(value: str) -> int | None:
        value = value.strip()
        if not value:
            return None
        match = re.match(r"^(\d+)(?:[.,]0+)?$", value)
        if not match:
            return None
        return int(match.group(1))

    target = normalize_group(group_query)

    group_col = -1
    group_row_idx = -1

    for r_idx, row in enumerate(rows):
        for c_idx, cell in enumerate(row):
            cell_clean = str(cell).strip()
            if not cell_clean:
                continue
            if normalize_group(cell_clean).startswith(target):
                group_col = c_idx
                group_row_idx = r_idx
                break
        if group_col != -1:
            break

    if group_col == -1:
        return []

    time_col = 3
    pair_col = 1

    schedule: list[dict] = []
    has_pairs = False
    r = group_row_idx + 1

    while r < len(rows):
        row = rows[r]

        if r > group_row_idx + 1:
            row_text = " ".join(row).lower()
            if "группа" in row_text:
                break

        if group_col >= len(row):
            r += 1
            continue

        subject = str(row[group_col]).strip()
        if not subject:
            r += 1
            continue

        pair_value = ""
        if pair_col < len(row):
            pair_value = str(row[pair_col]).strip()

        pair_index = parse_pair_index(pair_value)
        if pair_index is None:
            r += 1
            continue

        if has_pairs and pair_index == 1:
            break

        time_value = ""
        if time_col < len(row):
            time_value = str(row[time_col]).strip()

        room = ""
        room_col = group_col + 3
        for row_idx in (r, r + 1):
            if row_idx < len(rows) and room_col < len(rows[row_idx]):
                candidate = str(rows[row_idx][room_col]).strip()
                if candidate:
                    room = candidate
                    break

        teacher = ""
        if r + 1 < len(rows) and group_col < len(rows[r + 1]):
            teacher = str(rows[r + 1][group_col]).strip()

        schedule.append(
            {
                "pair": pair_value,
                "time": time_value,
                "subject": subject,
                "teacher": teacher,
                "room": room,
            }
        )

        has_pairs = True
        r += 2

    return schedule


def main() -> None:
    print("Загружаю страницу студентов...")
    html = fetch_page(STUDENTS_URL)

    links = find_schedule_links(html)
    if not links:
        print("Не удалось найти ссылки на файлы расписания (.xls/.xlsx).")
        return

    chosen = choose_link(links)
    if not chosen:
        print("Файл не выбран, выходим.")
        return

    download_dir = Path("downloads")
    downloaded_path = download_file(chosen, download_dir)

    group_query = input(
        "\nВведите номер или название группы (например, 158): "
    ).strip()
    if not group_query:
        print("Группа не указана.")
        return

    print_group_schedule(downloaded_path, group_query)


if __name__ == "__main__":
    import os

    if os.environ.get("RUN_SCHEDULE_CLI") == "1":
        main()
