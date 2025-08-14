import streamlit as st
import sqlite3
import pandas as pd

# -------------------------------
# SQLite Connection
# -------------------------------
DB_PATH = "user_conversations.db"

def run_query(query, params=()):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def execute_query(query, params=()):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(query, params)
    conn.commit()
    conn.close()

# -------------------------------
# Admin Login
# -------------------------------
st.set_page_config(page_title="TensAI Admin Dashboard", layout="wide", page_icon="📜")

st.image("logo.png", width=150) 

st.title("🔐 TensAI Chatbot Admin Dashboard")

 

ADMIN_USER = "Your_Username"
ADMIN_PASS = "Your_Password"  

# Simple login form
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
        if submitted:
            if username == ADMIN_USER and password == ADMIN_PASS:
                st.session_state.logged_in = True
                st.success("✅ Logged in successfully!")
            else:
                st.error("❌ Invalid credentials")
    st.stop()

# -------------------------------
# Refresh Button
# -------------------------------
if st.button("🔄 Refresh Data"):
    st.rerun()

# -------------------------------
# Dashboard Tabs
# -------------------------------
tab1, tab2, tab3 = st.tabs(["👤 Users", "💬 Conversations", "🗑 Delete"])

with tab1:
    st.subheader("Registered Users")
    users_df = run_query("SELECT * FROM users ORDER BY created_at DESC")
    st.dataframe(users_df, use_container_width=True)

with tab2:
    st.subheader("Conversation History")
    conv_df = run_query("""
        SELECT c.id, c.user_id, u.username, u.phone_number, u.email,
               c.question, c.answer, c.timestamp
        FROM conversations c
        LEFT JOIN users u ON c.user_id = u.user_id
        ORDER BY c.timestamp DESC
    """)
    st.dataframe(conv_df, use_container_width=True)

    # Search/Filter
    search_term = st.text_input("🔍 Search conversations (by username, phone, or question)")
    if search_term:
        filtered = conv_df[
            conv_df["username"].str.contains(search_term, case=False, na=False) |
            conv_df["phone_number"].str.contains(search_term, case=False, na=False) |
            conv_df["question"].str.contains(search_term, case=False, na=False) |
            conv_df["answer"].str.contains(search_term, case=False, na=False)
        ]
        st.dataframe(filtered, use_container_width=True)

with tab3:
    st.subheader("🗑 Delete Conversations & Users")
    delete_mode = st.radio("Delete by:", ["User UUID", "Username"])

    if delete_mode == "User UUID":
        user_uuid = st.text_input("Enter User UUID")
        if st.button("Delete by UUID"):
            if user_uuid:
                conn = sqlite3.connect(DB_PATH)
                cur = conn.cursor()
                try:
                    cur.execute("DELETE FROM conversations WHERE user_id = ?", (user_uuid,))
                    cur.execute("DELETE FROM users WHERE user_id = ?", (user_uuid,))
                    conn.commit()
                    st.success(f"✅ Deleted user and conversations for User UUID: {user_uuid}")
                except Exception as e:
                    st.error(f"❌ Error deleting: {e}")
                finally:
                    conn.close()
            else:
                st.warning("⚠ Please enter a valid UUID.")

    elif delete_mode == "Username":
        username = st.text_input("Enter Username")
        if st.button("Delete by Username"):
            if username:
                conn = sqlite3.connect(DB_PATH)
                cur = conn.cursor()
                try:
                    # First get the user's UUID from username
                    cur.execute("SELECT user_id FROM users WHERE username = ?", (username,))
                    result = cur.fetchone()
                    if result:
                        user_uuid = result[0]
                        cur.execute("DELETE FROM conversations WHERE user_id = ?", (user_uuid,))
                        cur.execute("DELETE FROM users WHERE user_id = ?", (user_uuid,))
                        conn.commit()
                        st.success(f"✅ Deleted user and conversations for Username: {username}")
                    else:
                        st.warning("⚠ Username not found.")
                except Exception as e:
                    st.error(f"❌ Error deleting: {e}")
                finally:
                    conn.close()
            else:
                st.warning("⚠ Please enter a valid username.")


