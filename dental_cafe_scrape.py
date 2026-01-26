import json
import datetime
from typing import Any, Dict, List, Optional

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (SBU Student Project)",
    "Accept": "application/json",
}

API_TEMPLATE = (
    "https://stonybrook.api.nutrislice.com/menu/api/weeks/school/sbu-eats-events/"
    "menu-type/dental-cafe/{year}/{month}/{day}/?format=json"
)


def eastern_now() -> datetime.datetime:
    return datetime.datetime.utcnow() - datetime.timedelta(hours=5)


def safe_food_name(mi: Dict[str, Any]) -> Optional[str]:
    food = mi.get("food") or {}
    if isinstance(food, dict):
        name = food.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def is_header_item(mi: Dict[str, Any]) -> bool:
    if mi.get("food"):
        return False
    return bool(mi.get("is_section_title") or mi.get("is_station_header"))


def header_text(mi: Dict[str, Any]) -> Optional[str]:
    for k in ("text", "name", "label", "description", "menu_item_name"):
        v = mi.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def pick_section_name(mi: Dict[str, Any], current_section: Optional[str]) -> str:
    mc = mi.get("menu_category")
    cat = mi.get("category")

    mc_name = mc.get("name") if isinstance(mc, dict) else None
    cat_name = cat.get("name") if isinstance(cat, dict) else None

    sec = (
        mc_name
        or cat_name
        or mi.get("category_name")
        or mi.get("station")
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


def fetch_daily_menu(date_obj: datetime.date) -> Dict[str, Any]:
    url = API_TEMPLATE.format(
        year=date_obj.year,
        month=f"{date_obj.month:02d}",
        day=f"{date_obj.day:02d}",
    )
    date_str = date_obj.strftime("%Y-%m-%d")

    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        r.raise_for_status()
        data = r.json()

        day_block = None
        for d in data.get("days", []):
            if d.get("date") == date_str:
                day_block = d
                break

        if not day_block:
            return {
                "status": "no_data_today",
                "message": f"API missing {date_str}",
                "source_url": url,
                "sections": [],
            }

        menu_items = day_block.get("menu_items") or []
        if not menu_items:
            return {
                "status": "no_data_today",
                "message": f"{date_str} menu_items empty",
                "source_url": url,
                "sections": [],
            }

        if (
            len(menu_items) == 1
            and isinstance(menu_items[0], dict)
            and menu_items[0].get("is_holiday")
            and isinstance(menu_items[0].get("text"), str)
        ):
            return {
                "status": "closed",
                "message": menu_items[0].get("text").strip(),
                "source_url": url,
                "sections": [],
            }

        section_map: Dict[str, List[str]] = {}
        current_section: Optional[str] = None

        for mi in menu_items:
            if not isinstance(mi, dict):
                continue

            if is_header_item(mi):
                ht = header_text(mi)
                if ht:
                    current_section = ht
                continue

            name = safe_food_name(mi)
            if not name:
                continue

            sec = pick_section_name(mi, current_section)
            section_map.setdefault(sec, []).append(name)

        sections_out: List[Dict[str, Any]] = []
        for sec_name, items in section_map.items():
            items2 = dedupe_preserve_order(items)
            if items2:
                sections_out.append({"section": sec_name, "items": items2})

        if not sections_out:
            return {
                "status": "no_data_today",
                "message": "No food names parsed",
                "source_url": url,
                "sections": [],
            }

        return {
            "status": "ok",
            "message": "Menu fetched.",
            "source_url": url,
            "sections": sections_out,
        }

    except Exception as e:
        return {
            "status": "fetch_error",
            "message": f"Error: {e}",
            "source_url": url,
            "sections": [],
        }


def main() -> None:
    now_eastern = eastern_now()
    today = now_eastern.date()

    fetched = fetch_daily_menu(today)

    out: Dict[str, Any] = {
        "location": "Dental Café",
        "date": today.strftime("%Y-%m-%d"),
        "timezone": "America/New_York",
        "updated_at": now_eastern.strftime("%Y-%m-%d %H:%M:%S EST"),
        "status": fetched["status"],
        "message": fetched["message"],
        "source_url": fetched["source_url"],
        "sections": fetched["sections"],
        "menu_url": f"https://stonybrook.nutrislice.com/menu/sbu-eats-events/dental-cafe/{today.strftime('%Y-%m-%d')}",
    }

    with open("dental_cafe.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print("Successfully wrote dental_cafe.json")


if __name__ == "__main__":
    main()
