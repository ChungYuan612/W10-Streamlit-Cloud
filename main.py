# main.py

import requests
import json
import os
from flask import Flask, render_template_string

app = Flask(__name__)

# --- 設定 CWA API 資訊 ---
# ⚠️ 部署到 Cloud Run 時，請通過環境變數傳遞金鑰，以確保安全
# 示例： export CWA_API_KEY="YOUR_ACTUAL_API_KEY"
API_URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-D0047-091?Authorization=CWA-FD731281-945E-4A82-83B3-A29D9938B48C&format=JSON&LocationName=%E9%9B%B2%E6%9E%97%E7%B8%A3"

# --- 天氣資料抓取函式 (改寫自您的步驟 1) ---

def fetch_weather_data(url):
    """
    抓取 CWA API 的 JSON 天氣資料並提取指定地點的預報。
    """

    try:
        response = requests.get(url)
        response.raise_for_status() # 對於 4xx 或 5xx 錯誤拋出異常
        data = response.json()
        
        # 檢查 API 回應是否成功
        if data.get('success') != 'true':
            return None, f"API 回應失敗: {data}"

        # 解析資料結構
        records = data.get('records', {})
        locations = records.get('Locations', [])
        
        target_location_data = None
        for loc in locations:
            for loc_detail in loc.get('Location', []):
                
                target_location_data = loc_detail
                break
            if target_location_data:
                break
                
        if not target_location_data:
            return None, f"找不到地點"

        # 格式化預報資料 (將分散的元素按時間段合併)
        time_data = {}
        for element in target_location_data.get('WeatherElement', []):
            element_name = element.get('ElementName')
            for time_period in element.get('Time', []):
                start_time = time_period.get('StartTime')
                end_time = time_period.get('EndTime')
                key = (start_time, end_time)
                
                if key not in time_data:
                    time_data[key] = {'StartTime': start_time, 'EndTime': end_time}
                
                element_value = time_period.get('ElementValue', [{}])[0]
                
                if element_name == '天氣預報綜合描述':
                    time_data[key]['WeatherDescription'] = element_value.get('WeatherDescription')
                elif element_name == '最高溫度':
                    time_data[key]['MaxTemperature'] = element_value.get('MaxTemperature')
                elif element_name == '最低溫度':
                    time_data[key]['MinTemperature'] = element_value.get('MinTemperature')
                elif element_name == '12小時降雨機率':
                    time_data[key]['PoP12h'] = element_value.get('ProbabilityOfPrecipitation')

        # 排序並輸出列表
        forecasts = [time_data[key] for key in sorted(time_data.keys())]
        
        return forecasts, None

    except requests.exceptions.RequestException as e:
        return None, f"網路請求錯誤: {e}"
    except Exception as e:
        # 捕捉解析或結構錯誤
        return None, f"發生資料處理錯誤: {e}"


# --- Flask 路由和網頁顯示 ---

@app.route('/')
def weather_display():
    """
    主頁面路由，抓取並顯示天氣預報。
    """
    forecasts, error = fetch_weather_data(API_URL)
    
    if error:
        # 如果有錯誤，顯示錯誤訊息
        html_content = f"""
        <html>
        <head><title> 天氣預報</title></head>
        <body>
            <h1>⛈️ 天氣資料載入失敗</h1>
            <p style="color: red;">{error}</p>
        </body>
        </html>
        """
    else:
        # 如果成功，生成表格 HTML
        table_rows = ""
        for item in forecasts:
            # 簡化時間顯示
            start_time = item.get('StartTime', 'N/A')[5:16].replace('T', ' ')
            end_time = item.get('EndTime', 'N/A')[5:16].replace('T', ' ')
            
            table_rows += f"""
            <tr>
                <td>{start_time} - {end_time}</td>
                <td>{item.get('MaxTemperature', 'N/A')} / {item.get('MinTemperature', 'N/A')} °C</td>
                <td>{item.get('WeatherDescription', 'N/A')}</td>
                <td>{item.get('PoP12h', 'N/A')}%</td>
            </tr>
            """
            
        html_content = f"""
        <html>
        <head>
            <title> 天氣預報</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                h1 {{ color: #1e88e5; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
                tr:nth-child(even) {{ background-color: #f9f9f9; }}
            </style>
        </head>
        <body>
            <h1>📍 未來一週天氣預報</h1>
            <table>
                <thead>
                    <tr>
                        <th>預報時段 (月-日 時:分)</th>
                        <th>溫度 (高/低)</th>
                        <th>天氣描述</th>
                        <th>12小時降雨機率</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows}
                </tbody>
            </table>
            <p>資料來源：中央氣象署</p>
        </body>
        </html>
        """
    
    # render_template_string 用於直接渲染內嵌的 HTML 字符串
    return render_template_string(html_content)

if __name__ == '__main__':
    # 在本地端運行，預設端口為 5000
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))