import streamlit as st
import sqlite3
import bcrypt
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo  # Built-in timezone support (Python 3.9+)

st.set_page_config(
    page_title="Booking Scheduler",
    page_icon="📅",
    layout="wide"
)

# Define IST Timezone
IST = ZoneInfo("Asia/Kolkata")

# ---------------- DATABASE ---------------- #

conn = sqlite3.connect(
    "database.db",
    check_same_thread=False
)

c = conn.cursor()

# Users table
c.execute("""
CREATE TABLE IF NOT EXISTS users (
    username TEXT,
    password BLOB
)
""")

# Bookings table
c.execute("""
CREATE TABLE IF NOT EXISTS bookings (
    username TEXT,
    booking_date TEXT,
    slot TEXT
)
""")

conn.commit()

# ---------------- REMOVE EXPIRED BOOKINGS ---------------- #

# Fetch current time in IST
now = datetime.now(IST)

c.execute("""
SELECT rowid, booking_date, slot
FROM bookings
""")

all_bookings = c.fetchall()

for booking in all_bookings:
    rowid = booking[0]
    booking_date = booking[1]
    slot = booking[2]

    # Parse and explicitly attach the IST timezone to the database record
    booking_datetime = datetime.strptime(
        f"{booking_date} {slot}",
        "%Y-%m-%d %I:%M %p"
    ).replace(tzinfo=IST)

    # Remove expired bookings securely comparing aware datetimes
    if booking_datetime < now:
        c.execute(
            "DELETE FROM bookings WHERE rowid=?",
            (rowid,)
        )

conn.commit()

# ---------------- SESSION ---------------- #

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "username" not in st.session_state:
    st.session_state.username = ""

# ---------------- TITLE ---------------- #

st.title("📅 Badminton Court Booking Scheduler")

# ---------------- LOGIN / SIGNUP ---------------- #

