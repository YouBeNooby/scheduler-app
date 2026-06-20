import streamlit as st
from supabase import create_client, Client
import bcrypt
from datetime import datetime, date, time
from zoneinfo import ZoneInfo

# --- INITIALIZATION & SUPABASE CONNECTION ---
st.set_page_config(page_title="Court Scheduler", layout="wide")

# Replace these with your actual Streamlit Secrets or Environment Variables
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "https://your-supabase-url.supabase.co")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "your-anon-key")

@st.cache_resource
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()
IST = ZoneInfo("Asia/Kolkata")

# Initialize persistent session states
if "user" not in st.session_state:
    st.session_state.user = None  # Holds dict: {"id":..., "username":..., "role":...}
if "court_config" not in st.session_state:
    st.session_state.court_config = None  # Holds dict: {"sport":..., "court_count":...}

# --- HELPER FUNCTIONS ---
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def logout():
    st.session_state.user = None
    st.session_state.court_config = None
    st.rerun()

# --- AUTHENTICATION FLOW ---
def render_login_and_registration():
    st.title("🏸 Court Scheduler Login")
    tab1, tab2 = st.tabs(["Login", "Register"])
    
    with tab1:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log In")
            
            if submitted:
                res = supabase.table("users").select("*").eq("username", username).execute()
                if res.data:
                    user_data = res.data[0]
                    if check_password(password, user_data["password"]):
                        st.session_state.user = {
                            "id": user_data["id"],
                            "username": user_data["username"],
                            "role": user_data.get("role", "user")
                        }
                        st.success("Logged in successfully!")
                        st.rerun()
                    else:
                        st.error("Invalid password.")
                else:
                    st.error("Username not found.")
                    
    with tab2:
        with st.form("register_form"):
            new_user = st.text_input("New Username")
            new_pass = st.text_input("New Password", type="password")
            is_admin = st.checkbox("Register as Admin Account")
            register_submitted = st.form_submit_button("Register")
            
            if register_submitted:
                if not new_user or not new_pass:
                    st.error("Fields cannot be empty.")
                else:
                    hashed = hash_password(new_pass)
                    role = "admin" if is_admin else "user"
                    try:
                        supabase.table("users").insert({
                            "username": new_user,
                            "password": hashed,
                            "role": role
                        }).execute()
                        st.success("Account created! You can now log in.")
                    except Exception as e:
                        st.error("Username might already exist or table mismatch.")

# --- GATEWAY: ACCESS CODE VERIFICATION ---
def render_access_code_gate():
    st.title("🔒 Access Code Required")
    st.write(f"Welcome back, **{st.session_state.user['username']}**! Please enter your facility access code to view the scheduler.")
    
    with st.form("access_code_form"):
        code_input = st.text_input("Access Code", placeholder="e.g. MONSOON2026").strip()
        submit_code = st.form_submit_button("Verify & Enter")
        
        if submit_code:
            res = supabase.table("court_configurations").select("*").eq("access_code", code_input).execute()
            if res.data:
                config = res.data[0]
                st.session_state.court_config = {
                    "sport": config["sport"],
                    "court_count": config["court_count"]
                }
                st.success(f"Access granted for {config['sport']}!")
                st.rerun()
            else:
                st.error("Invalid access code. Please verify with your admin.")
                
    if st.button("Log Out"):
        logout()

