import streamlit as st
import sqlite3
import bcrypt
from datetime import datetime, timedelta, date

st.set_page_config(
    page_title="Booking Scheduler",
    page_icon="📅",
    layout="wide"
)

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

now = datetime.now()

c.execute("""
SELECT rowid, booking_date, slot
FROM bookings
""")

all_bookings = c.fetchall()

for booking in all_bookings:

    rowid = booking[0]
    booking_date = booking[1]
    slot = booking[2]

    booking_datetime = datetime.strptime(
        f"{booking_date} {slot}",
        "%Y-%m-%d %I:%M %p"
    )

    # Remove expired bookings
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

st.title("📅 Booking Scheduler")

# ---------------- LOGIN / SIGNUP ---------------- #

if not st.session_state.logged_in:

    menu = st.selectbox(
        "Menu",
        ["Login", "Sign Up"]
    )

    username = st.text_input("Username")

    password = st.text_input(
        "Password",
        type="password"
    )

    # -------- SIGN UP -------- #

    if menu == "Sign Up":

        if st.button("Create Account"):

            c.execute(
                "SELECT * FROM users WHERE username=?",
                (username,)
            )

            existing = c.fetchone()

            if existing:

                st.error(
                    "Username already exists"
                )

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

                st.success(
                    "Account created!"
                )

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

                    st.error(
                        "Wrong password"
                    )

            else:

                st.error(
                    "User not found"
                )

# ---------------- MAIN APP ---------------- #

else:

    st.success(
        f"Logged in as {st.session_state.username}"
    )

    # -------- ADMIN PANEL -------- #

    if st.session_state.username == "admin":

        st.subheader("👑 Admin Panel")

        c.execute(
            "SELECT COUNT(*) FROM users"
        )

        total_users = c.fetchone()[0]

        c.execute(
            "SELECT COUNT(*) FROM bookings"
        )

        total_bookings = c.fetchone()[0]

        st.write(f"Total Users: {total_users}")
        st.write(f"Total Bookings: {total_bookings}")

        # -------- VIEW ALL BOOKINGS -------- #

        c.execute("""
        SELECT username, booking_date, slot
        FROM bookings
        ORDER BY booking_date
        """)

        all_data = c.fetchall()

        st.subheader("📋 All Bookings")

        for item in all_data:

            st.write(
                f"{item[0]} | {item[1]} | {item[2]}"
            )

    # -------- DATE CHOICE -------- #

    today = date.today()

    tomorrow = today + timedelta(days=1)

    selected_date = st.radio(
        "Choose Booking Day",
        [today, tomorrow],
        format_func=lambda x:
        x.strftime("%A %d %B")
    )

    # -------- GENERATE SLOTS -------- #

    slots = []

    start = datetime.strptime(
        "00:00",
        "%H:%M"
    )

    end = datetime.strptime(
        "23:59",
        "%H:%M"
    )

    now = datetime.now()

    while start < end:

        slot_str = start.strftime(
            "%I:%M %p"
        )

        # Hide past slots today
        if selected_date == today:

            if start.time() > now.time():

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

    booked_slots = [
        x[0] for x in c.fetchall()
    ]

    # -------- GET YOUR SLOTS -------- #

    c.execute(
        """
        SELECT slot
        FROM bookings
        WHERE username=?
        AND booking_date=?
        """,
        (
            st.session_state.username,
            str(selected_date)
        )
    )

    your_slots = [
        x[0] for x in c.fetchall()
    ]

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

                st.info(
                    f"🟦 {slot}"
                )

            # BOOKED SLOT
            elif slot in booked_slots:

                st.error(
                    f"🟥 {slot}"
                )

            # AVAILABLE SLOT
            else:

                if st.button(
                    f"🟩 {slot}",
                    key=f"slot_{slot}"
                ):

                    # Double-check slot
                    c.execute(
                        """
                        SELECT *
                        FROM bookings
                        WHERE booking_date=?
                        AND slot=?
                        """,
                        (
                            str(selected_date),
                            slot
                        )
                    )

                    already_booked = c.fetchone()

                    if already_booked:

                        st.error(
                            "Slot already booked"
                        )

                    else:

                        # Count bookings for THIS DAY
                        c.execute(
                            """
                            SELECT COUNT(*)
                            FROM bookings
                            WHERE username=?
                            AND booking_date=?
                            """,
                            (
                                st.session_state.username,
                                str(selected_date)
                            )
                        )

                        booking_count = c.fetchone()[0]

                        # Max 3 bookings per day
                        if booking_count >= 3:

                            st.error(
                                "Maximum 3 bookings per day"
                            )

                        else:

                            c.execute(
                                """
                                INSERT INTO bookings
                                VALUES (?, ?, ?)
                                """,
                                (
                                    st.session_state.username,
                                    str(selected_date),
                                    slot
                                )
                            )

                            conn.commit()

                            st.success(
                                f"Booked {slot}"
                            )

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
            booking_date = booking[1]
            slot = booking[2]

            col1, col2 = st.columns([3, 1])

            with col1:

                st.write(
                    f"📌 {booking_date} at {slot}"
                )

            with col2:

                if st.button(
                    "Cancel",
                    key=f"cancel_{rowid}"
                ):

                    c.execute(
                        """
                        DELETE FROM bookings
                        WHERE rowid=?
                        """,
                        (rowid,)
                    )

                    conn.commit()

                    st.success(
                        "Booking cancelled"
                    )

                    st.rerun()

    else:

        st.write(
            "No bookings yet"
        )

    # -------- LOGOUT -------- #

    if st.button("Logout"):

        st.session_state.logged_in = False
        st.session_state.username = ""

        st.rerun()