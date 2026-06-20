import streamlit as st
import secrets  # For generating cryptographically secure session tokens
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo  # Built-in timezone support (Python 3.9+)
import hashlib
from sqlalchemy import text
import pandas as pd
import extra_streamlit_components as stx

st.set_page_config(
    page_title="Multi-Sport Arena Scheduler",
    page_icon="🏸",
    layout="wide"
)

# Define IST Timezone
IST = ZoneInfo("Asia/Kolkata")

# ---------------- DATABASE CONNECTION ---------------- #

conn = st.connection("postgresql", type="sql")


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

# Fetch current time in IST
now = datetime.now(IST)

# Fetch directly from Supabase using conn.query
all_bookings_df = conn.query("SELECT id, booking_date, slot FROM tennis_bookings", ttl=0)

if not all_bookings_df.empty:
    with conn.session as session:
        for _, row in all_bookings_df.iterrows():
            bid = int(row['id'])
            b_date = row['booking_date']
            b_slot = row['slot']

            try:
                # Parse and explicitly attach the IST timezone to the database record
                booking_datetime = datetime.strptime(
                    f"{b_date} {b_slot}",
                    "%Y-%m-%d %I:%M %p"
                ).replace(tzinfo=IST)

                # Remove expired bookings securely comparing aware datetimes
                if booking_datetime < now:
                    session.execute(text("DELETE FROM tennis_bookings WHERE id=:id"), {"id": bid})
            except Exception:
                pass
        session.commit()

# ---------------- BASELINE STATE INITIALIZATION ---------------- #

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "username" not in st.session_state:
    st.session_state.username = ""

if "court_config" not in st.session_state:
    st.session_state.court_config = None  # Tracks dynamic dictionary maps: {"sport", "court_count", "access_code"}

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
            else:
                # Clean up invalid or tampered client cookies safely
                cookie_manager.delete(cookie="badminton_scheduler_token")
    except Exception:
        pass

# Ensure URL parameter hacks are completely locked down
st.query_params.clear()

# ---------------- TITLE ---------------- #

st.title(" Stadium Management Portal")

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
                        current_timestamp = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
                        
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

# ---------------- MAIN APP ---------------- #

