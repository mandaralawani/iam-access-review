# =============================================================================
# risk_engine.py
# =============================================================================
# PURPOSE: Evaluates each user in the IAM dataset against 4 risk rules
#          grounded in real compliance frameworks (NIST 800-53, SOX 404).
#          Returns the dataframe enriched with risk flags and a risk score.
#
# USED BY: app.py (imported as a module)
# CAN ALSO RUN STANDALONE: python risk_engine.py  → prints flagged users
# =============================================================================

import pandas as pd
from datetime import datetime, timedelta


# ── Configuration ─────────────────────────────────────────────────────────────

# A user is considered "dormant" if they haven't logged in within this many days
DORMANT_THRESHOLD_DAYS = 90

# Access levels that REQUIRE MFA — Standard users are lower risk
PRIVILEGED_ACCESS_LEVELS = ["Elevated", "Admin"]


# ── Risk Rules ────────────────────────────────────────────────────────────────

def get_risk_flags(row, cutoff_date):
    """
    Evaluates a single user row against all risk rules.
    Returns a list of human-readable flag strings.

    Each rule maps to a specific compliance control:
      Rule 1 → NIST 800-53 AC-2(3):  Disable inactive accounts
      Rule 2 → NIST 800-53 IA-5:     Enforce MFA for privileged access
      Rule 3 → SOX Section 404:      Segregation of Duties (SoD)
      Rule 4 → NIST 800-53 AC-2:     Accounts must have an owner/manager
    """
    flags = []

    # ------------------------------------------------------------------
    # Rule 1: DORMANT ACCOUNT
    # Trigger: last login was more than DORMANT_THRESHOLD_DAYS ago
    # Risk: inactive accounts are a common attack vector (credential stuffing)
    # ------------------------------------------------------------------
    if row["last_login"] < cutoff_date:
        days_inactive = (
            datetime.today() - datetime.strptime(row["last_login"], "%Y-%m-%d")
        ).days
        flags.append(f"DORMANT — {days_inactive} days since last login (threshold: {DORMANT_THRESHOLD_DAYS}d)")

    # ------------------------------------------------------------------
    # Rule 2: MFA GAP
    # Trigger: user has Elevated or Admin access but MFA is not enabled
    # Risk: privileged accounts without MFA are high-value targets
    # ------------------------------------------------------------------
    if row["access_level"] in PRIVILEGED_ACCESS_LEVELS and not row["mfa_enabled"]:
        flags.append(f"MFA GAP — {row['access_level']} access granted but MFA not enabled")

    # ------------------------------------------------------------------
    # Rule 3: SEGREGATION OF DUTIES (SoD) VIOLATION
    # Trigger: Finance department user has Admin system access
    # Risk: SOX 404 requires Finance users to NOT have system admin rights
    #       (they could modify financial records AND cover their tracks)
    # ------------------------------------------------------------------
    if row["department"] == "Finance" and row["access_level"] == "Admin":
        flags.append("SOD VIOLATION — Finance role + Admin system access conflicts with SOX 404")

    # ------------------------------------------------------------------
    # Rule 4: ORPHAN ACCOUNT
    # Trigger: no manager is assigned to this user
    # Risk: no one is accountable for reviewing or revoking this access
    # ------------------------------------------------------------------
    manager = str(row.get("manager", "")).strip()
    if not manager:
        flags.append("ORPHAN ACCOUNT — no manager assigned, access is unaccountable")

    return flags


# ── Main scoring function ─────────────────────────────────────────────────────

def flag_risks(df):
    """
    Takes the raw users DataFrame and returns a new DataFrame with
    three additional columns:
      - risk_flags  : list of flag strings for each user
      - risk_score  : integer count of flags (0 = clean, 3+ = critical)
      - risk_level  : human-readable label with emoji for easy filtering
    """
    # Calculate the dormancy cutoff date once (not per row, for performance)
    cutoff_date = (
        datetime.today() - timedelta(days=DORMANT_THRESHOLD_DAYS)
    ).strftime("%Y-%m-%d")

    df = df.copy()  # never mutate the original dataframe

    # Apply risk rules to every row
    df["risk_flags"] = df.apply(lambda row: get_risk_flags(row, cutoff_date), axis=1)

    # Score = number of flags
    df["risk_score"] = df["risk_flags"].apply(len)

    # Label for display
    df["risk_level"] = df["risk_score"].apply(
        lambda s: "🔴 HIGH"   if s >= 2
             else "🟡 MEDIUM" if s == 1
             else "🟢 CLEAN"
    )

    return df


# ── Standalone entry point ────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import os

    csv_path = "users.csv"

    if not os.path.exists(csv_path):
        print("❌  users.csv not found. Run generate_data.py first.")
        sys.exit(1)

    df_raw    = pd.read_csv(csv_path)
    df_scored = flag_risks(df_raw)

    flagged = df_scored[df_scored["risk_score"] > 0].sort_values(
        "risk_score", ascending=False
    )

    print(f"\n📊  Risk Summary — {len(df_scored)} users scanned")
    print(f"   🔴  High risk (2+ flags): {len(df_scored[df_scored.risk_level == '🔴 HIGH'])}")
    print(f"   🟡  Medium risk (1 flag): {len(df_scored[df_scored.risk_level == '🟡 MEDIUM'])}")
    print(f"   🟢  Clean (no flags):     {len(df_scored[df_scored.risk_level == '🟢 CLEAN'])}")

    print(f"\n🚩  Flagged users ({len(flagged)}):\n")
    for _, row in flagged.iterrows():
        print(f"  {row['risk_level']}  {row['name']} ({row['department']} / {row['role']})")
        for flag in row["risk_flags"]:
            print(f"       • {flag}")
        print()
