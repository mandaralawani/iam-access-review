# =============================================================================
# app.py
# =============================================================================
# PURPOSE: Streamlit web application — the front-end that ties everything
#          together. Loads the IAM data, scores it with the risk engine,
#          and provides a chat interface powered by Claude.
#
# HOW TO RUN: streamlit run app.py
# REQUIRES:   users.csv (run generate_data.py first)
#             .env file with ANTHROPIC_API_KEY
# =============================================================================

import streamlit as st
import pandas as pd
import ast

# Import our own modules
from risk_engine import flag_risks
from chatbot import chat_with_claude

# ── Page configuration ────────────────────────────────────────────────────────
# Must be the FIRST Streamlit command in the file

st.set_page_config(
    page_title="IAM Access Review",
    page_icon="🔐",
    layout="wide",
)


# ── Load & score data ─────────────────────────────────────────────────────────

@st.cache_data
def load_data():
    """
    Reads users.csv and runs the risk engine over it.
    @st.cache_data means this only runs once — Streamlit caches the result
    so the page doesn't re-read the CSV on every user interaction.
    """
    df = pd.read_csv("users.csv")

    # risk_flags is stored as a string in CSV — convert back to Python list
    if "risk_flags" in df.columns:
        df["risk_flags"] = df["risk_flags"].apply(
            lambda x: ast.literal_eval(x) if isinstance(x, str) else x
        )

    return flag_risks(df)


# ── App header ────────────────────────────────────────────────────────────────

st.title("🔐 IAM Access Review Assistant")
st.caption("Quarterly access certification · NIST 800-53 · SOX 404 · Powered by Claude")
st.divider()

# Load data (cached after first run)
try:
    df = load_data()
except FileNotFoundError:
    st.error("❌  users.csv not found. Please run `python generate_data.py` first.")
    st.stop()


# ── Layout: two columns ───────────────────────────────────────────────────────
# col_left  = Risk dashboard + user selector
# col_right = AI chat review interface

col_left, col_right = st.columns([1, 1.5], gap="large")


# ═════════════════════════════════════════════════════════════════════════════
# LEFT COLUMN — Dashboard & User Selection
# ═════════════════════════════════════════════════════════════════════════════

with col_left:

    # ── Summary metrics ───────────────────────────────────────────────────────
    st.subheader("📊 Risk Overview")

    high_count   = len(df[df["risk_level"] == "🔴 HIGH"])
    med_count    = len(df[df["risk_level"] == "🟡 MEDIUM"])
    clean_count  = len(df[df["risk_level"] == "🟢 CLEAN"])

    m1, m2, m3 = st.columns(3)
    m1.metric("🔴 High Risk",  high_count)
    m2.metric("🟡 Medium",     med_count)
    m3.metric("🟢 Clean",      clean_count)

    st.divider()

    # ── Review queue ──────────────────────────────────────────────────────────
    # Only show users with at least one risk flag
    flagged_df = (
        df[df["risk_score"] > 0]
        .sort_values("risk_score", ascending=False)
        .reset_index(drop=True)
    )

    st.subheader(f"🚩 Review Queue ({len(flagged_df)} users)")

    # Build a label for each user that shows their risk level and name
    user_labels = [
        f"{row['risk_level']}  {row['name']}  ({row['department']})"
        for _, row in flagged_df.iterrows()
    ]

    selected_label = st.selectbox(
        "Select a user to review:",
        user_labels,
        help="Users sorted by risk score (highest first)"
    )

    # Get the full row for the selected user
    selected_idx = user_labels.index(selected_label)
    user = flagged_df.iloc[selected_idx]

    st.divider()

    # ── Selected user profile card ────────────────────────────────────────────
    st.subheader("👤 User Profile")

    col_a, col_b = st.columns(2)
    col_a.write(f"**Name:** {user['name']}")
    col_a.write(f"**Dept:** {user['department']}")
    col_a.write(f"**Role:** {user['role']}")
    col_b.write(f"**Access:** {user['access_level']}")
    col_b.write(f"**MFA:** {'✅ Yes' if user['mfa_enabled'] else '❌ No'}")
    col_b.write(f"**Last Login:** {user['last_login']}")

    manager_display = user['manager'] if str(user.get('manager', '')).strip() else "⚠️ Unassigned"
    st.write(f"**Manager:** {manager_display}")

    st.divider()

    # ── Risk flags ────────────────────────────────────────────────────────────
    if user["risk_flags"]:
        st.error("**⚠️ Risk Flags Detected:**")
        for flag in user["risk_flags"]:
            st.write(f"• {flag}")
    else:
        st.success("✅ No risk flags — user is clean.")


