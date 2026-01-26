import json
import datetime
from typing import Any, Dict, List, Optional

import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (SBU Student Project)", "Accept": "application/json"}

API_TEMPLATE = (
    "https://stonybrook.api.nutrislice.com/menu/api/weeks/school/jasmine/menu-type/"
    "{slug}/{year}/{month}/{day}/?format=json"
)

FIXED_MENU_DATE = datetime.date(2026, 1, 27)

JASMINE_HOURS = {
    "mon_thu": "11am to 8pm",
    "fri": "11am to 8pm",
    "sat": "12pm to 7pm",
    "sun": "12pm to 7pm",
}

CURRY_HOURS = {
    "mon_thu": "11am to 8pm",
    "fri": "11am to 8pm",
    "sat": "Closed",
    "sun": "Closed",
}

STALLS = [
    {"name": "Cafetasia Chinese", "slug": "cafetasia-chinese", "daily": False},
    {"name": "Curry Kitchen", "slug": "curry-kitchen", "daily": True},  # daily
    {"name": "Cafetasia Korean", "slug": "cafetasia-korean", "daily": False},
    {"name": "Sushido", "slug": "sushido", "daily": False},
]


def eastern_now() -> datetime.datetime:
    return datetime.datetime.utcnow() - datetime.timedelta(hours=5)


def weekday_key(d: datetime.date) -> str:
    wd = d.weekday()  
    if wd <= 3:
        return "mon_thu"
    if wd == 4:
        return "fri"
    if wd == 5:
        return "sat"
    return "sun"


def safe_food_name(mi: Dict[str, Any]) -> Optional[str]:
    food = mi.get("food") or {}
    if isinstance(food, dict):
        name = food.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def detect_header_text(mi: Dict[str, Any]) -> Optional[str]:
    if mi.get("food"):
        return None

    for k in ("name", "text", "label", "description", "menu_item_name"):
        v = mi.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()

    cat = mi.get("category") or {}
    if isinstance(cat, dict):
        title = cat.get("name")
        if isinstance(title, str) and title.strip():
            return title.strip()

    return None


def pick_section_name(menu_item: Dict[str, Any], current_section: Optional[str]) -> str:
    mc = menu_item.get("menu_category")
    cat = menu_item.get("category")

    mc_name = mc.get("name") if isinstance(mc, dict) else None
    cat_name = cat.get("name") if isinstance(cat, dict) else None

    sec = (
        mc_name
        or cat_name
        or menu_item.get("category_name")
        or menu_item.get("station")
        or "Other"
    )

    if (not sec or sec == "Other") and current_section:
        sec = current_section

    if not isinstance(sec, str) or not sec.strip():
        return current_section or "Other"

    return sec.strip()


def dedupe_preserve_order(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def fetch_flat_items(slug: str, date_obj: datetime.date) -> List[str]:
    url = API_TEMPLATE.format(
        slug=slug,
        year=date_obj.year,
        month=f"{date_obj.month:02d}",
        day=f"{date_obj.day:02d}",
    )

    r = requests.get(url, headers=HEADERS, timeout=25)
    r.raise_for_status()
    data = r.json()

    date_str = date_obj.strftime("%Y-%m-%d")
    day_block = None
    for d in data.get("days", []):
        if d.get("date") == date_str:
            day_block = d
            break

    if not day_block:
        return []

    menu_items = day_block.get("menu_items") or []
    if not menu_items:
        return []

    section_map: Dict[str, List[str]] = {}
    current_section: Optional[str] = None

    for mi in menu_items:
        if not isinstance(mi, dict):
            continue

        header = detect_header_text(mi)
        if header:
            current_section = header
            continue

        name = safe_food_name(mi)
        if not name:
            continue

        sec = pick_section_name(mi, current_section)
        section_map.setdefault(sec, []).append(name)

    flat: List[str] = []
    for sec in section_map:
        flat.extend(section_map[sec])

    return dedupe_preserve_order(flat)


def stall_hours_today(stall_name: str, today_key: str) -> str:
    if stall_name.strip().lower() == "curry kitchen":
        return CURRY_HOURS[today_key]
    return JASMINE_HOURS[today_key]


def main() -> None:
    now_eastern = eastern_now()
    today = now_eastern.date()
    today_key = weekday_key(today)

    out: Dict[str, Any] = {
        "date": today.strftime("%Y-%m-%d"),
        "location": "Jasmine",
        "hours_today": JASMINE_HOURS[today_key],
        "fixed_menu_date_for_non_daily": FIXED_MENU_DATE.strftime("%Y-%m-%d"),
        "updated_at": now_eastern.strftime("%Y-%m-%d %H:%M:%S EST"),
        "timezone": "America/New_York",
        "sections": [],
    }

    for s in STALLS:
        name = s["name"]
        slug = s["slug"]
        is_daily = bool(s.get("daily"))

        fetch_date = today if is_daily else FIXED_MENU_DATE

        hours_today = stall_hours_today(name, today_key)

        if name.strip().lower() == "curry kitchen" and hours_today == "Closed":
            items: List[str] = []
        else:
            try:
                items = fetch_flat_items(slug, fetch_date)
            except Exception:
                items = []

        out["sections"].append(
            {
                "section": name,
                "hours_today": hours_today,
                "menu_date": fetch_date.strftime("%Y-%m-%d"),
                "items": items,
                "menu_url": f"https://stonybrook.nutrislice.com/menu/jasmine/{slug}/{fetch_date.strftime('%Y-%m-%d')}",
            }
        )

    with open("jasmine.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print("Successfully wrote jasmine.json")


if __name__ == "__main__":
    main()
