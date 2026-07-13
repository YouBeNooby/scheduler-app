import streamlit as st
import secrets
from datetime import datetime, timedelta, date
import zoneinfo
import hashlib
from sqlalchemy import text
import pandas as pd
import extra_streamlit_components as stx

# ---------------- INITIALIZATION ---------------- #
if "court_config" not in st.session_state: st.session_state.court_config = None
if "username" not in st.session_state: st.session_state.username = ""
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "account_vault" not in st.session_state: st.session_state.account_vault = {}
if "adding_new_account" not in st.session_state: st.session_state.adding_new_account = False
if "app_tz" not in st.session_state: st.session_state.app_tz = "Asia/Kolkata"

conn = st.connection("postgresql", type="sql")

def get_cookie_manager():
    try: return stx.CookieManager()
    except: return None

cookie_manager = get_cookie_manager()

# -------- ACTIVE ENFORCEMENT GUARD -------- #
if st.session_state.logged_in and st.session_state.court_config is not None:
    active_code = st.session_state.court_config.get("access_code")
    check_active = conn.query("SELECT sport FROM tennis_court_configurations WHERE access_code=:ac", params={"ac": active_code}, ttl=0)
    
    if check_active.empty:
        st.session_state.court_config = None
        if cookie_manager:
            try: cookie_manager.delete(cookie="stadium_access_code")
            except: pass
        st.warning("⚠️ The active session configuration key was deleted by an administrator. Please input an authenticated access code.")

# -------- BROWSER COOKIE ACCESS CODE AUTO-LOAD -------- #
if st.session_state.logged_in and st.session_state.court_config is None and cookie_manager:
    try:
        saved_code = cookie_manager.get(cookie="stadium_access_code")
        if saved_code:
            match_df = conn.query("SELECT sport, court_count, timezone FROM tennis_court_configurations WHERE access_code=:ac", params={"ac": saved_code}, ttl=0)
            if not match_df.empty:
                config_tz = match_df.iloc[0].get("timezone", "Asia/Kolkata")
                st.session_state.court_config = {
                    "sport": match_df.iloc[0]["sport"],
                    "court_count": int(match_df.iloc[0]["court_count"]),
                    "access_code": saved_code,
                    "timezone": config_tz
                }
                st.session_state.app_tz = config_tz
    except: pass

# -------- DYNAMIC UI CONFIG -------- #
dynamic_title, dynamic_icon = "Multi-Sport Arena Scheduler", "🏟️"

if st.session_state.court_config is not None:
    configured_sport = st.session_state.court_config["sport"].strip()
    dynamic_title = f"{configured_sport} Scheduler"
    sport_emoji_map = {"badminton": "🏸", "tennis": "🎾", "football": "⚽", "soccer": "⚽", "basketball": "🏀", "squash": "🏓", "swimming": "🏊", "cricket": "🏏", "volleyball": "🏐"}
    dynamic_icon = sport_emoji_map.get(configured_sport.lower(), "🏟️")
elif st.session_state.username == "admin":
    dynamic_title, dynamic_icon = "Admin Console Panel", "👑"

st.set_page_config(page_title=dynamic_title, page_icon=dynamic_icon, layout="wide")

# -------- TIMEZONE REGISTRY -------- #
current_tz_info = zoneinfo.ZoneInfo(st.session_state.app_tz)

@st.cache_resource
def get_all_timezones():
    return sorted(list(zoneinfo.available_timezones()))
all_tz_options = get_all_timezones()

# -------- DATABASE INIT -------- #
def make_hashes(password): return hashlib.sha256(str.encode(password)).hexdigest()

