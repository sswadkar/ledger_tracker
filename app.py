import streamlit as st
import json
import os
from datetime import datetime
from pymongo import MongoClient

from dotenv import load_dotenv
load_dotenv()

SETTINGS_FILE = "settings.json"
MONGO_URI = os.getenv("MONGO_URI")

# MongoDB setup
client = MongoClient(MONGO_URI)
db = client["split_tracker"]
collection = db["ledger"]

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    else:
        return {"person_a_name": "Alice", "person_b_name": "Bob"}

def load_ledger():
    data = collection.find_one({"_id": "ledger"})
    if data:
        data.pop("_id", None)
        return data
    else:
        default = {
            "person_a": {"name": "Alice", "balance": 0.0},
            "person_b": {"name": "Bob", "balance": 0.0},
            "transactions": []
        }
        collection.insert_one({**default, "_id": "ledger"})
        return default

def save_ledger(ledger):
    collection.replace_one({"_id": "ledger"}, {**ledger, "_id": "ledger"}, upsert=True)

# Load settings and ledger
settings = load_settings()
person_a_name = settings["person_a_name"]
person_b_name = settings["person_b_name"]
ledger = load_ledger()
ledger["person_a"]["name"] = person_a_name
ledger["person_b"]["name"] = person_b_name

# Persist identity across session
if "user" not in st.session_state:
    st.session_state["user"] = None

if st.session_state["user"] is None:
    st.title("👋 Welcome to Split Tracker")
    st.subheader("Please select your name to continue:")
    chosen = st.selectbox("Who are you?", [person_a_name, person_b_name])
    if st.button("Continue"):
        st.session_state["user"] = chosen
        st.rerun()
    st.stop()

user = st.session_state["user"]

# Title
st.title("💸 Split Tracker")
st.markdown(f"### Logged in as: **{user}**")

# New Transaction
st.markdown("---")
st.subheader("New Transaction")
col1, col2 = st.columns(2)
with col1:
    amount = st.number_input("Amount", min_value=0.01, step=0.01)
with col2:
    transaction_type = st.selectbox("Type", [
        "You Paid - Split 50/50",
        "You Paid - In Full for Them (You're owed all of it)",
        "They Paid - Split 50/50",
        "They Paid - In Full for You (You owe all of it)",
        "They Paid You (Settlement)",
        "You Paid Them (Settlement)"
    ])

reason = st.text_input("Optional Reason (e.g., dinner, Uber, etc.)")

if st.button("Add Transaction"):
    me, them = ("person_a", "person_b") if user == person_a_name else ("person_b", "person_a")

    # Balance logic
    if transaction_type == "You Paid - Split 50/50":
        ledger[me]["balance"] += amount / 2
        ledger[them]["balance"] -= amount / 2
    elif transaction_type == "You Paid - In Full for Them (You're owed all of it)":
        ledger[me]["balance"] += amount
        ledger[them]["balance"] -= amount
    elif transaction_type == "They Paid - Split 50/50":
        ledger[me]["balance"] -= amount / 2
        ledger[them]["balance"] += amount / 2
    elif transaction_type == "They Paid - In Full for You (You owe all of it)":
        ledger[me]["balance"] -= amount
        ledger[them]["balance"] += amount
    elif transaction_type == "They Paid You (Settlement)":
        ledger[me]["balance"] -= amount
        ledger[them]["balance"] += amount
    elif transaction_type == "You Paid Them (Settlement)":
        ledger[me]["balance"] += amount
        ledger[them]["balance"] -= amount

    ledger["transactions"].append({
        "user": user,
        "type": transaction_type,
        "amount": round(amount, 2),
        "reason": reason.strip(),
        "timestamp": datetime.now().isoformat(timespec='seconds')
    })

    save_ledger(ledger)
    st.success("Transaction recorded!")
    st.rerun()

# Ledger Summary
st.markdown("---")
st.header("📒 Ledger Summary")
st.write(f"**{ledger['person_a']['name']}** balance: ${ledger['person_a']['balance']:.2f}")
st.write(f"**{ledger['person_b']['name']}** balance: ${ledger['person_b']['balance']:.2f}")

# Settlement
st.markdown("### 🤝 Settlement Suggestion")
net = ledger["person_a"]["balance"]
if net > 0:
    st.write(f"💰 **{ledger['person_b']['name']}** owes **{ledger['person_a']['name']}**: **${net:.2f}**")
elif net < 0:
    st.write(f"💰 **{ledger['person_a']['name']}** owes **{ledger['person_b']['name']}**: **${-net:.2f}**")
else:
    st.write("✅ All settled up!")

# Recent Transactions
st.markdown("---")
st.subheader("🧾 Recent Transactions")
if not ledger["transactions"]:
    st.write("No transactions yet.")
else:
    for t in reversed(ledger["transactions"][-10:]):
        desc = f"**{t['user']}** → *{t['type']}* (${t['amount']:.2f})"
        if t["reason"]:
            desc += f" for _{t['reason']}_"
        desc += f" — {t['timestamp']}"
        st.markdown(desc)

# Delete Transaction
st.markdown("---")
st.subheader("🗑️ Delete a Transaction")

if ledger["transactions"]:
    def format_transaction(t):
        base = f"{t['user']} - {t['type']} - ${t['amount']:.2f}"
        if t["reason"]:
            base += f" for {t['reason']}"
        base += f" ({t['timestamp']})"
        return base

    transaction_map = {format_transaction(t): t for t in reversed(ledger["transactions"])}
    selected_label = st.selectbox("Select a transaction to delete:", list(transaction_map.keys()))
    confirm = st.checkbox("Are you sure you want to delete this transaction?")

    if st.button("Delete Transaction") and confirm:
        target = transaction_map[selected_label]
        ledger["transactions"].remove(target)

        me, them = ("person_a", "person_b") if target["user"] == person_a_name else ("person_b", "person_a")
        amt = target["amount"]
        type_ = target["type"]

        if type_ == "You Paid - Split 50/50":
            ledger[me]["balance"] -= amt / 2
            ledger[them]["balance"] += amt / 2
        elif type_ == "You Paid - In Full for Them (You're owed all of it)":
            ledger[me]["balance"] -= amt
            ledger[them]["balance"] += amt
        elif type_ == "They Paid - Split 50/50":
            ledger[me]["balance"] += amt / 2
            ledger[them]["balance"] -= amt / 2
        elif type_ == "They Paid - In Full for You (You owe all of it)":
            ledger[me]["balance"] += amt
            ledger[them]["balance"] -= amt
        elif type_ == "They Paid You (Settlement)":
            ledger[me]["balance"] += amt
            ledger[them]["balance"] -= amt
        elif type_ == "You Paid Them (Settlement)":
            ledger[me]["balance"] -= amt
            ledger[them]["balance"] += amt

        save_ledger(ledger)
        st.success("Transaction deleted.")
        st.rerun()