# ═════════════════════════════════════════════════════════════════════════════
# RIGHT COLUMN — AI Chat Review
# ═════════════════════════════════════════════════════════════════════════════

with col_right:

    st.subheader("💬 AI Review Assistant")
    st.caption("Claude will guide you through certifying or revoking this user's access.")

    # ── Session state management ──────────────────────────────────────────────
    # Streamlit reruns the entire script on every interaction.
    # st.session_state persists data between reruns (like a simple in-memory store).

    # If the user selection changed, reset the chat history
    if "current_user_id" not in st.session_state:
        st.session_state.current_user_id = None
        st.session_state.messages = []
        st.session_state.review_complete = False

    if st.session_state.current_user_id != user["user_id"]:
        # New user selected — clear everything
        st.session_state.current_user_id = user["user_id"]
        st.session_state.messages = []
        st.session_state.review_complete = False

    # ── Chat display ──────────────────────────────────────────────────────────
    # Render all previous messages in the conversation
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # ── Start button (shown only before chat begins) ──────────────────────────
    if not st.session_state.messages:
        st.info("👆 Click the button below to begin the access review with Claude.")

        if st.button("▶️ Start Access Review", type="primary", use_container_width=True):
            # Send the opening message to Claude
            opening_message = [
                {"role": "user", "content": "Please start the access review for this user."}
            ]

            with st.spinner("Claude is reviewing the user profile..."):
                try:
                    response = chat_with_claude(opening_message, user)
                except Exception as e:
                    st.error(f"❌ API Error: {e}")
                    st.stop()

            # Save both messages to session state
            st.session_state.messages = [
                {"role": "user",      "content": "Please start the access review for this user."},
                {"role": "assistant", "content": response},
            ]
            st.rerun()

    # ── Ongoing chat input ────────────────────────────────────────────────────
    elif not st.session_state.review_complete:
        if manager_input := st.chat_input("Type your response to Claude..."):

            # Add manager's message to history
            st.session_state.messages.append({"role": "user", "content": manager_input})

            # Send full history to Claude and get response
            with st.spinner("Claude is thinking..."):
                try:
                    response = chat_with_claude(st.session_state.messages, user)
                except Exception as e:
                    st.error(f"❌ API Error: {e}")
                    st.stop()

            # Add Claude's response to history
            st.session_state.messages.append({"role": "assistant", "content": response})
            st.rerun()

    # ── Decision buttons ──────────────────────────────────────────────────────
    # Shown once a conversation has started
    if st.session_state.messages:
        st.divider()
        st.caption("📋 **Ready to record your decision?**")

        btn1, btn2, btn3 = st.columns(3)

        if btn1.button("✅ CERTIFY", use_container_width=True, type="primary"):
            st.success(f"✅ Access CERTIFIED for {user['name']}. Decision logged.")
            st.session_state.review_complete = True

        if btn2.button("❌ REVOKE", use_container_width=True):
            st.error(f"❌ Access REVOKED for {user['name']}. IT team notified.")
            st.session_state.review_complete = True

        if btn3.button("⬆️ ESCALATE", use_container_width=True):
            st.warning(f"⬆️ Case ESCALATED to Security team for {user['name']}.")
            st.session_state.review_complete = True

        if st.session_state.review_complete:
            if st.button("🔄 Review Another User", use_container_width=True):
                st.session_state.messages = []
                st.session_state.review_complete = False
                st.rerun()