def init_db():
    with conn.session as session:
        session.execute(text("CREATE TABLE IF NOT EXISTS tennis_users (id SERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL)"))
        session.execute(text("CREATE TABLE IF NOT EXISTS tennis_bookings (id SERIAL PRIMARY KEY, username TEXT NOT NULL, booking_date TEXT NOT NULL, slot TEXT NOT NULL, court_number INTEGER DEFAULT 1, sport TEXT DEFAULT 'Badminton')"))
        session.execute(text("CREATE TABLE IF NOT EXISTS tennis_sessions (token TEXT PRIMARY KEY, username TEXT NOT NULL, created_at TEXT NOT NULL)"))
        session.execute(text("CREATE TABLE IF NOT EXISTS tennis_court_configurations (id SERIAL PRIMARY KEY, sport TEXT NOT NULL, court_count INTEGER NOT NULL DEFAULT 1, access_code TEXT UNIQUE NOT NULL, timezone TEXT DEFAULT 'Asia/Kolkata', created_at TEXT NOT NULL)"))
        session.commit()
        
        hashed_admin = make_hashes("LeBakri18!!")
        try:
            res = session.execute(text("SELECT username FROM tennis_users WHERE username = 'admin'")).fetchone()
            if not res: session.execute(text("INSERT INTO tennis_users (username, password) VALUES ('admin', :p)"), {"p": hashed_admin})
            session.commit()
        except: session.rollback()

if "db_initialized" not in st.session_state:
    init_db()
    st.session_state.db_initialized = True

# -------- REMOVE EXPIRED BOOKINGS -------- #
now = datetime.now(current_tz_info)
all_bookings_df = conn.query("SELECT id, booking_date, slot FROM tennis_bookings", ttl=0)

if not all_bookings_df.empty:
    with conn.session as session:
        for _, row in all_bookings_df.iterrows():
            try:
                booking_datetime = datetime.strptime(f"{row['booking_date']} {row['slot']}", "%Y-%m-%d %I:%M %p").replace(tzinfo=current_tz_info)
                if booking_datetime < now:
                    session.execute(text("DELETE FROM tennis_bookings WHERE id=:id"), {"id": int(row['id'])})
            except: pass
        session.commit()

# -------- MULTI-VAULT COOKIE LOGIC -------- #
if not st.session_state.logged_in and not st.session_state.adding_new_account and cookie_manager:
    try:
        vault_cookie = cookie_manager.get(cookie="scheduler_vault_tokens")
        if vault_cookie:
            for t in vault_cookie.split(","):
                if not t.strip(): continue
                session_df = conn.query("SELECT username FROM tennis_sessions WHERE token=:t", params={"t": t.strip()}, ttl=0)
                if not session_df.empty:
                    saved_username = session_df.iloc[0]["username"]
                    user_check_df = conn.query("SELECT username FROM tennis_users WHERE username=:u", params={"u": saved_username}, ttl=0)
                    if not user_check_df.empty:
                        st.session_state.account_vault[saved_username] = True
            
            if st.session_state.account_vault:
                st.session_state.logged_in = True
                st.session_state.username = list(st.session_state.account_vault.keys())[0]
    except: pass

st.query_params.clear()

