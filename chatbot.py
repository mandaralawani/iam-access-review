# =============================================================================
# chatbot.py
# =============================================================================
# PURPOSE: Handles all communication with the Claude API.
#          Builds the system prompt with user context, manages conversation
#          history, and returns the AI's response.
#
# USED BY: app.py (imported as a module)
# REQUIRES: ANTHROPIC_API_KEY set in your .env file
# =============================================================================

import os
import anthropic
from dotenv import load_dotenv

# Load ANTHROPIC_API_KEY from the .env file in this folder
load_dotenv()


# ── System Prompt Builder ─────────────────────────────────────────────────────

def build_system_prompt(user_row):
    """
    Constructs the system prompt that tells Claude:
      1. What role it plays (IAM Review Assistant)
      2. Which user is being reviewed (injected from the DataFrame row)
      3. What risk flags have been detected
      4. How to conduct the review conversation

    This is the most important function in the chatbot — the quality of the
    system prompt directly determines the quality of Claude's responses.

    Key concept: we give Claude ALL the context it needs upfront so it can
    ask specific, intelligent questions rather than generic ones.
    """

    # Format risk flags as a bullet list, or "None detected" if clean
    if user_row["risk_flags"]:
        flags_text = "\n".join(f"  • {flag}" for flag in user_row["risk_flags"])
    else:
        flags_text = "  • None detected — user appears clean"

    return f"""You are an IAM (Identity & Access Management) Access Review Assistant \
for a financial services firm. You help managers certify or revoke user access \
during quarterly access reviews, in line with NIST 800-53 and SOX compliance requirements.

You are currently reviewing this employee:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
User ID:       {user_row['user_id']}
Name:          {user_row['name']}
Department:    {user_row['department']}
Role:          {user_row['role']}
Access Level:  {user_row['access_level']}
Last Login:    {user_row['last_login']}
MFA Enabled:   {'Yes' if user_row['mfa_enabled'] else 'NO — not configured'}
Manager:       {user_row['manager'] if str(user_row.get('manager','')).strip() else 'UNASSIGNED'}
Account Since: {user_row['created_date']}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RISK FLAGS DETECTED:
{flags_text}

YOUR INSTRUCTIONS:
1. Start by greeting the manager and giving a brief, plain-English summary \
of what the risk flags mean and why they matter.
2. Ask targeted questions ONE AT A TIME to understand whether this access \
is still business-justified. Tailor questions to the specific flags found.
3. After 2–3 exchanges, issue a recommendation:
   - CERTIFY  → access is justified, no action needed
   - REVOKE   → access should be removed immediately
   - ESCALATE → needs further investigation by the security team
4. Always end your recommendation with a one-sentence compliance rationale \
citing the relevant control (e.g. "per NIST 800-53 AC-2" or "SOX 404 requires...").

STYLE RULES:
- Be concise and professional — managers are busy
- Never ask more than one question per message
- Use plain language, not jargon
- If the manager's answers are vague, probe further before recommending"""


# ── API Call ──────────────────────────────────────────────────────────────────

def chat_with_claude(messages, user_row):
    """
    Sends the full conversation history to Claude and returns the response text.

    Parameters:
      messages  — list of dicts: [{"role": "user"/"assistant", "content": "..."}]
                  This is the FULL history sent on every call because Claude
                  has no memory between API requests.
      user_row  — a pandas Series (one row from the DataFrame) for this user

    Returns:
      A string — Claude's response text
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY not found.\n"
            "Create a .env file in this folder and add:\n"
            "ANTHROPIC_API_KEY=sk-ant-..."
        )

    #client = anthropic.Anthropic(api_key=api_key)
	
	# WITH this (works both locally AND on Streamlit Cloud):
	import streamlit as st
	api_key = st.secrets.get("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
	client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",   # use the latest Sonnet model
        max_tokens=500,                      # keep responses concise
        system=build_system_prompt(user_row),
        messages=messages,                   # full conversation history
    )

    return response.content[0].text


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    """
    Quick test — simulates a single-turn review for a hardcoded risky user.
    Run with: python chatbot.py
    """
    import pandas as pd

    # Create a fake high-risk user to test with
    test_user = pd.Series({
        "user_id":      "U1042",
        "name":         "Jane Smith",
        "department":   "Finance",
        "role":         "Controller",
        "access_level": "Admin",
        "last_login":   "2024-09-01",
        "mfa_enabled":  False,
        "manager":      "",
        "created_date": "2022-03-15",
        "risk_flags": [
            "DORMANT — 184 days since last login (threshold: 90d)",
            "MFA GAP — Admin access granted but MFA not enabled",
            "SOD VIOLATION — Finance role + Admin system access conflicts with SOX 404",
            "ORPHAN ACCOUNT — no manager assigned, access is unaccountable",
        ],
    })

    print("Testing chatbot with a high-risk user...\n")

    test_messages = [
        {"role": "user", "content": "Please start the access review for this user."}
    ]

    try:
        reply = chat_with_claude(test_messages, test_user)
        print("Claude's response:\n")
        print(reply)
    except ValueError as e:
        print(f"❌  {e}")
    except Exception as e:
        print(f"❌  API error: {e}")
