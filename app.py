import streamlit as st
import secrets  # For generating cryptographically secure session tokens
from datetime import datetime, timedelta, date
import zoneinfo  # Comprehensive timezone engine support (Python 3.9+)
import hashlib
from sqlalchemy import text
import pandas as pd
import extra_streamlit_components as stx

# ---------------- INITIAL VALUE LOOKUPS & BASELINE INTERCEPTIONS ---------------- #

# 1. Initialize core state trackers before checking structural UI components
if "court_config" not in st.session_state:
    st.session_state.court_config = None

if "username" not in st.session_state:
    st.session_state.username = ""

# ---------------- DATABASE CONNECTION ---------------- #

conn = st.connection("postgresql", type="sql")

# 2. ACTIVE ENFORCEMENT GUARD: Verification check to kick out stale user sessions if code gets deleted
if st.session_state.court_config is not None:
    active_code = st.session_state.court_config.get("access_code")
    # Query database live to see if the admin has wiped this configuration key
    check_active_df = conn.query("SELECT sport FROM tennis_court_configurations WHERE access_code=:ac", params={"ac": active_code}, ttl=0)
    
    if check_active_df.empty:
        # Code no longer exists! Flush active session parameters state clean to redirect them to entry wall
        st.session_state.court_config = None
        st.warning("⚠️ The active session configuration key was deleted by an administrator. Please input an authenticated access code.")

# 3. Define dynamic browser configuration maps based on active session context parameters
dynamic_title = "Multi-Sport Arena Scheduler"
dynamic_icon = "🏟️"

if st.session_state.court_config is not None:
    configured_sport = st.session_state.court_config["sport"].strip()
    dynamic_title = f"{configured_sport} Scheduler"
    
    # Clean fallback normalization map matching sport labels to visual favicons
    sport_emoji_map = {
        "badminton": "🏸",
        "tennis": "🎾",
        "football": "⚽",
        "soccer": "⚽",
        "basketball": "🏀",
        "squash": "🏓",
        "swimming": "🏊",
        "cricket": "🏏",
        "volleyball": "🏐"
    }
    dynamic_icon = sport_emoji_map.get(configured_sport.lower(), "🏟️")
elif st.session_state.username == "admin":
    dynamic_title = "Admin Console Panel"
    dynamic_icon = "👑"

# 4. Securely deploy page layouts natively mapping structural components variables
st.set_page_config(
    page_title=dynamic_title,
    page_icon=dynamic_icon,
    layout="wide"
)

# Define IST Timezone
IST = zoneinfo.ZoneInfo("Asia/Kolkata")

# -------- TIMEZONE REGISTRY CONFIGURATOR -------- #
@st.cache_resource
def get_all_timezones():
    return sorted(list(zoneinfo.available_timezones()))

all_tz_options = get_all_timezones()

if "app_tz" not in st.session_state:
    st.session_state.app_tz = "Asia/Kolkata"

current_tz_info = zoneinfo.ZoneInfo(st.session_state.app_tz)


def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()


# Initialize Isolated Tables on the Shared Supabase Instance
def init_db():
    with conn.session as session:
        # Users table
        session.execute(text("""
        CREATE TABLE IF NOT EXISTS tennis_users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
        """))

        # Bookings table (strictly isolated by sport and court configurations)
        session.execute(text("""
        CREATE TABLE IF NOT EXISTS tennis_bookings (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL,
            booking_date TEXT NOT NULL,
            slot TEXT NOT NULL,
            court_number INTEGER DEFAULT 1,
            sport TEXT DEFAULT 'Badminton'
        )
        """))

        # Sessions table
        session.execute(text("""
        CREATE TABLE IF NOT EXISTS tennis_sessions (
            token TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """))

        # Completely configurable access code mapping registry
        session.execute(text("""
        CREATE TABLE IF NOT EXISTS tennis_court_configurations (
            id SERIAL PRIMARY KEY,
            sport TEXT NOT NULL,
            court_count INTEGER NOT NULL DEFAULT 1,
            access_code TEXT UNIQUE NOT NULL,
            timezone TEXT DEFAULT 'Asia/Kolkata',
            created_at TEXT NOT NULL
        )
        """))
        session.commit()

        # -------- AUTOMATIC ADMIN ACCOUNT GENERATION & ENFORCEMENT -------- #
        hashed_admin_password = make_hashes("LeBakri!!18")
        
        try:
            res = session.execute(text("SELECT username FROM tennis_users WHERE username = 'admin'")).fetchone()
            if res:
                session.execute(text("UPDATE tennis_users SET password=:p WHERE username='admin'"), {"p": hashed_admin_password})
            else:
                session.execute(text("INSERT INTO tennis_users (username, password) VALUES (:u, :p)"), {"u": "admin", "p": hashed_admin_password})
            session.commit()
        except Exception:
            session.rollback()