if not st.session_state.logged_in:

    menu = st.selectbox(
        "Menu",
        ["Login", "Sign Up"]
    )

    # Dynamically changing the keys based on 'menu' forces Streamlit 
    # to completely recreate clean inputs when switching modes.
    username = st.text_input("Username", key=f"user_{menu}").strip()
    password = st.text_input("Password", type="password", key=f"pass_{menu}")

    # -------- SIGN UP -------- #

    if menu == "Sign Up":

        if st.button("Create Account"):
            if not username or not password:
                st.error("Please fill in all fields.")
            else:
                c.execute(
                    "SELECT * FROM users WHERE username=?",
                    (username,)
                )

                existing = c.fetchone()

                if existing:
                    st.error("Username already exists")
                else:
                    c.execute(
                        """
                        INSERT INTO users
                        VALUES (?, ?)
                        """,
                        (
                            username,
                            bcrypt.hashpw(
                                password.encode(),
                                bcrypt.gensalt()
                            )
                        )
                    )
                    conn.commit()
                    st.success("Account created! You can now switch to Login.")

    # -------- LOGIN -------- #

    else:

        if st.button("Login"):

            c.execute(
                """
                SELECT * FROM users
                WHERE username=?
                """,
                (username,)
            )

            user = c.fetchone()

            if user:
                stored_password = user[1]

                if bcrypt.checkpw(
                    password.encode(),
                    stored_password
                ):
                    st.session_state.logged_in = True
                    st.session_state.username = username
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
                    # Fetch current stored password hash
                    c.execute("SELECT password FROM users WHERE username=?", (st.session_state.username,))
                    user_data = c.fetchone()
                    
                    if user_data and bcrypt.checkpw(current_password.encode(), user_data[0]):
                        # Hash the new password and update database record
                        new_hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt())
                        c.execute(
                            "UPDATE users SET password=? WHERE username=?", 
                            (new_hashed, st.session_state.username)
                        )
                        conn.commit()
                        st.success("Password changed successfully!")
                    else:
                        st.error("Incorrect current password.")

    # -------- ADMIN PANEL -------- #

    if st.session_state.username == "admin":

        st.subheader("👑 Admin Panel")

        c.execute("SELECT COUNT(*) FROM users")
        total_users = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM bookings")
        total_bookings = c.fetchone()[0]

        st.write(f"Total Users: {total_users}")
        st.write(f"Total Bookings: {total_bookings}")

        # -------- USER MANAGEMENT PANEL -------- #
        st.subheader("👥 User Accounts Management")
        
        c.execute("SELECT username FROM users")
        all_users = [row[0] for row in c.fetchall()]
        
        if all_users:
            for user_to_manage in all_users:
                # Prevent the admin from deleting their own admin account
                if user_to_manage == "admin":
                    continue
                    
                u_col1, u_col2 = st.columns([3, 1])
                with u_col1:
                    st.write(f"👤 User: **{user_to_manage}**")
                with u_col2:
                    if st.button("Delete Account", key=f"del_user_{user_to_manage}", type="secondary"):
                        # Delete user account record
                        c.execute("DELETE FROM users WHERE username=?", (user_to_manage,))
                        # Cascade delete user bookings so they don't block slots forever
                        c.execute("DELETE FROM bookings WHERE username=?", (user_to_manage,))
                        conn.commit()
                        st.success(f"Account '{user_to_manage}' and active bookings cleared successfully.")
                        st.rerun()
        else:
            st.info("No user accounts found.")

        # -------- VIEW ALL BOOKINGS -------- #

        c.execute("""
        SELECT username, booking_date, slot
        FROM bookings
        ORDER BY booking_date
        """)

        all_data = c.fetchall()

        st.subheader("📋 All Bookings")

        for item in all_data:
            st.write(f"{item[0]} | {item[1]} | {item[2]}")

    # -------- DATE CHOICE -------- #

    # Fetch today's date based precisely on IST time
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

    # Get the current time in IST to filter past slots out
    now_ist = datetime.now(IST)

    while start < end:
        slot_str = start.strftime("%I:%M %p")

        # Hide past slots today based on India Time
        if selected_date == today:
            if start.time() > now_ist.time():
                slots.append(slot_str)
        else:
            slots.append(slot_str)

        start += timedelta(minutes=30)

    # -------- GET BOOKED SLOTS -------- #

    c.execute(
        """
        SELECT slot
        FROM bookings
        WHERE booking_date=?
        """,
        (str(selected_date),)
    )

    booked_slots = [x[0] for x in c.fetchall()]

    # -------- GET YOUR SLOTS -------- #

    c.execute(
        """
        SELECT slot
        FROM bookings
        WHERE username=?
        AND booking_date=?
        """,
        (st.session_state.username, str(selected_date))
    )

    your_slots = [x[0] for x in c.fetchall()]

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

            # YOUR SLOT
            if slot in your_slots:
                st.info(f"🟦 {slot}")

            # BOOKED SLOT
            elif slot in booked_slots:
                st.error(f"🟥 {slot}")

            # AVAILABLE SLOT
            else:
                if st.button(f"🟩 {slot}", key=f"slot_{slot}"):

                    # Double-check slot
                    c.execute(
                        """
                        SELECT *
                        FROM bookings
                        WHERE booking_date=?
                        AND slot=?
                        """,
                        (str(selected_date), slot)
                    )

                    already_booked = c.fetchone()

                    if already_booked:
                        st.error("Slot already booked")
                    else:
                        # Count bookings for THIS DAY
                        c.execute(
                            """
                            SELECT COUNT(*)
                            FROM bookings
                            WHERE username=?
                            AND booking_date=?
                            """,
                            (st.session_state.username, str(selected_date))
                        )

                        booking_count = c.fetchone()[0]

                        # Max 3 bookings per day
                        if booking_count >= 3:
                            st.error("Maximum 3 bookings per day")
                        else:
                            c.execute(
                                """
                                INSERT INTO bookings
                                VALUES (?, ?, ?)
                                """,
                                (st.session_state.username, str(selected_date), slot)
                            )

                            conn.commit()
                            st.success(f"Booked {slot}")
                            st.rerun()

    # -------- USER BOOKINGS -------- #

    st.subheader("Your Bookings")

    c.execute(
        """
        SELECT rowid, booking_date, slot
        FROM bookings
        WHERE username=?
        ORDER BY booking_date, slot
        """,
        (st.session_state.username,)
    )

    user_bookings = c.fetchall()

    if user_bookings:

        for booking in user_bookings:
            rowid = booking[0]
            booking_date_str = booking[1]
            slot = booking[2]

            col1, col2 = st.columns([3, 1])

            with col1:
                st.write(f"📌 {booking_date_str} at {slot}")

            with col2:
                if st.button("Cancel", key=f"cancel_{rowid}"):
                    c.execute(
                        """
                        DELETE FROM bookings
                        WHERE rowid=?
                        """,
                        (rowid,)
                    )

                    conn.commit()
                    st.success("Booking cancelled")
                    st.rerun()
    else:
        st.write("No bookings yet")

    # -------- LOGOUT -------- #
    st.divider()
    if st.button("Logout", type="primary"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.rerun()