import requests
import json
import datetime
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# --- Configuration ---

TARGET_URL_TEMPLATE = (
    "https://stonybrook.api.nutrislice.com/menu/api/weeks/school/east-side-dining/menu-type/"
    "todays-dine-in-specials-esd/{year}/{month}/{day}/?format=json"
)

HEADERS = {"User-Agent": "Mozilla/5.0 (SBU Student Project)"}

# 关键字匹配餐段 (正则忽略大小写)
MEAL_KEYWORDS = [
    ("late_night", re.compile(r"\blate\s*night\b", re.I)),
    ("breakfast", re.compile(r"\bbreakfast\b", re.I)),
    ("lunch", re.compile(r"\blunch\b", re.I)),
    ("dinner", re.compile(r"\bdinner\b", re.I)),
]

# Pizza 和 Pasta 既然全天都有，需要特殊处理
PIZZA_SECTION_RE = re.compile(r"\bpizza\b", re.I)
PASTA_SECTION_RE = re.compile(r"\bpasta\b", re.I)

# 周末合并逻辑：把 Late Night 的 Grill 归入 Dinner
LATE_NIGHT_SOURCE_SECTION = "Late Night Specials"
LATE_NIGHT_TARGET_SECTION = "Grill Dinner Specials"


# --- Helper Functions ---

def _ny_tz():
    try:
        return ZoneInfo("America/New_York")
    except ZoneInfoNotFoundError as e:
        raise RuntimeError(
            "Missing timezone data for America/New_York.\n"
            "Fix (Windows 本地最常见): python -m pip install tzdata\n"
            "Then rerun."
        ) from e

NY_TZ = _ny_tz()

def ny_now() -> datetime.datetime:
    return datetime.datetime.now(NY_TZ)

def pick_section_name(menu_item: dict) -> str:
    """尝试从多个字段中提取档口/区域名称"""
    mc = menu_item.get("menu_category") or {}
    cat = menu_item.get("category") or {}
    return (
        mc.get("name")
        or cat.get("name")
        or menu_item.get("category_name")
        or menu_item.get("station")
        or "Other"
    )

def safe_food_name(mi: dict) -> str | None:
    food = mi.get("food") or {}
    name = food.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None

def detect_header_text(mi: dict) -> str | None:
    """检测是否是纯文本标题而非菜品"""
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

def guess_meal_from_section(section_name: str) -> str:
    """根据档口名猜测属于哪个餐段 (e.g. 'Grill Lunch' -> lunch)"""
    for meal, pat in MEAL_KEYWORDS:
        if pat.search(section_name or ""):
            return meal
    return "dinner" # 默认 fallback

def is_pizza_or_pasta_section(section_name: str) -> bool:
    s = section_name or ""
    return bool(PIZZA_SECTION_RE.search(s) or PASTA_SECTION_RE.search(s))

def add_name(meals_map: dict, meal: str, section: str, food_name: str):
    meals_map.setdefault(meal, {})
    meals_map[meal].setdefault(section, [])
    meals_map[meal][section].append(food_name)

def dedupe_preserve_order(names: list[str]) -> list[str]:
    seen = set()
    out = []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out

def meals_map_to_output(meals_map: dict, meal_order: list[str]) -> dict:
    out = {}
    for meal in meal_order:
        sections = meals_map.get(meal, {})
        blocks = []
        for sec, names in sections.items():
            blocks.append({"section": sec, "items": dedupe_preserve_order(names)})
        # 按档口名排序，保持整洁
        blocks.sort(key=lambda x: (x["section"] or "").lower())
        out[meal] = blocks
    return out

def merge_blocks(blocks: list[dict]) -> list[dict]:
    """合并同名 Section 的菜品列表"""
    sec_map: dict[str, list[str]] = {}
    for b in blocks:
        s = b.get("section") or "Other"
        sec_map.setdefault(s, []).extend(b.get("items") or [])
    
    merged = [{"section": s, "items": dedupe_preserve_order(items)} for s, items in sec_map.items()]
    merged.sort(key=lambda x: (x["section"] or "").lower())
    return merged