# Trigger initial table check on startup
init_db()

# ---------------- REMOVE EXPIRED BOOKINGS ---------------- #

# Fetch current time in configured context timezone
now = datetime.now(current_tz_info)

# Fetch directly from Supabase using conn.query
all_bookings_df = conn.query("SELECT id, booking_date, slot FROM tennis_bookings", ttl=0)

if not all_bookings_df.empty:
    with conn.session as session:
        for _, row in all_bookings_df.iterrows():
            bid = int(row['id'])
            b_date = row['booking_date']
            b_slot = row['slot']

            try:
                # Parse and explicitly attach the configured runtime timezone to the database record
                booking_datetime = datetime.strptime(
                    f"{b_date} {b_slot}",
                    "%Y-%m-%d %I:%M %p"
                ).replace(tzinfo=current_tz_info)

                # Remove expired bookings securely comparing aware datetimes
                if booking_datetime < now:
                    session.execute(text("DELETE FROM tennis_bookings WHERE id=:id"), {"id": bid})
            except Exception:
                pass
        session.commit()

# ---------------- BASELINE STATE INITIALIZATION ---------------- #

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# Initialize the Cookie Manager cleanly without caching decorators to avoid CachedWidgetWarning
def get_cookie_manager():
    try:
        return stx.CookieManager()
    except Exception:
        return None

cookie_manager = get_cookie_manager()

# BROWSER COOKIE AUTO-LOGIN INTERCEPTOR
if not st.session_state.logged_in and cookie_manager:
    try:
        # Read unique badminton cookie directly from the user's browser hard drive
        cookie_token = cookie_manager.get(cookie="badminton_scheduler_token")
        
        if cookie_token:
            # Crosscheck cookie validation key securely with Supabase database logs
            session_df = conn.query("SELECT username FROM tennis_sessions WHERE token=:t", params={"t": cookie_token}, ttl=0)
            
            if not session_df.empty:
                saved_username = session_df.iloc[0]["username"]
                # Extra verification step: Check if the user record still exists in the user registry
                user_check_df = conn.query("SELECT username FROM tennis_users WHERE username=:u", params={"u": saved_username}, ttl=0)
                if not user_check_df.empty:
                    st.session_state.logged_in = True
                    st.session_state.username = saved_username
                    st.rerun()  # Rerun to sync dynamic page parameters allocation securely on login
            else:
                # Clean up invalid or tampered client cookies safely
                cookie_manager.delete(cookie="badminton_scheduler_token")
    except Exception:
        pass

# Ensure URL parameter hacks are completely locked down
st.query_params.clear()

# ---------------- TITLE ---------------- #

st.title(f"{dynamic_icon} {dynamic_title}")

# ---------------- LOGIN / SIGNUP ---------------- #

