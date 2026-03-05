# =============================================================================
# generate_data.py
# =============================================================================
# PURPOSE: Creates a fake IAM (Identity & Access Management) dataset with
#          50 employees and deliberate risk anomalies injected.
#
# HOW TO RUN: python generate_data.py
# OUTPUT:     users.csv in the same folder
# =============================================================================

import pandas as pd
from faker import Faker
import random
from datetime import datetime, timedelta

fake = Faker()
random.seed(42)  # fixed seed = same data every time you run it (good for demos)

# ── Reference data ────────────────────────────────────────────────────────────

DEPARTMENTS = ["Finance", "IT", "Risk", "Operations", "HR"]

# Each department has realistic job roles
ROLES = {
    "Finance":    ["Analyst", "Senior Analyst", "Controller", "Manager"],
    "IT":         ["Engineer", "Senior Engineer", "Admin", "Architect"],
    "Risk":       ["Risk Analyst", "Risk Manager", "Compliance Officer"],
    "Operations": ["Coordinator", "Specialist", "Manager"],
    "HR":         ["Recruiter", "HR Specialist", "HR Manager"],
}

# Access levels from lowest to highest privilege
ACCESS_LEVELS = ["Standard", "Elevated", "Admin"]


# ── Helper functions ──────────────────────────────────────────────────────────

def random_last_login(is_dormant=False):
    """
    Returns a last-login date string.
    - Normal users: logged in within the last 60 days
    - Dormant users: haven't logged in for 91–365 days (triggers NIST AC-2 flag)
    """
    if is_dormant:
        days_ago = random.randint(91, 365)
    else:
        days_ago = random.randint(1, 60)
    return (datetime.today() - timedelta(days=days_ago)).strftime("%Y-%m-%d")


# ── Main data generation ──────────────────────────────────────────────────────

def generate_users(num_users=50):
    """
    Generates a list of fake employee records.
    Anomalies are injected into ~25% of users so the risk engine has
    interesting cases to flag.
    """
    users = []

    for i in range(num_users):
        dept = random.choice(DEPARTMENTS)
        role = random.choice(ROLES[dept])

        # -------------------------------------------------------------------
        # ANOMALY FLAGS — each user independently has a chance of being risky
        # These probabilities are tuned to give a realistic distribution
        # -------------------------------------------------------------------
        is_dormant    = random.random() < 0.15  # 15%: inactive > 90 days       → NIST AC-2(3)
        is_mfa_gap    = random.random() < 0.20  # 20%: elevated access, no MFA  → NIST IA-5
        is_sod_risk   = random.random() < 0.10  # 10%: Finance user with Admin   → SOX 404
        is_no_manager = random.random() < 0.10  # 10%: no manager assigned       → NIST AC-2

        # SoD-risk users are forced to Admin so the rule fires correctly
        access = "Admin" if is_sod_risk else random.choice(ACCESS_LEVELS)

        # MFA gap only matters for Elevated or Admin — downgrade Standard users
        if is_mfa_gap and access == "Standard":
            access = "Elevated"

        users.append({
            "user_id":      f"U{1000 + i}",
            "name":         fake.name(),
            "department":   dept,
            "role":         role,
            "access_level": access,
            "last_login":   random_last_login(is_dormant=is_dormant),
            "mfa_enabled":  not is_mfa_gap,           # False = MFA not set up
            "manager":      "" if is_no_manager else fake.name(),
            "created_date": fake.date_between(
                                start_date="-3y",
                                end_date="-30d"
                            ).strftime("%Y-%m-%d"),
        })

    return users


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Generating IAM user dataset...")

    users = generate_users(num_users=50)
    df = pd.DataFrame(users)

    # Save to CSV in the current directory
    output_path = "users.csv"
    df.to_csv(output_path, index=False)

    # Print a summary so you can see what was created
    cutoff = (datetime.today() - timedelta(days=90)).strftime("%Y-%m-%d")
    dormant_count   = len(df[df["last_login"] < cutoff])
    mfa_gap_count   = len(df[(df["access_level"].isin(["Elevated", "Admin"])) & (~df["mfa_enabled"])])
    sod_count       = len(df[(df["department"] == "Finance") & (df["access_level"] == "Admin")])
    orphan_count    = len(df[df["manager"].str.strip() == ""])

    print(f"\n✅  Saved {len(df)} users to {output_path}")
    print(f"\n   Anomaly breakdown:")
    print(f"   🔴  Dormant accounts (>90 days):       {dormant_count}")
    print(f"   🔴  MFA gap (elevated/admin, no MFA):  {mfa_gap_count}")
    print(f"   🔴  SoD violations (Finance + Admin):  {sod_count}")
    print(f"   🟡  Orphan accounts (no manager):      {orphan_count}")
    print(f"\n   Preview:")
    print(df.head(5).to_string(index=False))