else:

    st.success(
        f"Logged in as {st.session_state.username}"
    )

    # -------- PASSWORD CHANGING SYSTEM -------- #
    with st.expander("👤 Account Security"):
        st.subheader("Change Password")
        with st.form("change_password_form", clear_on_submit=True):
            current_password = st.text_input("Current Password", type="password")
            new_password = st.text_input("New Password", type="password")
            confirm_password = st.text_input("Confirm New Password", type="password")
            submit_change = st.form_submit_button("Update Password")

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

    # -------- ADMIN PANEL -------- #

    if st.session_state.username == "admin":

        st.subheader("👑 Admin Configurator Dashboard")

        # CONFIGURABLE CODE INTAKE ENGINE
        st.markdown("### ⚙️ Create Custom Access Code & Facility Mapping")
        with st.form("admin_access_code_form", clear_on_submit=True):
            sport_input = st.text_input("Sport / Facility Category Name", placeholder="e.g., Football, Squash, Swimming").strip()
            courts_input = st.number_input("Total Courts / Fields Configured", min_value=1, max_value=24, value=2)
            code_input = st.text_input("Unique System Entry Code").strip()
            submit_config = st.form_submit_button("Deploy Scheduler Configuration")

            if submit_config:
                if not sport_input or not code_input:
                    st.error("All configuration parameters are strictly required.")
                else:
                    try:
                        current_ts = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
                        with conn.session as session:
                            session.execute(
                                text("INSERT INTO tennis_court_configurations (sport, court_count, access_code, created_at) VALUES (:s, :cc, :ac, :cat)"),
                                {"s": sport_input, "cc": courts_input, "ac": code_input, "cat": current_ts}
                            )
                            session.commit()
                        st.success(f"Deployed! Code '{code_input}' dynamically generates a {courts_input}-court setup for '{sport_input}'.")
                        st.rerun()
                    except Exception:
                        st.error("Failed to deploy rules. Verify this access code isn't a duplicate registry item.")

        st.write("---")

        total_users = conn.query("SELECT COUNT(*) as count FROM tennis_users", ttl=0).iloc[0]['count']
        total_bookings = conn.query("SELECT COUNT(*) as count FROM tennis_bookings", ttl=0).iloc[0]['count']

        st.write(f"Total Users: {total_users}")
        st.write(f"Total Bookings: {total_bookings}")

        # -------- ADMIN SETTINGS LOG REGISTRY WITH DELETE CONTROLS -------- #
        st.subheader("🔑 Active Configurations Registry & Deletion")
        all_configs_df = conn.query("SELECT id, sport, court_count, access_code FROM tennis_court_configurations ORDER BY id DESC", ttl=0)
        
        if not all_configs_df.empty:
            for _, cfg_row in all_configs_df.iterrows():
                cfg_id = int(cfg_row["id"])
                cfg_sport = cfg_row["sport"]
                cfg_courts = cfg_row["court_count"]
                cfg_code = cfg_row["access_code"]
                
                c_col1, c_col2 = st.columns([3, 1])
                with c_col1:
                    st.markdown(f" Code Key: **{cfg_code}** | Sport: `{cfg_sport}` | Courts: `{cfg_courts}`")
                with c_col2:
                    if st.button("Delete Code Rule", key=f"del_code_{cfg_id}", type="secondary"):
                        with conn.session as session:
                            session.execute(text("DELETE FROM tennis_court_configurations WHERE id=:id"), {"id": cfg_id})
                            session.commit()
                        st.success(f"Configuration configuration key '{cfg_code}' deleted from system databases.")
                        st.rerun()
        else:
            st.info("No customized setup rules have been provisioned by the admin yet.")

        # -------- USER MANAGEMENT PANEL -------- #
        st.subheader("👥 User Accounts Management")
        
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

        # -------- VIEW ALL GLOBAL APP RESERVATIONS -------- #
        st.subheader("📋 All Global Court Bookings")
        all_data_df = conn.query("SELECT username, booking_date, slot, court_number, sport FROM tennis_bookings ORDER BY booking_date DESC, slot ASC", ttl=0)

        if not all_data_df.empty:
            for _, row in all_data_df.iterrows():
                court_lbl = f"Court {row.get('court_number', 1)}"
                sport_lbl = row.get('sport', 'Badminton')
                st.write(f"👤 {row['username']} | 📅 {row['booking_date']} | ⏰ {row['slot']} | 🏟️ {court_lbl} ({sport_lbl})")
        else:
            st.info("No bookings registered yet.")

    # -------- MANDATORY GATEWAY WALL: FORCES DYNAMIC SYSTEM ISOLATION VIA ACCESS CODES -------- #
    elif st.session_state.court_config is None:
        st.subheader("🔒 Target Access Code Required")
        st.info("Please supply an active facility code to dynamically open your scheduler view panels.")
        
        with st.form("gate_access_form"):
            entered_code = st.text_input("Enter Configuration Code").strip()
            submit_gate = st.form_submit_button("Authenticate & Open Scheduler")
            
            if submit_gate:
                match_df = conn.query("SELECT sport, court_count FROM tennis_court_configurations WHERE access_code=:ac", params={"ac": entered_code}, ttl=0)
                if not match_df.empty:
                    st.session_state.court_config = {
                        "sport": match_df.iloc[0]["sport"],
                        "court_count": int(match_df.iloc[0]["court_count"]),
                        "access_code": entered_code
                    }
                    st.success(f"Authorized! Opening your customized workspace for: **{st.session_state.court_config['sport']}**")
                    st.rerun()
                else:
                    st.error("Invalid configuration credentials. Please double-check your code or consult your system administrator.")

    # -------- DYNAMIC SCHEDULER BOARD IMPLEMENTATION -------- #
    if st.session_state.username == "admin" or st.session_state.court_config is not None:
        
        # Admin gets global baseline override view, users get their perfectly isolated setup rules
        if st.session_state.username == "admin":
            current_sport = "Global Admin View Manager"
            total_courts_to_render = 1
        else:
            current_sport = st.session_state.court_config["sport"]
            total_courts_to_render = st.session_state.court_config["court_count"]

        st.markdown(f"## 🎯 Dynamic Workspace: **{current_sport}**")
        if st.session_state.username != "admin":
            if st.button("🔄 Change Session Access Code"):
                st.session_state.court_config = None
                st.rerun()

        # -------- DATE CHOICE -------- #

        today = datetime.now(IST).date()
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

        now_ist = datetime.now(IST)

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
                st.markdown("🟩 Available  |  🟥 Booked  |  %s" % ("🟦 Yours" if st.session_state.username != "admin" else "🟦 Admin"))

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

        # -------- DISPLAY WORKSPACE-ISOLATED ACCORDION RESERVATIONS -------- #
        st.subheader(f"Your Bookings for {current_sport}")

        if st.session_state.username == "admin":
            user_bookings_df = conn.query("SELECT id, booking_date, slot, court_number, sport FROM tennis_bookings WHERE username=:u ORDER BY booking_date DESC, slot ASC", 
                                          params={"u": st.session_state.username}, ttl=0)
        else:
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

    # -------- LOGOUT HANDSHAKE ENGINE -------- #
    st.divider()
    if st.button("Logout", type="primary"):
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
        
        # Flush configurations clean from active memory state maps to break cycle deadlocks
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.court_config = None
        st.query_params.clear()
        st.rerun()