if not st.session_state.logged_in:

    menu = st.selectbox(
        "Menu",
        ["Login", "Sign Up"]
    )

    username = st.text_input("Username", key=f"user_{menu}").strip()
    password = st.text_input("Password", type="password", key=f"pass_{menu}")
    
    # Only show the "Keep me logged in" checkbox if the menu mode is Login
    remember_me = False
    if menu == "Login":
        remember_me = st.checkbox("Keep me logged in", key="remember_Login")

    # -------- SIGN UP -------- #

    if menu == "Sign Up":

        if st.button("Create Account"):
            if not username or not password:
                st.error("Please fill in all fields.")
            elif username.lower() == "admin":
                st.error("The username 'admin' is a reserved system identifier.")
            else:
                existing_df = conn.query("SELECT username FROM tennis_users WHERE username=:u", params={"u": username}, ttl=0)

                if not existing_df.empty:
                    st.error("Username already exists")
                else:
                    try:
                        with conn.session as session:
                            session.execute(
                                text("INSERT INTO tennis_users (username, password) VALUES (:u, :p)"),
                                {"u": username, "p": make_hashes(password)}
                            )
                            session.commit()
                        st.success("Account created! You can now switch to Login.")
                    except Exception:
                        st.error("Could not register user. Try again.")

    # -------- LOGIN -------- #

    else:

        if st.button("Login"):
            hashed_input = make_hashes(password)
            user_df = conn.query("SELECT username, password FROM tennis_users WHERE username=:u", params={"u": username}, ttl=0)

            if not user_df.empty:
                stored_password = user_df.iloc[0]["password"]

                if hashed_input == stored_password:
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    
                    if remember_me and cookie_manager:
                        secure_token = secrets.token_urlsafe(32)
                        current_timestamp = datetime.now(current_tz_info).strftime("%Y-%m-%d %H:%M:%S")
                        
                        # Write tracking mapping to backend database
                        with conn.session as session:
                            session.execute(
                                text("INSERT INTO tennis_sessions (token, username, created_at) VALUES (:t, :u, :c)"),
                                {"t": secure_token, "u": username, "c": current_timestamp}
                            )
                            session.commit()
                            
                        # Store a persistent cookie on client browser configuration expiring in 30 days
                        try:
                            cookie_manager.set(
                                cookie="badminton_scheduler_token",
                                val=secure_token,
                                expires_at=datetime.now() + pd.Timedelta(days=30)
                            )
                        except Exception:
                            pass
                    
                    st.query_params.clear()
                    st.rerun()
                else:
                    st.error("Wrong password")
            else:
                st.error("User not found")

# ---------------- MAIN APP (AUTHENTICATED SESSIONS) ---------------- #

