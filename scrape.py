import requests
import json
import datetime

# Scrape Dental Cafe menu via Nutrislice API
TARGET_URL_TEMPLATE = (
    "https://stonybrook.api.nutrislice.com/menu/api/weeks/school/sbu-eats-events/menu-type/"
    "dental-cafe/{year}/{month}/{day}/?format=json"
)


def fetch_dental_cafe_menu():
    # Get today's date in Eastern Time (fixed UTC-5 as in your original code)
    eastern_time = datetime.datetime.utcnow() - datetime.timedelta(hours=5)

    date_str = eastern_time.strftime("%Y-%m-%d")
    is_weekend = eastern_time.weekday() >= 5  # 5=Sat, 6=Sun

    # Format URL with zero-padded dates
    url = TARGET_URL_TEMPLATE.format(
        year=eastern_time.year,
        month=f"{eastern_time.month:02d}",
        day=f"{eastern_time.day:02d}",
    )
    print(f"Fetching from: {url}")

    headers = {"User-Agent": "Mozilla/5.0 (SBU Student Project)"}

    todays_menu = []
    found_today = False
    status = "ok"
    message = ""

    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        data = response.json()

        # Find today's menu inside the returned week payload
        for day_data in data.get("days", []):
            if day_data.get("date") == date_str:
                found_today = True
                menu_items = day_data.get("menu_items", [])
                print(f"Found date {date_str} with {len(menu_items)} items.")

                for item in menu_items:
                    food_obj = item.get("food")
                    if not food_obj:
                        continue

                    todays_menu.append(
                        {
                            "name": food_obj.get("name", "Unknown Name"),
                            "price": item.get("price", ""),
                        }
                    )
                break

        # Decide what message/status to surface (this is what you will read later)
        if is_weekend and (not found_today or len(todays_menu) == 0):
            status = "weekend_no_menu"
            message = f"happyweekends - No menu posted for {date_str}."
        elif not found_today:
            status = "no_data_today"
            message = f"API data does not contain {date_str}."
        else:
            status = "ok"
            message = f"Valid menu items: {len(todays_menu)}."

        print(message)

    except Exception as e:
        # Still write a JSON file so downstream code has something consistent to read
        status = "fetch_error"
        message = f"Error fetching menu: {e}"
        print(message)
        import traceback

        traceback.print_exc()

    # Always write output JSON so other code can reference status/message
    output = {
        "date": date_str,
        "location": "Dental Cafe",
        "menu": todays_menu,
        "status": status,
        "message": message,
        "updated_at": eastern_time.strftime("%Y-%m-%d %H:%M:%S EST"),
    }

    with open("dental_cafe.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=4, ensure_ascii=False)

    print(f"Successfully updated dental_cafe.json with {len(todays_menu)} items!")


if __name__ == "__main__":
    fetch_dental_cafe_menu()
