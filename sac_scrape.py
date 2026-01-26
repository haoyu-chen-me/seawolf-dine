import json
import datetime
import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (SBU Student Project)"}

API_TEMPLATE = (
    "https://stonybrook.api.nutrislice.com/menu/api/weeks/school/{school}/menu-type/"
    "{menu_type}/{year}/{month}/{day}/?format=json"
)

FIXED_DATE = datetime.date(2026, 1, 27)

DAILY_SECTION_KEY = "Soups & Chili"


SAC_SECTIONS = [
    {"section": "Flame", "school": "sac", "menu_type": "flame"},
    {"section": "Corner Deli", "school": "sac", "menu_type": "deli"},
    {"section": "Seawolves Pizza", "school": "sac", "menu_type": "tuscan-bistro"},
    {"section": "Noodles", "school": "sac", "menu_type": "noodles"},

  
    {"section": "Soups & Chili", "school": "sac", "menu_type": "grab-n-go", "daily": True},

    {"section": "SAC Grill", "school": "sac", "menu_type": "grill"},
    {"section": "Wok Wok | Stir Fry", "school": "sac", "menu_type": "stiry-fry"},
    {"section": "Healthy by Nature", "school": "sac", "menu_type": "healthy-by-nature-2"},

    
    {"section": "Craft", "school": "sac-market", "menu_type": "rotisserie"},
]


def today_est_date() -> datetime.date:
    
    now_est = datetime.datetime.utcnow() - datetime.timedelta(hours=5)
    return now_est.date()


def now_est_str() -> str:
    now_est = datetime.datetime.utcnow() - datetime.timedelta(hours=5)
    return now_est.strftime("%Y-%m-%d %H:%M:%S EST")


def safe_food_name(mi: dict) -> str | None:
    food = mi.get("food") or {}
    name = food.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def detect_header_text(mi: dict) -> str | None:
    if mi.get("food"):
        return None

    for k in ("name", "text", "label", "description", "menu_item_name"):
        v = mi.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()

    title = (mi.get("category") or {}).get("name")
    if isinstance(title, str) and title.strip():
        return title.strip()

    return None


def pick_section_name(menu_item: dict, current_section: str | None) -> str:
    mc = menu_item.get("menu_category") or {}
    cat = menu_item.get("category") or {}
    sec = (
        mc.get("name")
        or cat.get("name")
        or menu_item.get("category_name")
        or menu_item.get("station")
        or "Other"
    )
    if sec == "Other" and current_section:
        sec = current_section
    return sec


def dedupe_preserve_order(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def flatten_section_map(section_map: dict[str, list[str]]) -> list[str]:
    merged: list[str] = []
    for _, names in section_map.items():
        merged.extend(names)
    return dedupe_preserve_order(merged)


def fetch_one(school: str, menu_type: str, date_obj: datetime.date) -> dict:
    url = API_TEMPLATE.format(
        school=school,
        menu_type=menu_type,
        year=date_obj.year,
        month=f"{date_obj.month:02d}",
        day=f"{date_obj.day:02d}",
    )
    date_str = date_obj.strftime("%Y-%m-%d")

    result = {
        "school": school,
        "menu_type": menu_type,
        "date": date_str,
        "source_url": url,
        "status": "ok",
        "message": "",
        "items": [],
    }

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
            result["status"] = "no_data_today"
            result["message"] = f"API data does not contain {date_str}."
            return result

        menu_items = day_block.get("menu_items") or []
        if not menu_items:
            result["status"] = "no_data_today"
            result["message"] = f"{date_str} menu_items empty."
            return result

        section_map: dict[str, list[str]] = {}
        current_section = None

        for mi in menu_items:
            header = detect_header_text(mi)
            if header:
                current_section = header
                continue

            name = safe_food_name(mi)
            if not name:
                continue

            sec = pick_section_name(mi, current_section)
            section_map.setdefault(sec, []).append(name)

        items = flatten_section_map(section_map)
        if not items:
            result["status"] = "no_data_today"
            result["message"] = "No food names parsed."
            return result

        result["items"] = items
        result["message"] = "Menu fetched."

    except Exception as e:
        result["status"] = "fetch_error"
        result["message"] = f"Error: {e}"

    return result


def main():
    out = {
        "location": "SAC",
        "timezone": "America/New_York",
        "updated_at": now_est_str(),
        "status": "ok",
        "sections": [],
    }

    any_error = False
    daily_date = today_est_date()

    for s in SAC_SECTIONS:
        use_date = daily_date if s.get("daily") else FIXED_DATE

        info = fetch_one(s["school"], s["menu_type"], use_date)

        menu_url = f"https://stonybrook.nutrislice.com/menu/{s['school']}/{s['menu_type']}/{use_date.strftime('%Y-%m-%d')}"

        sec_obj = {
            "section": s["section"],
            "school": s["school"],
            "slug": s["menu_type"],  
            "date": info.get("date"),
            "status": info["status"],
            "message": info["message"],
            "items": info.get("items", []),
            "menu_url": menu_url,
            "source_url": info.get("source_url"),
            "is_daily": bool(s.get("daily")),
        }

        out["sections"].append(sec_obj)
        if info["status"] != "ok":
            any_error = True

    if any_error:
        out["status"] = "partial_error"

    with open("sac.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print("Successfully wrote sac.json")


if __name__ == "__main__":
    main()
