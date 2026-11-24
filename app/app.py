import os
import socket
from datetime import datetime, timezone
from flask import Flask, jsonify, render_template, request
from pymongo import MongoClient
from pymongo.errors import PyMongoError

app = Flask(__name__)

MONGO_URL = os.environ.get("MONGO_URL")
if not MONGO_URL:
    raise RuntimeError("MONGO_URL environment variable must be set.")

client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=2000)


def get_db():
    db = client.get_default_database()
    if db is None:
        db = client["emidb"]
    return db


def get_pod_info():
    pod_name = os.environ.get("HOSTNAME") or socket.gethostname()
    try:
        pod_ip = socket.gethostbyname(socket.gethostname())
    except socket.gaierror:
        pod_ip = "127.0.0.1"
    return pod_name, pod_ip


@app.route("/", methods=["GET"])
def index():
    pod_name, pod_ip = get_pod_info()
    return render_template("index.html", pod_name=pod_name, pod_ip=pod_ip)


@app.route("/health", methods=["GET"])
def health():
    try:
        client.admin.command("ping")
        return jsonify({"status": "ok"}), 200
    except PyMongoError as exc:
        return jsonify({"status": "unhealthy", "error": str(exc)}), 503


@app.route("/api/emi", methods=["POST"])
def calculate_emi():
    payload = request.get_json(silent=True) or request.form

    try:
        principal = float(payload.get("P", payload.get("principal", 0)))
        rate = float(payload.get("rate", 0))
        months_raw = float(payload.get("n", payload.get("months", 0)))
        months = int(months_raw)
    except (TypeError, ValueError):
        return jsonify({"error": "Inputs P, rate, and n must be valid numbers."}), 400

    if principal <= 0 or rate <= 0 or months <= 0 or months != months_raw:
        return jsonify({
            "error": "Principal (P) and annual rate must be positive numbers, and tenure (n) must be a positive integer."
        }), 400

    monthly_rate = (rate / 12.0) / 100.0
    factor = (1.0 + monthly_rate) ** months
    emi = (principal * monthly_rate * factor) / (factor - 1.0)
    total_payment = emi * months
    total_interest = total_payment - principal

    pod_name, pod_ip = get_pod_info()
    created_at = datetime.now(timezone.utc)

    record = {
        "principal": round(principal, 2),
        "rate": round(rate, 4),
        "months": months,
        "emi": round(emi, 2),
        "servedBy": pod_name,
        "createdAt": created_at,
    }

    try:
        db = get_db()
        db.calculations.insert_one(record)
    except PyMongoError as exc:
        return jsonify({"error": f"Database write failed: {exc}"}), 500

    return jsonify({
        "principal": round(principal, 2),
        "rate": round(rate, 4),
        "months": months,
        "emi": round(emi, 2),
        "totalPayment": round(total_payment, 2),
        "totalInterest": round(total_interest, 2),
        "servedBy": pod_name,
        "podIp": pod_ip,
        "createdAt": created_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
    }), 200


@app.route("/api/history", methods=["GET"])
def get_history():
    try:
        db = get_db()
        cursor = (
            db.calculations.find({}, {"_id": 0})
            .sort("createdAt", -1)
            .limit(10)
        )
        items = []
        for doc in cursor:
            created = doc.get("createdAt")
            if isinstance(created, datetime):
                doc["createdAt"] = created.strftime("%Y-%m-%d %H:%M:%S UTC")
            items.append(doc)
        return jsonify(items), 200
    except PyMongoError as exc:
        return jsonify({"error": f"Database read failed: {exc}"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