# --- ADMIN DASHBOARD ---
def render_admin_dashboard():
    st.title("👑 Admin Control Panel")
    
    # 1. Section to Create Access Codes
    st.subheader("Create New Access Session")
    with st.form("create_code_form", clear_on_submit=True):
        sport = st.text_input("Sport / Event Name", placeholder="e.g., Badminton, Tennis")
        courts = st.number_input("Number of Configured Courts", min_value=1, max_value=16, value=1)
        new_code = st.text_input("Custom Access Code").strip()
        create_submit = st.form_submit_button("Generate Configuration & Code")
        
        if create_submit:
            if not sport or not new_code:
                st.error("All fields are required.")
            else:
                try:
                    supabase.table("court_configurations").insert({
                        "sport": sport,
                        "court_count": courts,
                        "access_code": new_code,
                        "created_by": st.session_state.user["id"]
                    }).execute()
                    st.success(f"Successfully generated code '{new_code}' for {sport} ({courts} courts)!")
                except Exception as e:
                    st.error("Error creating code. Ensure the code is unique.")

    st.write("---")
    
    # 2. Section to View Existing Access Codes
    st.subheader("Active Court Configurations & Access Codes")
    configs_res = supabase.table("court_configurations").select("*").order("created_at", desc=True).execute()
    
    if configs_res.data:
        # Render a clean comparison table for the admin
        st.table([{
            "Sport": c["sport"], 
            "Available Courts": c["court_count"], 
            "Access Code": c["access_code"],
            "Created At": c["created_at"][:10]
        } for c in configs_res.data])
    else:
        st.info("No access codes created yet.")

# --- USER SCHEDULER BOARD ---
def render_user_scheduler():
    config = st.session_state.court_config
    st.title(f"🏸 {config['sport']} Scheduler")
    st.subheader(f"Managing {config['court_count']} Active Court Columns")
    
    # Select Date
    selected_date = st.date_input("Select Booking Date", min_value=date.today())
    
    # Simple dynamic layout rendering: Create an interface layout spanning N courts
    columns = st.columns(config["court_count"])
    
    # Fetch existing bookings for this day to cross-check slots
    bookings_res = supabase.table("bookings").select("*").eq("booking_date", str(selected_date)).execute()
    booked_slots = set()
    if bookings_res.data:
        for b in bookings_res.data:
            # Storing tracking context as strings: "time_slot|court_number"
            booked_slots.add(f"{b['time_slot']}|{b.get('court_number', 1)}")

    # Standard available hour slots 
    time_slots = [f"{hour:02d}:00" for hour in range(6, 22)] # From 06:00 to 22:00 IST
    
    for court_index in range(config["court_count"]):
        court_num = court_index + 1
        with columns[court_index]:
            st.metric(label=f"Court Name / ID", value=f"Court #{court_num}")
            
            for t_slot in time_slots:
                slot_id = f"{t_slot}|{court_num}"
                is_taken = slot_id in booked_slots
                
                if is_taken:
                    st.button(f"🔒 {t_slot} (Booked)", key=f"btn_{slot_id}", disabled=True)
                else:
                    if st.button(f"🟢 Book {t_slot}", key=f"btn_{slot_id}"):
                        try:
                            # Insert into your bookings table
                            supabase.table("bookings").insert({
                                "user_id": st.session_state.user["id"],
                                "booking_date": str(selected_date),
                                "time_slot": t_slot,
                                "court_number": court_num,
                                "sport": config["sport"]
                            }).execute()
                            st.success(f"Booked Court {court_num} @ {t_slot}!")
                            st.rerun()
                        except Exception as e:
                            st.error("Booking error occurred.")

# --- CORE APPLICATION ROUTER ---
if st.session_state.user is None:
    render_login_and_registration()
else:
    # Sidebar Navigation & Context details
    with st.sidebar:
        st.write(f"👤 Account: **{st.session_state.user['username']}**")
        st.write(f"🛡️ Role: `{st.session_state.user['role'].upper()}`")
        if st.session_state.court_config:
            st.write(f"🎯 Session: **{st.session_state.court_config['sport']}**")
            
        if st.button("Log Out and Clear Session"):
            logout()
            
    # Check roles and branch execution
    if st.session_state.user["role"] == "admin":
        render_admin_dashboard()
    else:
        # If normal user is logged in, force them through the access code gate first
        if st.session_state.court_config is None:
            render_access_code_gate()
        else:
            render_user_scheduler()