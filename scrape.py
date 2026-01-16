import requests
import json
import datetime

#爬取dental 的网站
TARGET_URL_TEMPLATE = "https://stonybrook.api.nutrislice.com/menu/api/weeks/school/sbu-eats-events/menu-type/dental-cafe/{year}/{month}/{day}/?format=json"

def fetch_dental_cafe_menu():
    
    # 日期美东
    today = datetime.datetime.utcnow() - datetime.timedelta(hours=5)
    
    #填充个位日期
    url = TARGET_URL_TEMPLATE.format(
        year=today.year,
        month=f"{today.month:02d}",
        day=f"{today.day:02d}"
    )

    print(f"开始运行了： {url}")
    
    headers = {"User-Agent": "Mozilla/5.0 (SBU Student Project)"}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        todays_menu = []
        date_str = today.strftime("%Y-%m-%d")
        
        found_today = False

        #找到今天
        for day_data in data.get('days', []):
            if day_data.get('date') == date_str:
                found_today = True
                menu_items = day_data.get('menu_items', [])
                
                print(f"找到日期 {date_str}，共有 {len(menu_items)} 数据。")

                for item in menu_items:
                    food_obj = item.get('food')
                    
                    if food_obj is None:
                        continue 

                    food_name = food_obj.get('name', 'Unknown Name')
                    price = item.get('price', '')

                    todays_menu.append({
                        "name": food_name,
                        "price": price,
                    })
                break 

        #今天没数据？
        if not found_today:
            print(f"API 数据里没有 {date_str} 这一天。")
        else:
            print(f"有效菜品: {len(todays_menu)} 个。")

        # 写入jsonn文件
        output = {
            "date": date_str,
            "location": "Dental Cafe",
            "menu": todays_menu,
            "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        with open('dental_cafe.json', 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=4, ensure_ascii=False)

    except Exception as e:
        print(f"严重错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    fetch_dental_cafe_menu()