# ---------------- LOGIN / SIGNUP (FORM-LESS FOR STABILITY) ---------------- #
if not st.session_state.logged_in:
    st.title(f"{dynamic_icon} {dynamic_title}")
    
    if st.session_state.adding_new_account:
        st.subheader("Add an Account to your Vault")
    else:
        st.subheader("Please Login or Sign Up")

    # Fixed: No on_change=st.rerun, let Streamlit handle it naturally
    menu = st.radio("Mode", ["Login", "Sign Up"], horizontal=True, key="auth_radio")
    
    username = st.text_input("Username").strip()
    password = st.text_input("Password", type="password")
    
    if menu == "Sign Up":
        if st.button("Create Account", type="primary"):
            if not username or not password: st.error("Please fill in all fields.")
            elif username.lower() == "admin": st.error("The username 'admin' is a reserved system identifier.")
            else:
                existing = conn.query("SELECT username FROM tennis_users WHERE username=:u", params={"u": username}, ttl=0)
                if not existing.empty: st.error("Username already exists")
                else:
                    try:
                        with conn.session as s:
                            s.execute(text("INSERT INTO tennis_users (username, password) VALUES (:u, :p)"), {"u": username, "p": make_hashes(password)})
                            s.commit()
                        st.success("Account created! You can now switch to Login.")
                    except: st.error("Could not register user. Try again.")
    else: # Login
        remember_me = st.checkbox("Keep me logged in")
        if st.button("Login", type="primary"):
            if not username or not password: st.error("Please fill in all fields.")
            else:
                user_df = conn.query("SELECT username, password FROM tennis_users WHERE username=:u", params={"u": username}, ttl=0)
                if not user_df.empty and make_hashes(password) == user_df.iloc[0]["password"]:
                    st.session_state.update({"logged_in": True, "username": username, "adding_new_account": False})
                    st.session_state.account_vault[username] = True
                    
                    if remember_me and cookie_manager:
                        token = secrets.token_urlsafe(32)
                        with conn.session as s:
                            s.execute(text("INSERT INTO tennis_sessions (token, username, created_at) VALUES (:t, :u, :c)"), {"t": token, "u": username, "c": str(datetime.now(current_tz_info))})
                            s.commit()
                        
                        existing_cookie = cookie_manager.get(cookie="scheduler_vault_tokens")
                        new_cookie_val = f"{existing_cookie},{token}" if existing_cookie else token
                        try: cookie_manager.set(cookie="scheduler_vault_tokens", val=new_cookie_val, expires_at=datetime.now() + pd.Timedelta(days=30))
                        except: pass
                    st.rerun()
                else:
                    st.error("Invalid username or password.")

    if st.session_state.adding_new_account:
        if st.button("Cancel & Return to Vault", use_container_width=True):
            st.session_state.adding_new_account = False
            st.session_state.logged_in = True
            st.rerun()
    st.stop()

