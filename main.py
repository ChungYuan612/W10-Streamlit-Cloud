# streamlit_app.py
import streamlit as st
import requests
import os
import pandas as pd
import json
import urllib3
from datetime import datetime, timezone # 確保有 timezone

# 🌟 新增官方套件導入
from google import genai
from google.genai.errors import APIError # 用於處理 API 錯誤
from google.genai import types # 🌟 新增導入 types

# 由於您可能在部署時遇到 SSL 憑證問題，暫時禁用警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 設定 CWA API 資訊 ---
BASE_API_URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-D0047-091"

# ⚠️ CWA 金鑰：程式碼優先使用環境變數（Secrets），若無則使用硬編碼值。
CWA_AUTH_KEY_HARDCODED = "CWA-FD731281-945E-4A82-83B3-A29D9938B48C"
CWA_API_KEY = os.environ.get("CWA_API_KEY", CWA_AUTH_KEY_HARDCODED)

# --- 設定 GEMINI API 資訊 ---
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent"
# ⚠️ GEMINI 金鑰：必須從環境變數或 Secrets 讀取！
GEMINI_API_KEY = "AIzaSyBJl2iNRzF-xRANQNiVWoFZz6_1oG0nQOs"


# --- 應用程式標題和設定 ---
st.set_page_config(page_title="臺灣鄉鎮一週天氣預報與 AI 總結", layout="wide")
st.title("📍 臺灣鄉鎮一週天氣預報 (CWA) 與 AI 總結")
st.caption("資料來源：交通部中央氣象署")

# 檢查 CWA 金鑰（使用整合後的 CWA_API_KEY）
if not CWA_API_KEY:
    st.error("❌ 錯誤：中央氣象署 (CWA) API 金鑰未設定。")
    st.markdown("請確認您已在 Streamlit Cloud 的 **Secrets** 中設定 `CWA_API_KEY` 變數。")
    st.stop() 

# --- 資料抓取與處理函式 ---
@st.cache_data(ttl=3600) # 緩存資料 1 小時 (3600 秒)
def fetch_weather_data(api_key, location_name):
    """抓取 CWA API 的 JSON 天氣資料並提取指定地點的預報。"""
    
    params = {
        'Authorization': api_key,
        'format': 'JSON',
        'locationName': location_name, 
        'elementName': 'WeatherDescription,MinT,MaxT,PoP12h'
    }

    try:
        # 使用 verify=False 繞過 SSL 憑證驗證問題
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

        # 這是修正後的資料提取邏輯，將所有元素的值正確放入 time_data
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
                key = (start_time, end_time) # 使用原始時間字串作為 key
                
                if key not in time_data:
                    # 解析並格式化時間
                    try:
                        dt_start = datetime.fromisoformat(start_time)
                        dt_end = datetime.fromisoformat(end_time)
                    except ValueError:
                        return None, f"時間格式解析錯誤: {start_time}"

                    start_time_fmt = dt_start.strftime('%m/%d %H:%M')
                    end_time_fmt = dt_end.strftime('%H:%M')
                    
                    time_data[key] = {
                        '預報時段': f"{start_time_fmt} - {end_time_fmt}",
                        '預報開始時間': start_time, # 保留原始時間字串供內部使用
                        '預報結束時間': end_time    # 保留原始時間字串供內部使用
                    }
                
                element_value = time_period.get('ElementValue', [{}])[0]
                
                # 根據 element_name 提取對應的值
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
        
        # 確保最終 DataFrame 包含所有預期的欄位，並按照順序
        final_columns = ['預報時段', '最高溫', '最低溫', '天氣描述', '降雨機率']
        # 檢查所有預期的欄位是否都在 df 中，並補上缺失的欄位（用 NaN）
        for col in final_columns:
            if col not in df.columns:
                df[col] = pd.NA # 或者 '' 或是 'N/A'
        
        return df[final_columns], None # 確保返回指定順序的欄位

    except requests.exceptions.RequestException as e:
        return None, f"網路請求錯誤: {e}"
    except Exception as e:
        return None, f"發生資料處理錯誤: {e}"

@st.cache_resource
def get_gemini_client():
    """初始化並返回 Gemini Client。"""
    # client 會自動從環境變數 GEMINI_API_KEY 讀取金鑰
    try:
        # 使用 st.secrets 作為首選，如果沒有則會嘗試 os.environ
        api_key = GEMINI_API_KEY
        if not api_key:
            return None
        return genai.Client(api_key=api_key)
    except Exception as e:
        st.error(f"無法初始化 Gemini Client: {e}")
        return None

def generate_summary(weather_data_text):
    """使用 Gemini SDK 產生天氣總結與穿搭建議，並設定 AI 角色。"""
    
    client = get_gemini_client()
    if client is None:
        return None, "Gemini API 金鑰未設定或 Client 初始化失敗。"

    # 設置給 AI 的提示 (這部分不變)
    prompt = f"""
    這是臺灣某地區未來一週的天氣預報資料：
    --- 資料 ---
    {weather_data_text}
    ---
    請你根據這份資料，總結未來的天氣趨勢（氣溫、晴雨狀況），並提供實用且具體的穿搭建議。
    請確保你的總結**限定在 150 字以內**。
    """
    
    # 🌟 使用 types.GenerateContentConfig 設置所有配置和角色
    config = types.GenerateContentConfig(
        system_instruction="你是一位專業、幽默且口語化的氣象主播。請以親切熱情的語氣進行播報。",
        temperature=0.5
    )
    
    try:
        # 🌟 將配置物件傳遞給 config 參數
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=config # 傳遞配置物件
        )
        
        # 返回 AI 輸出的文字
        return response.text, None
        
    except APIError as e:
        return None, f"Gemini API 請求失敗 (SDK 錯誤): {e}"
    except Exception as e:
        return None, f"發生意外錯誤: {e}"
        
# --- 5. Streamlit 應用程式主邏輯 ---

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
    weather_df, error_message = fetch_weather_data(CWA_API_KEY, selected_location)

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
    
    st.markdown("---")
    
    # --- AI 總結按鈕和顯示區塊 ---
    
    # 將 DataFrame 轉換為 AI 容易閱讀的文字格式
    weather_text_for_ai = weather_df.to_string(index=False) 

    if st.button("🤖 點此連線 AI 總結天氣與穿搭建議", use_container_width=True, type="primary"):
        with st.spinner("正在連線至 Gemini 產生總結，請稍候..."):
            summary_text, gemini_error = generate_summary(weather_text_for_ai)
            
            if gemini_error:
                st.error(gemini_error)
            else:
                st.subheader("💡 AI 天氣總結與穿搭指南")
                st.markdown(summary_text)