def weekend_merge_brunch_dinner(base: dict) -> dict:
    """
    周末特殊逻辑：
    Brunch = Breakfast + Lunch
    Dinner = Dinner + Late Night (重命名 Late Night Grill -> Grill Dinner)
    """
    # 1. Brunch
    brunch_blocks = []
    brunch_blocks.extend(base.get("breakfast", []))
    brunch_blocks.extend(base.get("lunch", []))
    brunch_blocks.extend(base.get("brunch", []))
    brunch = merge_blocks(brunch_blocks)

    # 2. Dinner
    dinner_blocks = list(base.get("dinner", []))
    
    # 将 Late Night 内容并入 Dinner
    for b in base.get("late_night", []):
        sec = b.get("section") or "Other"
        items = b.get("items") or []
        
        # 特殊逻辑：把 "Late Night Specials" (实际上是 Grill) 改名为 "Grill Dinner Specials"
        # 这样前端过滤 Dinner 时能把这些 Grill 菜品选出来
        if sec == LATE_NIGHT_SOURCE_SECTION:
            dinner_blocks.append({"section": LATE_NIGHT_TARGET_SECTION, "items": items})
        else:
            dinner_blocks.append(b)

    dinner = merge_blocks(dinner_blocks)
    
    return {"brunch": brunch, "dinner": dinner}


# --- Main Logic ---

def fetch_east_dining_menu():
    now = ny_now()
    date_str = now.strftime("%Y-%m-%d")
    is_weekend = now.weekday() >= 5  # Saturday=5, Sunday=6

    url = TARGET_URL_TEMPLATE.format(
        year=now.year,
        month=f"{now.month:02d}",
        day=f"{now.day:02d}",
    )
    print(f"Fetching from: {url}")

    status = "ok"
    message = ""
    meals_map = {}
    found_today = False

    try:
        response = requests.get(url, headers=HEADERS, timeout=25)
        response.raise_for_status()
        data = response.json()

        todays_items = []
        for day_data in data.get("days", []):
            if day_data.get("date") == date_str:
                found_today = True
                todays_items = day_data.get("menu_items", [])
                print(f"Found date {date_str} with {len(todays_items)} items.")
                break

        if not found_today or not todays_items:
            status = "no_data_today"
            message = f"API data does not contain {date_str} (or empty)."
            print(message)
        else:
            current_section = None

            for mi in todays_items:
                # 1. 检查是否是 Section Header (Nutrislice 经常把标题作为 item 返回)
                header = detect_header_text(mi)
                if header:
                    current_section = header
                    continue

                # 2. 获取菜名
                food_name = safe_food_name(mi)
                if not food_name:
                    continue

                # 3. 确定 Section 名称
                section = pick_section_name(mi)
                if section == "Other" and current_section:
                    section = current_section

                # 4. Pizza 和 Pasta 分发逻辑 (全天供应)
                if is_pizza_or_pasta_section(section):
                    if is_weekend:
                        add_name(meals_map, "brunch", section, food_name)
                        add_name(meals_map, "dinner", section, food_name)
                    else:
                        add_name(meals_map, "lunch", section, food_name)
                        add_name(meals_map, "dinner", section, food_name)
                        add_name(meals_map, "late_night", section, food_name)
                    continue

                # 5. 普通逻辑：根据 Section 名字猜测餐段
                meal = guess_meal_from_section(section)
                add_name(meals_map, meal, section, food_name)

            status = "ok"
            message = "Menu fetched and categorized."
            print(message)

    except Exception as e:
        status = "fetch_error"
        message = f"Error fetching menu: {e}"
        print(message)
        import traceback
        traceback.print_exc()

    # 生成最终输出结构
    if is_weekend:
        base = meals_map_to_output(meals_map, ["breakfast", "lunch", "dinner", "late_night", "brunch"])
        meals_out = weekend_merge_brunch_dinner(base)
    else:
        meals_out = meals_map_to_output(meals_map, ["breakfast", "lunch", "dinner", "late_night"])

    output = {
        "date": date_str,
        "location": "East Side Dining (Dine-in Specials)",
        "is_weekend": is_weekend,
        "status": status,
        "message": message,
        "updated_at": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "timezone": "America/New_York",
        "meals": meals_out,
        "source_url": url,
    }

    # 写入文件
    filename = "east_dining.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Successfully updated {filename}!")

if __name__ == "__main__":
    fetch_east_dining_menu()