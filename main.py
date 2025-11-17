# streamlit_app.py
import streamlit as st
import requests
import os
import pandas as pd
import json

# --- 設定 CWA API 資訊 ---
# 基礎 URL，不包含任何參數
BASE_API_URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-D0047-091"
CWA_API_KEY = "CWA-FD731281-945E-4A82-83B3-A29D9938B48C"
# --- 應用程式標題和設定 ---
st.set_page_config(page_title="臺灣鄉鎮一週天氣預報", layout="wide")
st.title("📍 臺灣鄉鎮一週天氣預報 (CWA)")
st.caption("資料來源：交通部中央氣象署")

# 從 Streamlit Secrets 或環境變數安全地讀取 API 金鑰
API_KEY = os.environ.get("CWA_API_KEY")

if not API_KEY:
    st.error("❌ 錯誤：中央氣象署 (CWA) API 金鑰未設定。")
    st.markdown("請確認您已在 Streamlit Cloud 的 **Secrets** 中設定了 `CWA_API_KEY` 變數。")
    st.stop() 

# --- 資料抓取與處理函式 ---

@st.cache_data(ttl=3600) # 緩存資料 1 小時 (3600 秒)
def fetch_weather_data(api_key, location_name):
    """
    抓取 CWA API 的 JSON 天氣資料並提取指定地點的預報，
    將結果格式化為 Pandas DataFrame。
    """
    
    # === 使用 params 字典來構造您的完整 URL ===
    # requests 會自動將這些參數轉換為 URL query string
    params = {
        'Authorization': api_key,
        'format': 'JSON',
        'locationName': location_name, # <-- 這是動態的地點
        'elementName': 'WeatherDescription,MinT,MaxT,PoP12h'
    }
    # 範例：requests 會將此轉換為您想要的完整 URL (例如：雲林縣會被自動編碼)
    # response = requests.get("BASE_API_URL?Authorization=...&format=JSON&LocationName=雲林縣&elementName=...")
    # ===============================================

    try:
        # === 將 verify=False 加入 requests.get 呼叫中 ===
        # ⚠️ 風險警告：這會禁用 SSL 驗證，降低安全性
        response = requests.get(BASE_API_URL, params=params, timeout=10, verify=False) 
        response.raise_for_status()
        data = response.json()
        
        if data.get('success') != 'true':
            error_msg = data.get('message', 'API 回應成功但狀態為非成功')
            return None, f"API 請求失敗: {error_msg}"

        # --------------------- 資料解析邏輯 ---------------------
        records = data.get('records', {})
        locations = records.get('Locations', [])
        
        target_location_data = None
        for loc in locations:
            for loc_detail in loc.get('Location', []):
                if loc_detail.get('LocationName') == location_name: 
                    target_location_data = loc_detail
                    break
            if target_location_data:
                break
                
        if not target_location_data:
            return None, f"找不到地點: {location_name}"

        time_data = {}
        for element in target_location_data.get('WeatherElement', []):
            element_name = element.get('ElementName')
            
            element_map = {
                '天氣預報綜合描述': '天氣描述',
                '最高溫度': '最高溫',
                '最低溫度': '最低溫',
                '12小時降雨機率': '降雨機率',
            }
            display_name = element_map.get(element_name, element_name)
            
            for time_period in element.get('Time', []):
                start_time = time_period.get('StartTime')
                end_time = time_period.get('EndTime')
                key = (start_time, end_time)
                
                if key not in time_data:
                    time_data[key] = {
                        '預報開始時間': start_time, 
                        '預報結束時間': end_time
                    }
                
                element_value = time_period.get('ElementValue', [{}])[0]
                
                if element_name == '12小時降雨機率':
                    value = element_value.get('ProbabilityOfPrecipitation')
                    time_data[key][display_name] = f"{value}%"
                elif element_name == '最高溫度':
                    value = element_value.get('MaxTemperature')
                    time_data[key][display_name] = f"{value} °C"
                elif element_name == '最低溫度':
                    value = element_value.get('MinTemperature')
                    time_data[key][display_name] = f"{value} °C"
                elif element_name == '天氣預報綜合描述':
                    value = element_value.get('WeatherDescription')
                    time_data[key][display_name] = value

        # 轉換為 DataFrame
        forecasts = list(time_data.values())
        if not forecasts:
            return None, "API 返回的資料結構中未包含預報時間段。"
        
        df = pd.DataFrame(forecasts)
        
        df['預報時段'] = df['預報開始時間'].str[5:16].str.replace('T', ' ') + ' ~ ' + df['預報結束時間'].str[5:16].str.replace('T', ' ')
        
        final_columns = ['預報時段', '最高溫', '最低溫', '天氣描述', '降雨機率']
        present_columns = [col for col in final_columns if col in df.columns]
        
        return df[present_columns], None

    except requests.exceptions.RequestException as e:
        return None, f"網路請求錯誤: {e}"
    except Exception as e:
        return None, f"發生資料處理錯誤: {e}"


# --- Streamlit 應用程式主邏輯 ---

available_locations = [
    "雲林縣", "臺北市", "新北市", "桃園市", "臺中市", "臺南市", "高雄市", 
    "基隆市", "新竹市", "新竹縣", "苗栗縣", "彰化縣", "南投縣", "嘉義市", 
    "嘉義縣", "屏東縣", "宜蘭縣", "花蓮縣", "臺東縣", "澎湖縣", "金門縣", "連江縣"
]

default_location_index = available_locations.index("雲林縣")

# 側邊欄選擇器
selected_location = st.sidebar.selectbox(
    '選擇縣市：',
    options=available_locations,
    index=default_location_index
)

# 執行資料抓取
with st.spinner(f'正在抓取 {selected_location} 的天氣預報...'):
    weather_df, error_message = fetch_weather_data(API_KEY, selected_location)

# 顯示結果
if error_message:
    st.error(f"⚠️ 資料抓取失敗: {error_message}")
else:
    st.subheader(f"✅ {selected_location} 最新一週預報")
    
    # 處理溫度進度條的 min/max value
    min_temp_limit = 5
    max_temp_limit = 40

    st.dataframe(
        weather_df, 
        use_container_width=True,
        column_config={
            "最高溫": st.column_config.ProgressColumn("最高溫", format="%g °C", min_value=min_temp_limit, max_value=max_temp_limit),
            "最低溫": st.column_config.ProgressColumn("最低溫", format="%g °C", min_value=min_temp_limit, max_value=max_temp_limit),
            "降雨機率": st.column_config.ProgressColumn("降雨機率", format="%g %%", help="12小時累積降雨機率", min_value=0, max_value=100)
        }
    )

    st.sidebar.info("資料已緩存，每 1 小時更新一次。")

