import streamlit as st
import datetime
import pytz
import math
import requests
import xml.etree.ElementTree as ET
from streamlit_autorefresh import st_autorefresh
from skyfield import almanac
from skyfield.api import load, wgs84
from skyfield.framelib import ecliptic_frame

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Indian Market Astro-Algo Pro", layout="wide", page_icon="🕉️")

# --- AUTO REFRESH (Every 60 Seconds) ---
count = st_autorefresh(interval=60000, key="datarefresh")

# --- CUSTOM CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #0E1117; color: #E0E0E0; }
    
    /* Astro-Prediction Card */
    .prediction-box {
        background-color: #1A1C24;
        border: 1px solid #333;
        border-radius: 8px;
        padding: 15px;
        height: 100%;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        border-left: 4px solid #00FFA3;
    }
    .index-title { font-size: 1.1rem; font-weight: bold; color: #FFF; margin-bottom: 10px; border-bottom: 1px solid #444; padding-bottom: 5px;}
    
    .stat-row { display: flex; justify-content: space-between; margin-bottom: 6px; font-size: 0.9rem; }
    .stat-label { color: #888; }
    .stat-val-green { color: #00FFA3; font-weight: bold; }
    .stat-val-red { color: #FF453A; font-weight: bold; }
    .stat-val-white { color: #EEE; font-weight: bold; }
    
    .strategy-tag {
        background-color: rgba(0, 255, 163, 0.1);
        color: #00FFA3;
        padding: 4px 8px;
        border-radius: 4px;
        text-align: center;
        font-weight: bold;
        margin-top: 10px;
        font-size: 0.9rem;
        border: 1px solid #00FFA3;
    }

    /* News & Table Styles */
    .news-item {
        background-color: #1A1C24;
        border-left: 3px solid #00FFA3;
        padding: 10px;
        margin-bottom: 10px;
        border-radius: 4px;
        transition: transform 0.2s;
    }
    .news-item:hover { transform: translateX(5px); }
    .news-link { color: #E0E0E0; text-decoration: none; font-size: 0.9rem; font-weight: 500; display: block; }
    .news-source { color: #00FFA3; font-size: 0.7rem; margin-top: 5px; display: block; text-transform: uppercase; }

    .trade-row { border-left: 4px solid #444; padding: 12px; margin-bottom: 8px; background: #16181e; display: flex; align-items: center; border-radius: 4px;}
    .trade-row.active { border-left: 4px solid #00FFA3; background: #1f2937; border: 1px solid #00FFA3; box-shadow: 0 0 10px rgba(0,255,163,0.1); }
    .trade-row.rahu { border-left: 4px solid #FF453A; background: #2d1b1b; }
    
    .badge-good { background-color: rgba(0, 255, 163, 0.15); color: #00FFA3; padding: 2px 6px; border-radius: 4px; font-size: 0.8rem; border: 1px solid #00FFA3; }
    .badge-bad { background-color: rgba(255, 69, 58, 0.15); color: #FF453A; padding: 2px 6px; border-radius: 4px; font-size: 0.8rem; border: 1px solid #FF453A; }
    .badge-neutral { background-color: rgba(94, 92, 230, 0.15); color: #a1a1aa; padding: 2px 6px; border-radius: 4px; font-size: 0.8rem; border: 1px solid #555; }
    </style>
    """, unsafe_allow_html=True)

# --- 1. CONFIGURATION ---
TZ_IST = pytz.timezone('Asia/Kolkata')
ASSAM_PLACES = {
    "North Lakhimpur": (27.2360, 94.1028),
    "Guwahati": (26.1445, 91.7362),
    "Dibrugarh": (27.4728, 94.9120),
    "Jorhat": (26.7509, 94.2037),
    "Silchar": (24.8333, 92.7789),
    "Tezpur": (26.6528, 92.7926),
    "Nagaon": (26.3452, 92.6838),
    "Tinsukia": (27.4886, 95.3558)
}

# --- 2. DATA ENGINES ---
@st.cache_data(ttl=60)
def fetch_real_news():
    """Fetches Live Market News with Browser Headers"""
    news_items = []
    
    # Headers to mimic a real browser (Fixes 5paisa blocking)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    sources = [
        ("Economic Times", "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms"),
        ("MoneyControl", "https://www.moneycontrol.com/rss/marketreports.xml"),
        ("5paisa", "https://www.5paisa.com/rss/latest-share-market-news-moving-stocks.xml"),
        ("LiveMint", "https://www.livemint.com/rss/markets")
    ]
    
    for source_name, url in sources:
        try:
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                count = 0
                for item in root.findall('./channel/item'):
                    if count >= 3: break
                    title = item.find('title').text
                    link = item.find('link').text
                    
                    # Avoid duplicates
                    if not any(d['title'] == title for d in news_items):
                        news_items.append({"title": title, "link": link, "source": source_name})
                    count += 1
        except Exception:
            continue
            
    if not news_items: return [{"title": "News feed unavailable. Check internet connection.", "link": "#", "source": "System"}]
    return news_items

# --- 3. IMPROVED ASTRO LOGIC (SIDEREAL) ---
try:
    eph = load('de421.bsp')
except:
    st.warning("Downloading NASA Data...")
    eph = load('de421.bsp')

sun, moon, earth = eph['sun'], eph['moon'], eph['earth']
ts = load.timescale()

# LOCATIONS
# Critical: Market Timing relies on MUMBAI sunrise, not user location.
NSE_LOC = wgs84.latlon(19.0760, 72.8777) 

def get_lahiri_ayanamsa(t):
    """
    Calculates approximate Lahiri Ayanamsa for the given time.
    Formula: ~24 degrees (modern era)
    This converts Western (Tropical) Longitude to Vedic (Sidereal).
    """
    # Approximate J2000 epoch difference
    # A simplified but effective calculation for Lahiri
    # Mean Ayanamsa = 23 deg 51 min 25.5 sec + rate * t
    days_since_j2000 = t.tt - 2451545.0
    # Rate of precession approx 50.29 arcseconds per year
    precession = (50.29 / 3600.0) * (days_since_j2000 / 365.25)
    # Base Ayanamsa for J2000 (Lahiri) approx 23.85 degrees
    ayanamsa = 23.85 + precession
    return ayanamsa

def get_sidereal_pos(body, t, observer_loc):
    """Returns the Sidereal Longitude (0-360) of a planet"""
    observer = earth + observer_loc
    astrometric = observer.at(t).observe(body)
    _, lon_ecl, _ = astrometric.apparent().ecliptic_latlon()
    
    tropical_lon = lon_ecl.degrees
    ayanamsa = get_lahiri_ayanamsa(t)
    
    sidereal_lon = (tropical_lon - ayanamsa) % 360
    return sidereal_lon

def get_tithi(t, observer_loc):
    """Calculates the Lunar Day (Tithi) based on Sidereal positions"""
    # Tithi is independent of Ayanamsa actually (relative distance), 
    # but using sidereal for consistency.
    moon_lon = get_sidereal_pos(moon, t, observer_loc)
    sun_lon = get_sidereal_pos(sun, t, observer_loc)
    
    diff = (moon_lon - sun_lon) % 360
    tithi_idx = int(diff / 12) + 1
    
    # Paksha (Waxing/Waning)
    paksha = "Shukla (Waxing)" if tithi_idx <= 15 else "Krishna (Waning)"
    display_tithi = tithi_idx if tithi_idx <= 15 else tithi_idx - 15
    
    tithi_names = ["Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami", 
                   "Shashthi", "Saptami", "Ashtami", "Navami", "Dashami", 
                   "Ekadashi", "Dwadashi", "Trayodashi", "Chaturdashi", "Purnima/Amavasya"]
    
    name = tithi_names[display_tithi-1]
    if tithi_idx == 30: name = "Amavasya (New Moon)"
    if tithi_idx == 15: name = "Purnima (Full Moon)"
    
    return f"{name} ({paksha})"

def calculate_rahu_kaal(weekday_idx, sunrise, sunset):
    # Accurate Rahu Kaal Segments (Sunrise to Sunset / 8)
    rk_map = {0: 1, 1: 6, 2: 4, 3: 5, 4: 3, 5: 2, 6: 7} # 0=Mon, 1=Tue...
    duration = (sunset - sunrise).total_seconds()
    part = duration / 8.0
    segment_idx = rk_map[weekday_idx]
    
    # Logic: Start time is sunrise + (segment_idx * part) NOT (segment_idx - 1)
    # Actually standard chart:
    # Mon: 2nd part (7:30-9:00 approx) -> Index 1 in 0-7 scale? 
    # Let's use the standard "Part Number" logic where Sunrise is part 0.
    # Standard Map (1st part is 0): 
    # Mon(1), Tue(6), Wed(4), Thu(5), Fri(3), Sat(2), Sun(7)
    
    start_seconds = (segment_idx - 1) * part # Because map is 1-based (1st part, 2nd part...)
    start = sunrise + datetime.timedelta(seconds=start_seconds)
    end = start + datetime.timedelta(seconds=part)
    return start, end

def calculate_market_schedule(date_obj_py):
    # USE NSE LOCATION FOR MARKET TIMING
    midnight = date_obj_py.replace(hour=0, minute=0, second=0, microsecond=0)
    t0 = ts.from_datetime(midnight)
    t1 = ts.from_datetime(midnight + datetime.timedelta(days=1))
    t_rise, y_rise = almanac.find_discrete(t0, t1, almanac.sunrise_sunset(eph, NSE_LOC))
    
    sunrise_t, sunset_t = None, None
    for t, event in zip(t_rise, y_rise):
        if event == 1 and sunrise_t is None: sunrise_t = t
        elif event == 0 and sunset_t is None: sunset_t = t
    
    if sunrise_t is None or sunset_t is None: return [], None, None, None

    sunrise_dt = sunrise_t.astimezone(TZ_IST)
    sunset_dt = sunset_t.astimezone(TZ_IST)
    
    rk_start, rk_end = calculate_rahu_kaal(date_obj_py.weekday(), sunrise_dt, sunset_dt)
    
    day_duration = (sunset_dt - sunrise_dt).total_seconds()
    hora_len = day_duration / 12.0
    
    weekday = date_obj_py.weekday()
    # 0=Mon, 1=Tue...
    weekdays_lords = ["Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Sun"]
    day_lord = weekdays_lords[weekday]
    
    # Hora Order logic: Start with Day Lord, then 6th planet from it
    # Order: Sun -> Venus -> Mercury -> Moon -> Saturn -> Jupiter -> Mars
    hora_fixed_order = ["Sun", "Venus", "Mercury", "Moon", "Saturn", "Jupiter", "Mars"]
    
    # Find start index
    start_idx = hora_fixed_order.index(day_lord)
    
    schedule = []
    curr = sunrise_dt
    
    # Define Market Hours
    mkt_open = date_obj_py.replace(hour=9, minute=15, second=0, microsecond=0)
    mkt_close = date_obj_py.replace(hour=15, minute=30, second=0, microsecond=0)
    pre_open = date_obj_py.replace(hour=9, minute=0, second=0, microsecond=0)
    
    for i in range(12):
        end = curr + datetime.timedelta(seconds=hora_len)
        planet = hora_fixed_order[(start_idx + i) % 7]
        
        # Check overlaps
        # Case 1: Hora is completely inside market hours
        # Case 2: Hora starts before market, ends in market
        # Case 3: Hora starts in market, ends after market
        
        # Intersection logic
        latest_start = max(curr, pre_open)
        earliest_end = min(end, mkt_close)
        
        if latest_start < earliest_end:
            # Re-calculate Rahu overlap strictly based on time
            is_rahu = (curr < rk_end) and (end > rk_start)
            # Refine Rahu: Only flag if the intersection actually overlaps Rahu
            # (Simplification: if the Hora block touches Rahu Kaal, mark it)
            
            schedule.append({
                "start": curr, 
                "end": end, 
                "planet": planet, 
                "is_rahu": is_rahu
            })
            
        curr = end
        
    return schedule, day_lord, rk_start, rk_end

def get_nakshatra_info_sidereal(t_obj, lat, lon):
    # Use user location object
    user_loc_obj = wgs84.latlon(lat, lon)
    
    # GET SIDEREAL LONGITUDE (The Fix)
    sidereal_deg = get_sidereal_pos(moon, t_obj, user_loc_obj)
    
    # 360 degrees / 27 nakshatras = 13.3333... degrees per nakshatra
    index = int(sidereal_deg / 13.333333333)
    
    nakshatras = [
        "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra", "Punarvasu", "Pushya", "Ashlesha",
        "Magha", "Purva Phalguni", "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
        "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati"
    ]
    lords = [
        "Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury",
        "Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury",
        "Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"
    ]
    
    # Correct index wraparound
    idx = index % 27
    
    # Calculate Padam (Quarter 1,2,3,4)
    remainder = sidereal_deg % 13.333333333
    padam = int(remainder / 3.333333333) + 1
    
    return nakshatras[idx], lords[idx], padam, sidereal_deg

# --- 4. PREDICTION LOGIC ---
PLANET_STRATEGIES = {
    "Jupiter": {"strat": "BUY CALL", "reason": "Trend Expansion / Banking"},
    "Sun":      {"strat": "BUY CALL", "reason": "Institutional Buying / PSU"},
    "Mars":     {"strat": "BUY PUT",  "reason": "Aggressive Selling / Panic"},
    "Mercury": {"strat": "SCALP BOTH", "reason": "High Speed / Volatility"},
    "Venus":    {"strat": "AVOID",    "reason": "Rangebound / Premium Decay"},
    "Saturn":  {"strat": "SELL OPT", "reason": "Slow Movement / Theta Decay"},
    "Moon":     {"strat": "TRAP",      "reason": "Erratic / Fake Breakouts"}
}

INDEX_PREFS = {
    "NIFTY 50":     {"best": ["Jupiter", "Sun"], "worst": ["Saturn", "Rahu"]}, 
    "BANK NIFTY":   {"best": ["Mercury", "Mars", "Jupiter"], "worst": ["Saturn", "Venus"]}, 
    "SENSEX":       {"best": ["Sun", "Jupiter"], "worst": ["Ketu", "Rahu"]},
    "MIDCAP SEL":   {"best": ["Mars", "Mercury"], "worst": ["Saturn", "Venus"]}
}

def get_astro_prediction(schedule, index_name, is_today_view, now_reference):
    prefs = INDEX_PREFS.get(index_name)
    best_t = "None"
    worst_t = "None"
    strategy = "WAIT"
    reason = "Neutral Market"
    
    # Find NEXT Best
    for slot in schedule:
        check_time = now_reference if is_today_view else slot['start'] - datetime.timedelta(minutes=1)

        if slot['end'] > check_time:
            if slot['planet'] in prefs['best']:
                if best_t == "None":
                    best_t = slot['start'].strftime('%I:%M')
                    strat_info = PLANET_STRATEGIES.get(slot['planet'])
                    strategy = strat_info['strat']
                    reason = strat_info['reason']
                    break
    
    # Find NEXT Worst
    for slot in schedule:
        check_time = now_reference if is_today_view else slot['start'] - datetime.timedelta(minutes=1)
        if slot['end'] > check_time:
            if slot['planet'] in prefs['worst'] or slot['is_rahu']:
                if worst_t == "None":
                    worst_t = slot['start'].strftime('%I:%M')
                    break
                
    return best_t, worst_t, strategy, reason

# --- 5. EXECUTION ---
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # 1. DOB SELECTION (DEFAULT: 1984-09-06)
    user_dob = st.date_input("Date of Birth", datetime.date(1984, 9, 6))
    
    # 2. TOB SELECTION (DEFAULT: 00:37)
    user_tob = st.time_input("Time of Birth", datetime.time(0, 37))
    
    # 3. PLACE OF BIRTH SELECTION
    place_names = list(ASSAM_PLACES.keys())
    pob_name = st.selectbox("Place of Birth", place_names, index=place_names.index("North Lakhimpur"))
    pob_coords = ASSAM_PLACES[pob_name]

    # 4. DATE SELECTION FOR ANALYSIS
    target_date = st.date_input("Select Trading Date", datetime.date.today())
    
    st.info("System uses **Sidereal (Lahiri)** Calculations for accuracy.")

# --- DATE LOGIC ---
real_now_ist = datetime.datetime.now(TZ_IST)
is_today_view = (target_date == datetime.date.today())

# Handle Weekends
if target_date.weekday() > 4:
    st.error("Market is Closed on Weekends. Select a weekday.")
    st.stop()

if is_today_view:
    calculation_dt = real_now_ist
    display_date_str = f"TODAY ({target_date.strftime('%d %b %Y')})"
else:
    start_of_day = datetime.datetime.combine(target_date, datetime.time(9, 15))
    calculation_dt = TZ_IST.localize(start_of_day)
    display_date_str = f"FUTURE ({target_date.strftime('%d %b %Y')})"

# Calculate Schedule using NSE (Mumbai) Location for accuracy
schedule, day_lord, rk_start, rk_end = calculate_market_schedule(calculation_dt)

if not schedule:
    st.error("Time calculation failed.")
    st.stop()

# --- USER ASTRO CALCULATIONS ---
# Combine Date and Time
dt_naive = datetime.datetime.combine(user_dob, user_tob)
dt_ist = TZ_IST.localize(dt_naive)
t_user = ts.from_datetime(dt_ist)

# Get Sidereal Nakshatra (Corrected from Tropical)
user_star, user_lord, user_padam, moon_deg = get_nakshatra_info_sidereal(t_user, pob_coords[0], pob_coords[1])

# Get Tithi for Market Day
t_market = ts.from_datetime(calculation_dt)
current_tithi = get_tithi(t_market, NSE_LOC)

# Determine "Current Hora"
current_hora = {"planet": "OFF", "start": calculation_dt, "end": calculation_dt, "is_rahu": False}
if is_today_view:
    curr = next((s for s in schedule if s['start'] <= real_now_ist < s['end']), None)
    if curr: current_hora = curr
else:
    current_hora["planet"] = "N/A (Future)"

# --- DASHBOARD HEADER ---
st.markdown(f"### 🔮 Astro-Scalping Signals: {display_date_str}")
if is_today_view:
    st.caption(f"Current Time: {real_now_ist.strftime('%I:%M %p')} | Tithi: **{current_tithi}**")
else:
    st.caption(f"Forecast for: {target_date} | Tithi: **{current_tithi}**")

m1, m2, m3, m4 = st.columns(4)
indices = ["NIFTY 50", "BANK NIFTY", "SENSEX", "MIDCAP SEL"]
cols_ref = [m1, m2, m3, m4]

for idx, label in enumerate(indices):
    best_t, worst_t, strat, reason = get_astro_prediction(schedule, label, is_today_view, real_now_ist)
    
    with cols_ref[idx]:
        st.markdown(f"""
        <div class='prediction-box'>
            <div class='index-title'>{label}</div>
            <div class='stat-row'><span class='stat-label'>Next Best:</span> <span class='stat-val-green'>{best_t}</span></div>
            <div class='stat-row'><span class='stat-label'>Avoid:</span> <span class='stat-val-red'>{worst_t}</span></div>
            <div class='stat-row'><span class='stat-label'>Logic:</span> <span class='stat-val-white'>{reason}</span></div>
            <div class='strategy-tag'>{strat}</div>
        </div>
        """, unsafe_allow_html=True)

# --- USER LUCK & DETAILS ---
st.markdown("---")
u1, u2 = st.columns([3, 1])

FRIENDSHIP_TABLE = {
    "Sun":      {"friends": ["Moon", "Mars", "Jupiter"], "enemies": ["Venus", "Saturn", "Rahu", "Ketu"]},
    "Moon":     {"friends": ["Sun", "Mercury"], "enemies": ["Rahu", "Ketu", "Saturn"]}, # Updated Sat as enemy/neutral
    "Mars":     {"friends": ["Sun", "Moon", "Jupiter"], "enemies": ["Mercury", "Rahu"]},
    "Mercury": {"friends": ["Sun", "Venus"], "enemies": ["Moon"]},
    "Jupiter": {"friends": ["Sun", "Moon", "Mars"], "enemies": ["Mercury", "Venus"]},
    "Venus":    {"friends": ["Mercury", "Saturn", "Rahu"], "enemies": ["Sun", "Moon"]},
    "Saturn":  {"friends": ["Mercury", "Venus", "Rahu"], "enemies": ["Sun", "Moon", "Mars"]},
    "Rahu":    {"friends": ["Venus", "Saturn", "Mercury"], "enemies": ["Sun", "Moon", "Mars"]},
    "Ketu":    {"friends": ["Mars", "Jupiter"], "enemies": ["Sun", "Moon"]}
}

def check_compatibility(user_lord, hora_planet):
    rel = FRIENDSHIP_TABLE.get(user_lord, {})
    if hora_planet in rel.get("friends", []): return "Lucky", "badge-good", 100
    elif hora_planet in rel.get("enemies", []): return "Avoid", "badge-bad", 20
    return "Neutral", "badge-neutral", 50

with u1:
    st.markdown(f"**Day Lord:** {day_lord} | **Your Birth Star:** {user_star} (Padam {user_padam}) | **Your Lord:** {user_lord}")
    with st.expander("Show Astronomical Details"):
        st.text(f"Moon Longitude (Sidereal): {moon_deg:.2f}°")
        st.text(f"Algorithm: Lahiri Ayanamsa Correction applied to NASA JPL Data")
        st.text(f"Market Timing Source: NSE Mumbai (19.07N, 72.87E)")

with u2:
    if is_today_view and current_hora['planet'] != "OFF":
        luck_label, luck_badge, luck_pct = check_compatibility(user_lord, current_hora['planet'])
        d_col = "normal" if luck_pct == 100 else ("inverse" if luck_pct == 20 else "off")
        st.metric("My Luck Now", f"{luck_pct}%", delta=luck_label, delta_color=d_col)
    elif not is_today_view:
        st.metric("My Luck Now", "--", delta="Future View", delta_color="off")
    else:
        st.metric("My Luck Now", "Closed", delta="Off-Market", delta_color="off")

# --- NEWS SECTION ---
news = fetch_real_news()
st.markdown("### 📰 Real-Time Headlines")
n1, n2 = st.columns(2)
half = (len(news) // 2) + 1
with n1:
    for item in news[:half]:
        st.markdown(f"<div class='news-item'><a class='news-link' href='{item['link']}' target='_blank'>{item['title']}</a><span class='news-source'>{item['source']}</span></div>", unsafe_allow_html=True)
with n2:
    for item in news[half:]:
        st.markdown(f"<div class='news-item'><a class='news-link' href='{item['link']}' target='_blank'>{item['title']}</a><span class='news-source'>{item['source']}</span></div>", unsafe_allow_html=True)

# --- SCHEDULE SECTION ---
st.markdown("---")
st.subheader(f"📜 Schedule (Filtered for Trading): {target_date.strftime('%A, %d %B')}")
cols = st.columns([2, 1, 1, 2, 2, 3])
cols[0].markdown("**Time (IST)**")
cols[1].markdown("**Hora**")
cols[2].markdown("**Rahu?**")
cols[3].markdown(f"**Luck ({user_lord})**")
cols[4].markdown("**Status**")
cols[5].markdown("**Explanation**")

for slot in schedule:
    s_str = slot['start'].strftime('%I:%M %p')
    e_str = slot['end'].strftime('%I:%M %p')
    planet = slot['planet']
    
    # Logic for Active/Past
    is_active = False
    is_past = False
    if is_today_view:
        is_active = slot['start'] <= real_now_ist < slot['end']
        is_past = real_now_ist > slot['end']
    
    # --- STATUS LOGIC with BEST/WORST Flagging ---
    luck_txt, luck_badge, luck_val = check_compatibility(user_lord, planet)
    
    # Default State
    status_text = "🟢 OPEN"
    text_color = "#00FFA3" # Green
    expl = "Scalping Zone"
    row_class = "trade-row"
    opacity = "1.0"

    # 1. Astro Logic Override
    if luck_val == 100:
        status_text = "🌟 BEST"
        text_color = "#FFD700" # Gold
        expl = f"High Luck with {planet}"
    elif luck_val == 20:
        status_text = "🛑 AVOID"
        text_color = "#FF453A" # Red
        expl = "Incompatible Planet"
    
    # 2. Safety Overrides (Rahu / Pre-Open)
    if slot['is_rahu']:
        status_text = "⛔ RAHU"
        text_color = "#FF453A"
        expl = "Trap Zone / High Risk"
        row_class = "trade-row rahu"
    
    if slot['start'].hour == 9 and slot['start'].minute < 15:
        status_text = "🟠 PRE"
        text_color = "#FEAE00"
        expl = "Pre-Open / Volatility"

    # 3. Active/Past Logic
    if is_active:
        status_text = f"🟢 LIVE ({status_text})"
        row_class += " active"
    elif is_past:
        opacity = "0.5" # Dim past rows

    rahu_txt = "💀 YES" if slot['is_rahu'] else "-"
    rahu_col = "#FF453A" if slot['is_rahu'] else "#444"

    st.markdown(f"""
    <div class='{row_class}' style='opacity:{opacity}'>
        <div style='width:16%; font-family:monospace; font-size:1.0rem;'>{s_str} &nbsp;&nbsp;-&nbsp;&nbsp; {e_str}</div>
        <div style='width:10%; font-weight:bold; color:#00FFA3'>{planet}</div>
        <div style='width:10%; color:{rahu_col}; font-weight:bold'>{rahu_txt}</div>
        <div style='width:16%'><span class='{luck_badge}'>{luck_txt}</span></div>
        <div style='width:16%; font-weight:bold; color:{text_color}'>{status_text}</div>
        <div style='width:25%; font-size:0.9rem; color:#aaa'>{expl}</div>
    </div>
    """, unsafe_allow_html=True)


# --- ADVANCED PLANNER ---
st.markdown("---")
st.subheader("🚀 Advanced Index Scalping Planner")
st.caption(f"Filters specific trade setups based on Planetary Friendships & Market Timings.")

planner_tabs = st.tabs(indices)

for i, index_name in enumerate(indices):
    with planner_tabs[i]:
        prefs = INDEX_PREFS.get(index_name)
        valid_slots = []
        
        for slot in schedule:
            show_slot = True
            if is_today_view and slot['end'] < real_now_ist:
                show_slot = False
            
            if show_slot:
                is_best = slot['planet'] in prefs['best']
                is_worst = (slot['planet'] in prefs['worst']) or slot['is_rahu']
                
                if is_best and not slot['is_rahu']: # Added Rahu check to Best
                    strat_data = PLANET_STRATEGIES[slot['planet']]
                    valid_slots.append({
                        "time": f"{slot['start'].strftime('%I:%M %p')} - {slot['end'].strftime('%I:%M %p')}",
                        "hora": slot['planet'],
                        "status": "🌟 HIGH PROBABILITY",
                        "action": f"✅ {strat_data['strat']}", 
                        "logic": f"{slot['planet']} is Strong for {index_name}",
                        "color": "#00FFA3",
                        "bg": "rgba(0, 255, 163, 0.05)"
                    })
                elif is_worst:
                    reason = "Rahu Kaal (Traps)" if slot['is_rahu'] else f"{slot['planet']} is Weak for {index_name}"
                    valid_slots.append({
                        "time": f"{slot['start'].strftime('%I:%M %p')} - {slot['end'].strftime('%I:%M %p')}",
                        "hora": slot['planet'],
                        "status": "🛑 DANGER ZONE",
                        "action": "⛔ NO TRADING",
                        "logic": reason,
                        "color": "#FF453A",
                        "bg": "rgba(255, 69, 58, 0.05)"
                    })

        if valid_slots:
            st.markdown(f"""
            <div style="display:flex; font-weight:bold; color:#888; padding:5px 10px; border-bottom:1px solid #444; margin-bottom:10px;">
                <div style="width:25%">Time</div>
                <div style="width:15%">Hora</div>
                <div style="width:25%">Signal</div>
                <div style="width:35%">Action</div>
            </div>
            """, unsafe_allow_html=True)
            
            for v in valid_slots:
                st.markdown(f"""
                <div style="border-left: 4px solid {v['color']}; background-color: {v.get('bg', '#1A1C24')}; padding: 12px; margin-bottom: 8px; border-radius: 4px; display: flex; align-items: center;">
                    <div style="width: 25%; font-family:monospace; font-size:1.0rem;">{v['time']}</div>
                    <div style="width: 15%; font-weight:bold; color: #FFF;">{v['hora']}</div>
                    <div style="width: 25%; font-weight:bold; color: {v['color']};">{v['status']}</div>
                    <div style="width: 35%;"><span style="background:{v.get('bg', 'transparent')}; color:{v['color']}; padding:4px 8px; border-radius:4px; border:1px solid {v['color']}; font-size:0.9rem; font-weight:bold;">{v['action']}</span></div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info(f"No significant High/Low probability events found for {index_name} for the remainder of {target_date}.")