else:

    # ---------------- INTERFACE ARCHITECTURE: GLOBAL ACCOUNT SIDEBAR (LEFT) ---------------- #
    with st.sidebar:
        st.markdown(f"### 👤 Active Profile")
        st.success(f"Logged in as: **{st.session_state.username}**")
        
        if st.session_state.court_config is not None:
            st.info(f"🎯 Active Layout: **{st.session_state.court_config['sport']}**")
            if st.button("🔄 Switch Access Code", use_container_width=True):
                st.session_state.court_config = None
                st.rerun()
        
        st.write("---")
        
        # -------- PASSWORD CHANGING SYSTEM FOR ALL ACCOUNTS IN SIDEBAR -------- #
        st.markdown("### 🔒 Account Security")
        with st.expander("Update Profile Password"):
            with st.form("change_password_form", clear_on_submit=True):
                current_password = st.text_input("Current Password", type="password")
                new_password = st.text_input("New Password", type="password")
                confirm_password = st.text_input("Confirm New Password", type="password")
                submit_change = st.form_submit_button("Update Password", use_container_width=True)

                if submit_change:
                    if not current_password or not new_password or not confirm_password:
                        st.error("All password fields are required.")
                    elif new_password != confirm_password:
                        st.error("New passwords do not match.")
                    else:
                        user_data_df = conn.query("SELECT password FROM tennis_users WHERE username=:u", params={"u": st.session_state.username}, ttl=0)
                        
                        if not user_data_df.empty and make_hashes(current_password) == user_data_df.iloc[0]["password"]:
                            new_hashed = make_hashes(new_password)
                            with conn.session as session:
                                session.execute(
                                    text("UPDATE tennis_users SET password=:p WHERE username=:u"), 
                                    {"p": new_hashed, "u": st.session_state.username}
                                )
                                session.commit()
                            st.success("Password changed successfully!")
                        else:
                            st.error("Incorrect current password.")
                            
        st.write("---")
        
        # -------- FIXED LOGOUT PIPELINE IN SIDEBAR -------- #
        if st.button("Logout from Account", type="primary", use_container_width=True):
            if cookie_manager:
                active_cookie = cookie_manager.get(cookie="badminton_scheduler_token")
                if active_cookie:
                    with conn.session as session:
                        session.execute(text("DELETE FROM tennis_sessions WHERE token=:t"), {"t": active_cookie})
                        session.commit()
                    
                    try:
                        cookie_manager.delete(cookie="badminton_scheduler_token")
                    except Exception:
                        pass
            
            st.session_state.logged_in = False
            st.session_state.username = ""
            st.session_state.court_config = None
            st.query_params.clear()
            st.rerun()

    # ---------------- MAIN CONTENT WRAPPER ---------------- #

    # -------- INTERFACE ARCHITECTURE: ADMIN COMMAND DECK (MAIN CONTENT TOP) -------- #
    if st.session_state.username == "admin":
        st.markdown("## 👑 Admin Control Panel")
        
        admin_tab1, admin_tab2, admin_tab3, admin_tab4 = st.tabs([
            "⚙️ Deploy Access Configurations",
            "🔑 Code Registry Logs",
            "👥 Accounts Registry",
            "📋 Global Bookings Registry"
        ])
        
        with admin_tab1:
            st.markdown("### Create Custom Access Code & Facility Mapping")
            with st.form("admin_access_code_form", clear_on_submit=True):
                sport_input = st.text_input("Sport / Facility Category Name", placeholder="e.g., Football, Squash, Swimming").strip()
                courts_input = st.number_input("Total Courts / Fields Configured", min_value=1, max_value=24, value=2)
                code_input = st.text_input("Unique System Entry Code").strip()
                
                tz_input = st.selectbox(
                    "Facility Local Timezone",
                    options=all_tz_options,
                    index=all_tz_options.index("Asia/Kolkata") if "Asia/Kolkata" in all_tz_options else 0
                )
                submit_config = st.form_submit_button("Deploy Scheduler Configuration")

                if submit_config:
                    if not sport_input or not code_input:
                        st.error("All configuration parameters are strictly required.")
                    else:
                        try:
                            current_ts = datetime.now(current_tz_info).strftime("%Y-%m-%d %H:%M:%S")
                            with conn.session as session:
                                session.execute(
                                    text("INSERT INTO tennis_court_configurations (sport, court_count, access_code, timezone, created_at) VALUES (:s, :cc, :ac, :tz, :cat)"),
                                    {"s": sport_input, "cc": courts_input, "ac": code_input, "tz": tz_input, "cat": current_ts}
                                )
                                session.commit()
                            st.success(f"Deployed! Code '{code_input}' locks a {courts_input}-court setup for '{sport_input}' in standard `{tz_input}` time.")
                            st.rerun()
                        except Exception:
                            st.error("Failed to deploy rules. Verify this access code isn't a duplicate registry item.")
                            
        with admin_tab2:
            st.markdown("### Active Configurations Registry & Deletion")
            all_configs_df = conn.query("SELECT id, sport, court_count, access_code, timezone FROM tennis_court_configurations ORDER BY id DESC", ttl=0)
            
            if not all_configs_df.empty:
                for _, cfg_row in all_configs_df.iterrows():
                    cfg_id = int(cfg_row["id"])
                    cfg_sport = cfg_row["sport"]
                    cfg_courts = cfg_row["court_count"]
                    cfg_code = cfg_row["access_code"]
                    cfg_tz = cfg_row.get("timezone", "Asia/Kolkata")
                    
                    c_col1, c_col2 = st.columns([3, 1])
                    with c_col1:
                        st.markdown(f"🔹 Code Key: **{cfg_code}** | Sport: `{cfg_sport}` | Courts: `{cfg_courts}` | Timezone: `{cfg_tz}`")
                    with c_col2:
                        if st.button("Delete Code Rule", key=f"del_code_{cfg_id}", type="secondary"):
                            with conn.session as session:
                                # CASCADE DELETION: Purge matching booking rows as well
                                session.execute(text("DELETE FROM tennis_bookings WHERE sport=:sp"), {"sp": cfg_sport})
                                session.execute(text("DELETE FROM tennis_court_configurations WHERE id=:id"), {"id": cfg_id})
                                session.commit()
                            st.success(f"Configuration key '{cfg_code}' and matching booking rows wiped from master logs.")
                            st.rerun()
            else:
                st.info("No customized setup rules have been provisioned by the admin yet.")
                
        with admin_tab3:
            st.markdown("### User Accounts Management")
            total_users = conn.query("SELECT COUNT(*) as count FROM tennis_users", ttl=0).iloc[0]['count']
            st.write(f"Total Registered Users: {total_users}")
            
            all_users_df = conn.query("SELECT username FROM tennis_users", ttl=0)
            
            if not all_users_df.empty:
                for _, row in all_users_df.iterrows():
                    user_to_manage = row["username"]
                    if user_to_manage == "admin":
                        continue
                        
                    u_col1, u_col2 = st.columns([3, 1])
                    with u_col1:
                        st.write(f"👤 User: **{user_to_manage}**")
                    with u_col2:
                        if st.button("Delete Account", key=f"del_user_{user_to_manage}", type="secondary"):
                            with conn.session as session:
                                session.execute(text("DELETE FROM tennis_users WHERE username=:u"), {"u": user_to_manage})
                                session.execute(text("DELETE FROM tennis_bookings WHERE username=:u"), {"u": user_to_manage})
                                session.execute(text("DELETE FROM tennis_sessions WHERE username=:u"), {"u": user_to_manage})
                                session.commit()
                            st.success(f"Account '{user_to_manage}' and active bookings cleared successfully.")
                            st.rerun()
            else:
                st.info("No user accounts found.")
                
        with admin_tab4:
            st.markdown("### Global System Bookings Logs")
            total_bookings = conn.query("SELECT COUNT(*) as count FROM tennis_bookings", ttl=0).iloc[0]['count']
            st.write(f"Total Database Bookings: {total_bookings}")
            
            all_data_df = conn.query("SELECT id, username, booking_date, slot, court_number, sport FROM tennis_bookings ORDER BY booking_date DESC, slot ASC", ttl=0)

            if not all_data_df.empty:
                for _, row in all_data_df.iterrows():
                    b_id = int(row['id'])
                    court_lbl = f"Court {row.get('court_number', 1)}"
                    sport_lbl = row.get('sport', 'Badminton')
                    
                    b_col1, b_col2 = st.columns([3, 1])
                    with b_col1:
                        st.write(f"👤 {row['username']} | 📅 {row['booking_date']} | ⏰ {row['slot']} | 🏟️ {court_lbl} ({sport_lbl})")
                    with b_col2:
                        if st.button("Cancel Booking", key=f"admin_cancel_bk_{b_id}", type="secondary"):
                            with conn.session as session:
                                session.execute(text("DELETE FROM tennis_bookings WHERE id=:id"), {"id": b_id})
                                session.commit()
                            st.success("Reservation removed successfully.")
                            st.rerun()
            else:
                st.info("No bookings registered yet.")
                
        st.markdown("---")

    # -------- MANDATORY GATEWAY WALL FOR ALL ACCOUNTS (INCLUDING ADMIN) -------- #
    if st.session_state.court_config is None:
        st.subheader("🔒 Target Access Code Required")
        st.info("Please supply an active facility code to dynamically open your scheduler view panels.")
        
        with st.form("gate_access_form"):
            entered_code = st.text_input("Enter Configuration Code").strip()
            submit_gate = st.form_submit_button("Authenticate & Open Scheduler")
            
            if submit_gate:
                match_df = conn.query("SELECT sport, court_count, timezone FROM tennis_court_configurations WHERE access_code=:ac", params={"ac": entered_code}, ttl=0)
                if not match_df.empty:
                    config_tz = match_df.iloc[0].get("timezone", "Asia/Kolkata")
                    st.session_state.court_config = {
                        "sport": match_df.iloc[0]["sport"],
                        "court_count": int(match_df.iloc[0]["court_count"]),
                        "access_code": entered_code,
                        "timezone": config_tz
                    }
                    st.session_state.app_tz = config_tz
                    st.success(f"Authorized! Opening customized workspace for: **{st.session_state.court_config['sport']}**")
                    st.rerun()
                else:
                    st.error("Invalid configuration credentials. Please double-check your code or consult your system administrator.")

    # -------- DYNAMIC SCHEDULER BOARD IMPLEMENTATION -------- #
    else:
        current_sport = st.session_state.court_config["sport"]
        total_courts_to_render = st.session_state.court_config["court_count"]

        st.markdown(f"## {dynamic_icon} Bounded Workspace: **{current_sport}** (`{st.session_state.app_tz}` Time)")

        # -------- DATE CHOICE -------- #

        today = datetime.now(current_tz_info).date()
        tomorrow = today + timedelta(days=1)

        selected_date = st.radio(
            "Choose Booking Day",
            [today, tomorrow],
            format_func=lambda x: x.strftime("%A %d %B")
        )

        # -------- GENERATE SLOTS -------- #

        slots = []

        start = datetime.strptime("00:00", "%H:%M")
        end = datetime.strptime("23:59", "%H:%M")

        now_ist = datetime.now(current_tz_info)

        while start < end:
            slot_str = start.strftime("%I:%M %p")

            if selected_date == today:
                if start.time() > now_ist.time():
                    slots.append(slot_str)
            else:
                slots.append(slot_str)

            start += timedelta(minutes=30)

        # -------- HIGHLY DETAILED DYNAMIC COURT SUB-TABS INTERFACE GENERATOR -------- #
        court_tabs = st.tabs([f"🏟️ Court / Section #{c}" for c in range(1, total_courts_to_render + 1)])

        for court_idx in range(1, total_courts_to_render + 1):
            with court_tabs[court_idx - 1]:

                # -------- GET BOOKED SLOTS NATIVELY FILTERED BY CONFIGURED SPORT NAME -------- #
                booked_df = conn.query("SELECT slot FROM tennis_bookings WHERE booking_date=:d AND court_number=:cn AND sport=:sp", 
                                       params={"d": str(selected_date), "cn": court_idx, "sp": current_sport}, ttl=0)
                booked_slots = booked_df["slot"].tolist() if not booked_df.empty else []

                # -------- GET YOUR SLOTS NATIVELY FILTERED BY CONFIGURED SPORT NAME -------- #
                your_df = conn.query("SELECT slot FROM tennis_bookings WHERE username=:u AND booking_date=:d AND court_number=:cn AND sport=:sp", 
                                     params={"u": st.session_state.username, "d": str(selected_date), "cn": court_idx, "sp": current_sport}, ttl=0)
                your_slots = your_df["slot"].tolist() if not your_df.empty else []

                # -------- SLOT LEGEND -------- #
                st.markdown("🟩 Available  |  🟥 Booked  |  🟦 Yours")

                # -------- SLOT UI -------- #
                st.subheader(f"Available Time Slices - Court #{court_idx}")
                cols = st.columns(4)

                for i, slot in enumerate(slots):
                    with cols[i % 4]:
                        if slot in your_slots:
                            st.info(f"🟦 {slot}")
                        elif slot in booked_slots:
                            st.error(f"🟥 {slot}")
                        else:
                            if st.button(f"🟩 {slot}", key=f"slot_{slot}_c{court_idx}"):
                                # Safe double-check transaction check
                                check_df = conn.query("SELECT slot FROM tennis_bookings WHERE booking_date=:d AND slot=:s AND court_number=:cn AND sport=:sp", 
                                                      params={"d": str(selected_date), "s": slot, "cn": court_idx, "sp": current_sport}, ttl=0)

                                if not check_df.empty:
                                    st.error("This slot was just claimed. Please select an available slice.")
                                else:
                                    # Day cap lookup logic mapping tracking criteria
                                    count_df = conn.query("SELECT COUNT(*) as count FROM tennis_bookings WHERE username=:u AND booking_date=:d", 
                                                          params={"u": st.session_state.username, "d": str(selected_date)}, ttl=0)
                                    booking_count = count_df.iloc[0]['count']

                                    if booking_count >= 3 and st.session_state.username != "admin":
                                        st.error("Daily booking safety protocol limits reached (Max 3/day).")
                                    else:
                                        with conn.session as session:
                                            session.execute(
                                                text("INSERT INTO tennis_bookings (username, booking_date, slot, court_number, sport) VALUES (:u, :d, :s, :cn, :sp)"),
                                                {"u": st.session_state.username, "d": str(selected_date), "s": slot, "cn": court_idx, "sp": current_sport}
                                            )
                                            session.commit()
                                        st.success(f"Successfully booked {slot} on Court #{court_idx}!")
                                        st.rerun()

        # -------- DISPLAY WORKSPACE-ISOLATED RESERVATIONS -------- #
        st.subheader(f"Your Bookings for {current_sport}")

        user_bookings_df = conn.query("SELECT id, booking_date, slot, court_number, sport FROM tennis_bookings WHERE username=:u AND sport=:sp ORDER BY booking_date DESC, slot ASC", 
                                      params={"u": st.session_state.username, "sp": current_sport}, ttl=0)

        if not user_bookings_df.empty:
            for _, row in user_bookings_df.iterrows():
                bid = int(row['id'])
                booking_date_str = row['booking_date']
                slot = row['slot']
                c_num = row.get('court_number', 1)
                s_name = row.get('sport', 'Badminton')

                col1, col2 = st.columns([3, 1])

                with col1:
                    st.write(f"📌 {booking_date_str} at {slot} (Court #{c_num} — {s_name})")

                with col2:
                    if st.button("Cancel Booking", key=f"cancel_{bid}"):
                        with conn.session as session:
                            session.execute(text("DELETE FROM tennis_bookings WHERE id=:id"), {"id": bid})
                            session.commit()
                        st.success("Booking successfully removed.")
                        st.rerun()
        else:
            st.write("You don't have any reservations registered under this specific category context yet.")