# ---------------- MAIN APP (AUTHENTICATED) ---------------- #
else:
    # -------- SIDEBAR ACCOUNT VAULT -------- #
    with st.sidebar:
        st.markdown("### 👤 Active Profile")
        st.success(f"Logged in as: **{st.session_state.username}**")
        
        if len(st.session_state.account_vault) > 1:
            st.divider()
            st.subheader("Account Vault")
            vault_users = list(st.session_state.account_vault.keys())
            current_idx = vault_users.index(st.session_state.username) if st.session_state.username in vault_users else 0
                
            switch_to = st.selectbox("Switch Account", vault_users, index=current_idx)
            if switch_to != st.session_state.username:
                st.session_state.username = switch_to
                st.session_state.court_config = None
                if cookie_manager:
                    try: cookie_manager.delete(cookie="stadium_access_code")
                    except: pass
                st.rerun()

            st.caption("Remove account from vault:")
            for user in vault_users:
                if user != st.session_state.username:
                    if st.button(f"🗑️ Remove {user}", key=f"rem_{user}", use_container_width=True):
                        del st.session_state.account_vault[user]
                        st.rerun()

        if st.button("➕ Add Another Account", use_container_width=True):
            st.session_state.adding_new_account = True
            st.session_state.logged_in = False
            st.session_state.court_config = None
            if cookie_manager:
                try: cookie_manager.delete(cookie="stadium_access_code")
                except: pass
            st.rerun()
            
        st.write("---")

        if st.session_state.court_config is not None:
            st.info(f"🎯 Active Layout: **{st.session_state.court_config['sport']}**")
            if st.button("🔄 Switch Access Code", use_container_width=True):
                st.session_state.court_config = None
                if cookie_manager:
                    try: cookie_manager.delete(cookie="stadium_access_code")
                    except: pass
                st.rerun()
        
        st.write("---")
        
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
                        user_data = conn.query("SELECT password FROM tennis_users WHERE username=:u", params={"u": st.session_state.username}, ttl=0)
                        if not user_data.empty and make_hashes(current_password) == user_data.iloc[0]["password"]:
                            with conn.session as s:
                                s.execute(text("UPDATE tennis_users SET password=:p WHERE username=:u"), {"p": make_hashes(new_password), "u": st.session_state.username})
                                s.commit()
                            st.success("Password changed successfully!")
                        else: st.error("Incorrect current password.")
                            
        st.write("---")
        
        if st.button("Logout from Entire Session", type="primary", use_container_width=True):
            if cookie_manager:
                vault_cookie = cookie_manager.get(cookie="scheduler_vault_tokens")
                if vault_cookie:
                    with conn.session as s:
                        for t in vault_cookie.split(","):
                            if t.strip(): s.execute(text("DELETE FROM tennis_sessions WHERE token=:t"), {"t": t.strip()})
                        s.commit()
                    try: cookie_manager.delete(cookie="scheduler_vault_tokens")
                    except: pass
                try: cookie_manager.delete(cookie="stadium_access_code")
                except: pass
            st.session_state.clear()
            st.query_params.clear()
            st.rerun()

    # -------- ADMIN COMMAND DECK -------- #
    if st.session_state.username == "admin":
        st.markdown("## 👑 Admin Control Panel")
        admin_tab1, admin_tab2, admin_tab3, admin_tab4 = st.tabs(["⚙️ Deploy Configs", "🔑 Code Registry", "👥 Accounts", "📋 Global Bookings"])
        
        with admin_tab1:
            st.markdown("### Create Custom Access Code")
            with st.form("admin_access_code_form", clear_on_submit=True):
                sport_input = st.text_input("Sport / Facility Name", placeholder="e.g., Football, Squash").strip()
                courts_input = st.number_input("Total Courts Configured", min_value=1, max_value=24, value=2)
                code_input = st.text_input("Unique Entry Code").strip()
                tz_input = st.selectbox("Facility Timezone", options=all_tz_options, index=all_tz_options.index("Asia/Kolkata") if "Asia/Kolkata" in all_tz_options else 0)
                
                if st.form_submit_button("Deploy Configuration"):
                    if not sport_input or not code_input: st.error("All parameters are required.")
                    else:
                        try:
                            with conn.session as s:
                                s.execute(text("INSERT INTO tennis_court_configurations (sport, court_count, access_code, timezone, created_at) VALUES (:s, :cc, :ac, :tz, :cat)"),
                                          {"s": sport_input, "cc": courts_input, "ac": code_input, "tz": tz_input, "cat": str(datetime.now(current_tz_info))})
                                s.commit()
                            st.success(f"Deployed! Code '{code_input}' for '{sport_input}' ({tz_input}).")
                            st.rerun()
                        except: st.error("Failed. Verify this code isn't a duplicate.")
                            
        with admin_tab2:
            st.markdown("### Active Configurations Registry")
            all_configs = conn.query("SELECT id, sport, court_count, access_code, timezone FROM tennis_court_configurations ORDER BY id DESC", ttl=0)
            if not all_configs.empty:
                for _, row in all_configs.iterrows():
                    c_col1, c_col2 = st.columns([3, 1])
                    with c_col1: st.markdown(f"🔹 Code: **{row['access_code']}** | `{row['sport']}` | Courts: `{row['court_count']}` | TZ: `{row.get('timezone', 'Asia/Kolkata')}`")
                    with c_col2:
                        if st.button("Delete", key=f"del_code_{row['id']}", type="secondary", use_container_width=True):
                            with conn.session as s:
                                s.execute(text("DELETE FROM tennis_bookings WHERE sport=:sp"), {"sp": row['sport']})
                                s.execute(text("DELETE FROM tennis_court_configurations WHERE id=:id"), {"id": row['id']})
                                s.commit()
                            st.rerun()
            else: st.info("No customized rules provisioned.")
                
        with admin_tab3:
            st.markdown("### User Accounts Management")
            total_users = conn.query("SELECT COUNT(*) as count FROM tennis_users", ttl=0).iloc[0]['count']
            st.write(f"Total Users: {total_users}")
            all_users = conn.query("SELECT username FROM tennis_users", ttl=0)
            if not all_users.empty:
                for _, row in all_users.iterrows():
                    u = row["username"]
                    if u == "admin": continue
                    u_col1, u_col2 = st.columns([3, 1])
                    with u_col1: st.write(f"👤 **{u}**")
                    with u_col2:
                        if st.button("Delete Account", key=f"del_user_{u}", type="secondary", use_container_width=True):
                            with conn.session as s:
                                s.execute(text("DELETE FROM tennis_users WHERE username=:u"), {"u": u})
                                s.execute(text("DELETE FROM tennis_bookings WHERE username=:u"), {"u": u})
                                s.execute(text("DELETE FROM tennis_sessions WHERE username=:u"), {"u": u})
                                s.commit()
                            st.rerun()
            else: st.info("No accounts found.")
                
        with admin_tab4:
            st.markdown("### Global System Bookings")
            all_bookings = conn.query("SELECT id, username, booking_date, slot, court_number, sport FROM tennis_bookings ORDER BY booking_date DESC, slot ASC", ttl=0)
            st.write(f"Total Bookings: {len(all_bookings)}")
            if not all_bookings.empty:
                for _, row in all_bookings.iterrows():
                    b_col1, b_col2 = st.columns([3, 1])
                    with b_col1: st.write(f"👤 {row['username']} | 📅 {row['booking_date']} | ⏰ {row['slot']} | 🏟️ Court {row.get('court_number',1)} ({row.get('sport','Badminton')})")
                    with b_col2:
                        if st.button("Cancel", key=f"admin_cancel_{row['id']}", type="secondary", use_container_width=True):
                            with conn.session as s:
                                s.execute(text("DELETE FROM tennis_bookings WHERE id=:id"), {"id": row['id']})
                                s.commit()
                            st.rerun()
            else: st.info("No bookings registered.")
        st.markdown("---")

    # -------- GATEWAY WALL -------- #
    if st.session_state.court_config is None:
        st.title(f"{dynamic_icon} {dynamic_title}")
        st.subheader("🔒 Target Access Code Required")
        st.info("Please supply an active facility code to open the scheduler.")
        
        with st.form("gate_access_form"):
            entered_code = st.text_input("Enter Configuration Code").strip()
            remember_code = st.checkbox("Remember this code")
            if st.form_submit_button("Authenticate"):
                match = conn.query("SELECT sport, court_count, timezone FROM tennis_court_configurations WHERE access_code=:ac", params={"ac": entered_code}, ttl=0)
                if not match.empty:
                    config_tz = match.iloc[0].get("timezone", "Asia/Kolkata")
                    st.session_state.court_config = {
                        "sport": match.iloc[0]["sport"],
                        "court_count": int(match.iloc[0]["court_count"]),
                        "access_code": entered_code,
                        "timezone": config_tz
                    }
                    st.session_state.app_tz = config_tz
                    
                    if remember_code and cookie_manager:
                        try: cookie_manager.set(cookie="stadium_access_code", val=entered_code, expires_at=datetime.now() + pd.Timedelta(days=30))
                        except: pass
                    st.success(f"Authorized for: **{st.session_state.court_config['sport']}**")
                    st.rerun()
                else: st.error("Invalid configuration credentials.")
        st.stop()

    # -------- DYNAMIC SCHEDULER -------- #
    current_sport = st.session_state.court_config["sport"]
    total_courts = st.session_state.court_config["court_count"]

    st.title(f"{dynamic_icon} {dynamic_title}")
    st.markdown(f"### Bounded Workspace: **{current_sport}** (`{st.session_state.app_tz}` Time)")

    today = datetime.now(current_tz_info).date()
    tomorrow = today + timedelta(days=1)
    selected_date = st.radio("Choose Booking Day", [today, tomorrow], format_func=lambda x: x.strftime("%A %d %B"))

    slots = []
    start = datetime.strptime("00:00", "%H:%M")
    end = datetime.strptime("23:59", "%H:%M")
    now_ist = datetime.now(current_tz_info)

    while start < end:
        slot_str = start.strftime("%I:%M %p")
        if selected_date == today:
            if start.time() > now_ist.time(): slots.append(slot_str)
        else: slots.append(slot_str)
        start += timedelta(minutes=30)

    court_tabs = st.tabs([f"🏟️ Court #{c}" for c in range(1, total_courts + 1)])

    for court_idx in range(1, total_courts + 1):
        with court_tabs[court_idx - 1]:
            booked = conn.query("SELECT slot FROM tennis_bookings WHERE booking_date=:d AND court_number=:cn AND sport=:sp", 
                                params={"d": str(selected_date), "cn": court_idx, "sp": current_sport}, ttl=0)
            booked_slots = booked["slot"].tolist() if not booked.empty else []

            yours = conn.query("SELECT slot FROM tennis_bookings WHERE username=:u AND booking_date=:d AND court_number=:cn AND sport=:sp", 
                               params={"u": st.session_state.username, "d": str(selected_date), "cn": court_idx, "sp": current_sport}, ttl=0)
            your_slots = yours["slot"].tolist() if not yours.empty else []

            st.markdown("🟩 Available  |  🟥 Booked  |  🟦 Yours")
            cols = st.columns(4)

            for i, slot in enumerate(slots):
                with cols[i % 4]:
                    if slot in your_slots: st.info(f"🟦 {slot}")
                    elif slot in booked_slots: st.error(f"🟥 {slot}")
                    else:
                        if st.button(f"🟩 {slot}", key=f"s_{slot}_c{court_idx}"):
                            check = conn.query("SELECT slot FROM tennis_bookings WHERE booking_date=:d AND slot=:s AND court_number=:cn AND sport=:sp", 
                                               params={"d": str(selected_date), "s": slot, "cn": court_idx, "sp": current_sport}, ttl=0)
                            if not check.empty: st.error("Slot just claimed!")
                            else:
                                count = conn.query("SELECT COUNT(*) as count FROM tennis_bookings WHERE username=:u AND booking_date=:d", 
                                                   params={"u": st.session_state.username, "d": str(selected_date)}, ttl=0).iloc[0]['count']
                                if count >= 3 and st.session_state.username != "admin": st.error("Daily limit reached (Max 3/day).")
                                else:
                                    with conn.session as s:
                                        s.execute(text("INSERT INTO tennis_bookings (username, booking_date, slot, court_number, sport) VALUES (:u, :d, :s, :cn, :sp)"),
                                                  {"u": st.session_state.username, "d": str(selected_date), "s": slot, "cn": court_idx, "sp": current_sport})
                                        s.commit()
                                    st.success(f"Booked {slot} on Court #{court_idx}!")
                                    st.rerun()

    # -------- YOUR BOOKINGS -------- #
    st.subheader(f"Your Bookings for {current_sport}")
    user_bks = conn.query("SELECT id, booking_date, slot, court_number, sport FROM tennis_bookings WHERE username=:u AND sport=:sp ORDER BY booking_date DESC, slot ASC", 
                          params={"u": st.session_state.username, "sp": current_sport}, ttl=0)

    if not user_bks.empty:
        for _, row in user_bks.iterrows():
            col1, col2 = st.columns([3, 1])
            with col1: st.write(f"📌 {row['booking_date']} at {row['slot']} (Court #{row.get('court_number', 1)})")
            with col2:
                if st.button("Cancel", key=f"cancel_{row['id']}", use_container_width=True):
                    with conn.session as s:
                        s.execute(text("DELETE FROM tennis_bookings WHERE id=:id"), {"id": row['id']})
                        s.commit()
                    st.rerun()
    else: st.write("No reservations yet.")