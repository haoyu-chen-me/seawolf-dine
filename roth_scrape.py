import json
import datetime
import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (SBU Student Project)"}

# Roth 在 Nutrislice / API 里的 school slug（如果跑出来 no_data_today，就改这里）
SCHOOL_SLUG = "roth-cafe"

API_TEMPLATE = (
    "https://stonybrook.api.nutrislice.com/menu/api/weeks/school/{school}/menu-type/"
    "{slug}/{year}/{month}/{day}/?format=json"
)

# ✅ 因为 1/25、1/26 关门，所以固定抓 1/27
FIXED_DATE = datetime.date(2026, 1, 27)

# Roth 4 个档口
# - Smash / Savor 抓菜单（你说菜单不变，抓一次即可）
# - Subway / Popeyes 连锁：不抓菜单，只给一句提示，点击跳官网
ROTH_SECTIONS = [
    {
        "section": "Subway",
        "type": "chain",
        "slug": None,
        "items": ["Click to view the official menu"],
        "menu_url": "https://www.subway.com/en-us/menu",
    },
    {
        "section": "Smash n' Shake",
        "type": "static",
        "slug": "smash-n-shake",
        "menu_url": f"https://stonybrook.nutrislice.com/menu/roth-cafe/smash-n-shake/{FIXED_DATE.strftime('%Y-%m-%d')}",
    },
    {
        "section": "Savor",
        "type": "static",
        "slug": "chef-jet",
        "menu_url": f"https://stonybrook.nutrislice.com/menu/roth-cafe/chef-jet/{FIXED_DATE.strftime('%Y-%m-%d')}",
    },
    {
        "section": "Popeyes",
        "type": "chain",
        "slug": None,
        "items": ["Click to view the official menu"],
        "menu_url": "https://www.popeyes.com/menu",
    },
]


def safe_food_name(mi: dict) -> str | None:
    food = mi.get("food") or {}
    name = food.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def detect_header_text(mi: dict) -> str | None:
    # Nutrislice 有时把 section 标题作为“没有 food 的条目”塞进 menu_items
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


def flatten_blocks(section_map: dict[str, list[str]]) -> list[str]:
    # Roth：一个档口一个 section，这里把 Nutrislice 的多个 category/station 合并成一个 items 列表
    merged: list[str] = []
    for _, names in section_map.items():
        merged.extend(names)
    return dedupe_preserve_order(merged)


def fetch_static_menu(slug: str, date_obj: datetime.date) -> dict:
    url = API_TEMPLATE.format(
        school=SCHOOL_SLUG,
        slug=slug,
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
                "items": [],
            }

        menu_items = day_block.get("menu_items") or []
        if not menu_items:
            return {
                "status": "no_data_today",
                "message": f"{date_str} menu_items empty",
                "source_url": url,
                "items": [],
            }

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

        items = flatten_blocks(section_map)
        if not items:
            return {
                "status": "no_data_today",
                "message": "No food names parsed",
                "source_url": url,
                "items": [],
            }

        return {"status": "ok", "message": "Menu fetched.", "source_url": url, "items": items}

    except Exception as e:
        return {"status": "fetch_error", "message": f"Error: {e}", "source_url": url, "items": []}


def main():
    # 近似 EST（够用）；你前面其他脚本也是这么处理的风格
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-5)))
    updated_at = now.strftime("%Y-%m-%d %H:%M EST")

    out = {
        "location": "Roth Cafe",
        "date_fetched_from": FIXED_DATE.strftime("%Y-%m-%d"),
        "timezone": "America/New_York",
        "updated_at": updated_at,
        "status": "ok",
        "sections": [],
    }

    any_error = False

    for sec in ROTH_SECTIONS:
        entry = {
            "section": sec["section"],
            "type": sec["type"],
            "menu_url": sec["menu_url"],
            "items": sec.get("items", []),
            "status": "ok",
            "message": "",
        }

        if sec["type"] == "static":
            slug = sec["slug"]
            fetched = fetch_static_menu(slug, FIXED_DATE)
            entry["status"] = fetched["status"]
            entry["message"] = fetched["message"]
            entry["source_url"] = fetched["source_url"]
            entry["items"] = fetched["items"]

            if entry["status"] != "ok":
                any_error = True

        out["sections"].append(entry)

    if any_error:
        out["status"] = "partial_error"

    with open("roth.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print("Successfully wrote roth.json")


if __name__ == "__main__":
    main()
