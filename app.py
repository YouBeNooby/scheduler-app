import streamlit as st
import secrets  # For generating cryptographically secure session tokens
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo  # Built-in timezone support (Python 3.9+)
import hashlib
from sqlalchemy import text

st.set_page_config(
    page_title="Booking Scheduler",
    page_icon="📅",
    layout="wide"
)

# Define IST Timezone
IST = ZoneInfo("Asia/Kolkata")

# ---------------- DATABASE CONNECTION ---------------- #

conn = st.connection("postgresql", type="sql")


def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()


# Initialize Tables on Supabase
def init_db():
    with conn.session as session:
        # Users table (Storing hashed passwords as TEXT for Postgres compliance)
        session.execute(text("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
        """))

        # Bookings table
        session.execute(text("""
        CREATE TABLE IF NOT EXISTS bookings (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL,
            booking_date TEXT NOT NULL,
            slot TEXT NOT NULL
        )
        """))

        # Persistent Session Tokens table
        session.execute(text("""
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """))
        session.commit()

        # -------- AUTOMATIC ADMIN ACCOUNT GENERATION & ENFORCEMENT -------- #
        hashed_admin_password = make_hashes("LeBakri!!18")
        
        try:
            res = session.execute(text("SELECT username FROM users WHERE username = 'admin'")).fetchone()
            if res:
                session.execute(text("UPDATE users SET password=:p WHERE username='admin'"), {"p": hashed_admin_password})
            else:
                session.execute(text("INSERT INTO users (username, password) VALUES (:u, :p)"), {"u": "admin", "p": hashed_admin_password})
            session.commit()
        except Exception:
            session.rollback()


# Trigger initial table check on startup
init_db()

# ---------------- REMOVE EXPIRED BOOKINGS & SESSIONS ---------------- #

# Fetch current time in IST
now = datetime.now(IST)

# Fetch directly from Supabase using conn.query
all_bookings_df = conn.query("SELECT id, booking_date, slot FROM bookings", ttl=0)

if not all_bookings_df.empty:
    with conn.session as session:
        for _, row in all_bookings_df.iterrows():
            bid = int(row['id'])
            b_date = row['booking_date']
            b_slot = row['slot']

            # Parse and explicitly attach the IST timezone to the database record
            booking_datetime = datetime.strptime(
                f"{b_date} {b_slot}",
                "%Y-%m-%d %I:%M %p"
            ).replace(tzinfo=IST)

            # Remove expired bookings securely comparing aware datetimes
            if booking_datetime < now:
                session.execute(text("DELETE FROM bookings WHERE id=:id"), {"id": bid})
        session.commit()

# ---------------- SECURE AUTOMATIC LOGIN INTERCEPTOR ---------------- #

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "username" not in st.session_state:
    st.session_state.username = ""

# If the browser URL contains a token and the session isn't loaded yet, try to auto-login
if "token" in st.query_params and not st.session_state.logged_in:
    url_token = st.query_params["token"]
    
    session_df = conn.query("SELECT username FROM sessions WHERE token=:t", params={"t": url_token}, ttl=0)
    
    if not session_df.empty:
        saved_username = session_df.iloc[0]["username"]
        # Extra verification step: Check if the user record still exists in the user registry
        user_check_df = conn.query("SELECT username FROM users WHERE username=:u", params={"u": saved_username}, ttl=0)
        if not user_check_df.empty:
            st.session_state.logged_in = True
            st.session_state.username = saved_username
    else:
        # Clean up stale or altered invalid tokens from the URL string
        st.query_params.clear()

# ---------------- TITLE ---------------- #

st.title("📅 Badminton Court Booking Scheduler")

# ---------------- LOGIN / SIGNUP ---------------- #

if not st.session_state.logged_in:

    menu = st.selectbox(
        "Menu",
        ["Login", "Sign Up"]
    )

    username = st.text_input("Username", key=f"user_{menu}").strip()
    password = st.text_input("Password", type="password", key=f"pass_{menu}")
    
    remember_me = st.checkbox("Keep me logged in", key=f"remember_{menu}")

    # -------- SIGN UP -------- #

    if menu == "Sign Up":

        if st.button("Create Account"):
            if not username or not password:
                st.error("Please fill in all fields.")
            elif username.lower() == "admin":
                st.error("The username 'admin' is a reserved system identifier.")
            else:
                existing_df = conn.query("SELECT username FROM users WHERE username=:u", params={"u": username}, ttl=0)

                if not existing_df.empty:
                    st.error("Username already exists")
                else:
                    try:
                        with conn.session as session:
                            session.execute(
                                text("INSERT INTO users (username, password) VALUES (:u, :p)"),
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
            user_df = conn.query("SELECT username, password FROM users WHERE username=:u", params={"u": username}, ttl=0)

            if not user_df.empty:
                stored_password = user_df.iloc[0]["password"]

                if hashed_input == stored_password:
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    
                    if remember_me:
                        secure_token = secrets.token_urlsafe(32)
                        current_timestamp = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
                        
                        with conn.session as session:
                            session.execute(
                                text("INSERT INTO sessions (token, username, created_at) VALUES (:t, :u, :c)"),
                                {"t": secure_token, "u": username, "c": current_timestamp}
                            )
                            session.commit()
                        st.query_params["token"] = secure_token
                    
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
                    user_data_df = conn.query("SELECT password FROM users WHERE username=:u", params={"u": st.session_state.username}, ttl=0)
                    
                    if not user_data_df.empty and make_hashes(current_password) == user_data_df.iloc[0]["password"]:
                        new_hashed = make_hashes(new_password)
                        with conn.session as session:
                            session.execute(
                                text("UPDATE users SET password=:p WHERE username=:u"), 
                                {"p": new_hashed, "u": st.session_state.username}
                            )
                            session.commit()
                        st.success("Password changed successfully!")
                    else:
                        st.error("Incorrect current password.")

    # -------- ADMIN PANEL -------- #

    if st.session_state.username == "admin":

        st.subheader("👑 Admin Panel")

        total_users = conn.query("SELECT COUNT(*) as count FROM users", ttl=0).iloc[0]['count']
        total_bookings = conn.query("SELECT COUNT(*) as count FROM bookings", ttl=0).iloc[0]['count']

        st.write(f"Total Users: {total_users}")
        st.write(f"Total Bookings: {total_bookings}")

        # -------- USER MANAGEMENT PANEL -------- #
        st.subheader("👥 User Accounts Management")
        
        all_users_df = conn.query("SELECT username FROM users", ttl=0)
        
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
                            session.execute(text("DELETE FROM users WHERE username=:u"), {"u": user_to_manage})
                            session.execute(text("DELETE FROM bookings WHERE username=:u"), {"u": user_to_manage})
                            session.execute(text("DELETE FROM sessions WHERE username=:u"), {"u": user_to_manage})
                            session.commit()
                        st.success(f"Account '{user_to_manage}' and active bookings cleared successfully.")
                        st.rerun()
        else:
            st.info("No user accounts found.")

        # -------- VIEW ALL BOOKINGS -------- #

        all_data_df = conn.query("SELECT username, booking_date, slot FROM bookings ORDER BY booking_date", ttl=0)

        st.subheader("📋 All Bookings")

        if not all_data_df.empty:
            for _, row in all_data_df.iterrows():
                st.write(f"{row['username']} | {row['booking_date']} | {row['slot']}")
        else:
            st.info("No bookings registered yet.")

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

    # -------- GET BOOKED SLOTS -------- #

    booked_df = conn.query("SELECT slot FROM bookings WHERE booking_date=:d", params={"d": str(selected_date)}, ttl=0)
    booked_slots = booked_df["slot"].tolist() if not booked_df.empty else []

    # -------- GET YOUR SLOTS -------- #

    your_df = conn.query("SELECT slot FROM bookings WHERE username=:u AND booking_date=:d", 
                         params={"u": st.session_state.username, "d": str(selected_date)}, ttl=0)
    your_slots = your_df["slot"].tolist() if not your_df.empty else []

    # -------- SLOT LEGEND -------- #

    st.markdown("""
🟩 Available  
🟥 Booked  
🟦 Yours
""")

    # -------- SLOT UI -------- #

    st.subheader("Time Slots")

    cols = st.columns(4)

    for i, slot in enumerate(slots):

        with cols[i % 4]:

            if slot in your_slots:
                st.info(f"🟦 {slot}")

            elif slot in booked_slots:
                st.error(f"🟥 {slot}")

            else:
                if st.button(f"🟩 {slot}", key=f"slot_{slot}"):

                    # Double-check slot
                    check_df = conn.query("SELECT slot FROM bookings WHERE booking_date=:d AND slot=:s", 
                                          params={"d": str(selected_date), "s": slot}, ttl=0)

                    if not check_df.empty:
                        st.error("Slot already booked")
                    else:
                        # Count bookings for THIS DAY
                        count_df = conn.query("SELECT COUNT(*) as count FROM bookings WHERE username=:u AND booking_date=:d", 
                                              params={"u": st.session_state.username, "d": str(selected_date)}, ttl=0)
                        booking_count = count_df.iloc[0]['count']

                        if booking_count >= 3:
                            st.error("Maximum 3 bookings per day")
                        else:
                            with conn.session as session:
                                session.execute(
                                    text("INSERT INTO bookings (username, booking_date, slot) VALUES (:u, :d, :s)"),
                                    {"u": st.session_state.username, "d": str(selected_date), "s": slot}
                                )
                                session.commit()
                            st.success(f"Booked {slot}")
                            st.rerun()

    # -------- USER BOOKINGS -------- #

    st.subheader("Your Bookings")

    user_bookings_df = conn.query("SELECT id, booking_date, slot FROM bookings WHERE username=:u ORDER BY booking_date, slot", 
                                  params={"u": st.session_state.username}, ttl=0)

    if not user_bookings_df.empty:
        for _, row in user_bookings_df.iterrows():
            bid = int(row['id'])
            booking_date_str = row['booking_date']
            slot = row['slot']

            col1, col2 = st.columns([3, 1])

            with col1:
                st.write(f"📌 {booking_date_str} at {slot}")

            with col2:
                if st.button("Cancel", key=f"cancel_{bid}"):
                    with conn.session as session:
                        session.execute(text("DELETE FROM bookings WHERE id=:id"), {"id": bid})
                        session.commit()
                    st.success("Booking cancelled")
                    st.rerun()
    else:
        st.write("No bookings yet")

    # -------- LOGOUT -------- #
    st.divider()
    if st.button("Logout", type="primary"):
        if "token" in st.query_params:
            with conn.session as session:
                session.execute(text("DELETE FROM sessions WHERE token=:t"), {"t": st.query_params["token"]})
                session.commit()
            
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.query_params.clear()
        st.rerun()