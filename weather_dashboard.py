import os
import time
import pandas as pd
import requests
import streamlit as st
import plotly.express as px
from sqlalchemy import create_engine, text
from streamlit_autorefresh import st_autorefresh

# ---------- VISUAL STYLING ----------

# Background gradient
st.markdown(
    """
    <style>
    .stApp {
        background: linear-gradient(135deg, #dbeafe, #f0f9ff);
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Title styling
st.markdown(
    """
    <style>
    h1 {
        text-align: center;
        color: #1e3a8a;
        font-size: 3em;
        font-weight: bold;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Metric card styling
st.markdown(
    """
    <style>
    div[data-testid="metric-container"] {
        background-color: #ffffff;
        border-radius: 12px;
        padding: 15px;
        box-shadow: 0px 2px 8px rgba(0, 0, 0, 0.1);
        text-align: center;
        background: linear-gradient(135deg, #e0f2fe, #bae6fd);
        transition: transform 0.2s, box-shadow 0.2s;
    }
    div[data-testid="metric-container"]:hover {
        transform: translateY(-5px);
        box-shadow: 0px 5px 15px rgba(0, 0, 0, 0.2);
    }
    div[data-testid="metric-container"] label {
        color: #1e3a8a;
        font-weight: bold;
    }
    div[data-testid="metric-container"] [data-testid="stMetricValue"] {
        color: #0f172a;
        font-size: 1.5em;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# ---------- AUTO REFRESH EVERY 30 SECONDS ----------
st_autorefresh(interval=30000, key="refresh")

# ---------- CONFIG ----------
st.set_page_config(page_title="Live Weather Dashboard 🌤️", layout="wide")

# ---------- API & DB CONFIG ----------
API_KEY = os.getenv("OPENWEATHER_API_KEY")
DEFAULT_CITY = os.getenv("DEFAULT_CITY", "Bangalore")
DB_USER = os.getenv("DB_USER", "weather_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "weather_pass")
DB_HOST = os.getenv("DB_HOST", "weather-mysql")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_NAME = os.getenv("DB_NAME", "weather_db")
DB_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# ---------- DB CONNECTION WITH RETRY ----------
MAX_RETRIES = 40
WAIT_SECONDS = 5
engine = None

for attempt in range(1, MAX_RETRIES + 1):
    try:
        engine = create_engine(DB_URL)
        with engine.begin() as conn:
            conn.execute(text("SELECT 1"))
        break
    except Exception as e:
        print(f"DB connection attempt {attempt} failed: {e}")
        time.sleep(WAIT_SECONDS)
else:
    raise Exception("Could not connect to DB after multiple retries.")

# ---------- ENSURE TABLE EXISTS ----------
with engine.begin() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS weather_logs (
            city VARCHAR(50),
            temperature FLOAT,
            humidity FLOAT,
            pressure FLOAT,
            wind_speed FLOAT,
            description VARCHAR(255),
            timestamp DATETIME
        )
    """))

# ---------- USER INPUT ----------
city = st.text_input("Enter City Name:", DEFAULT_CITY).strip()

# ---------- FETCH WEATHER DATA ----------
def fetch_weather(city_name):
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city_name}&appid={API_KEY}&units=metric"
    response = requests.get(url).json()
    if response.get("cod") != 200:
        return None
    data = {
        "city": city_name,
        "temperature": response["main"]["temp"],
        "humidity": response["main"]["humidity"],
        "pressure": response["main"]["pressure"],
        "wind_speed": response["wind"]["speed"],
        "description": response["weather"][0]["description"],
        "timestamp": pd.Timestamp.now()
    }
    return data

# ---------- SAVE WEATHER DATA ----------
def save_weather(engine, weather_data):
    df = pd.DataFrame([weather_data])
    with engine.begin() as conn:
        df.to_sql("weather_logs", conn, if_exists="append", index=False)

# ---------- HELPER: STYLE CHARTS ----------
def style_chart(fig):
    fig.update_layout(
        font=dict(family="Arial", size=14, color="#1e3a8a"),
        xaxis_title="Time",
        yaxis_title="",
        plot_bgcolor="rgba(255,255,255,0.9)",
        paper_bgcolor="rgba(255,255,255,0)",
        title=dict(x=0.5, font=dict(size=18, color="#1e3a8a")),
        xaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.1)"),
        yaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.1)"),
    )
    fig.update_traces(line=dict(width=3))
    return fig

# ---------- MAIN ----------
weather_data = fetch_weather(city)

if weather_data:
    st.title(f"Weather in {city}")
    st.subheader(f"{weather_data['description'].title()}")

    # Display metric cards
    col1, col2, col3 = st.columns(3)
    col1.metric("Temperature (°C)", weather_data["temperature"])
    col2.metric("Humidity (%)", weather_data["humidity"])
    col3.metric("Wind Speed (m/s)", weather_data["wind_speed"])

    # Save to DB
    save_weather(engine, weather_data)

    # Plot history
    with engine.begin() as conn:
        df_history = pd.read_sql(
            text("SELECT * FROM weather_logs WHERE city = :city ORDER BY timestamp DESC LIMIT 50"),
            conn,
            params={"city": city}
        )

    if not df_history.empty:
        df_history = df_history.sort_values("timestamp", ascending=False)
        df_history['time'] = pd.to_datetime(df_history['timestamp']).dt.strftime('%H:%M')

        # Temperature chart
        fig_temp = px.line(df_history, x="time", y="temperature", title=f"Temperature Trend - {city}")
        st.plotly_chart(style_chart(fig_temp), use_container_width=True)

        # Humidity chart
        fig_hum = px.line(df_history, x="time", y="humidity", title=f"Humidity Trend - {city}")
        st.plotly_chart(style_chart(fig_hum), use_container_width=True)

        # Pressure chart
        fig_press = px.line(df_history, x="time", y="pressure", title=f"Pressure Trend - {city}")
        st.plotly_chart(style_chart(fig_press), use_container_width=True)

        # Wind Speed chart
        fig_wind = px.line(df_history, x="time", y="wind_speed", title=f"Wind Speed Trend - {city}")
        st.plotly_chart(style_chart(fig_wind), use_container_width=True)

else:
    st.error("City not found or API error.")
