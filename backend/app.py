from flask import Flask, request, jsonify
from flask_cors import CORS
from model import predict_fraud
from db import get_connection
import sqlite3

app = Flask(__name__)
# Enable CORS for the Frontend Dashboard
CORS(app)

@app.route('/transaction', methods=['POST'])
def add_transaction():
    data = request.json
    
    amount = float(data.get('amount', 0))
    location = data.get('location', '')
    t_type = data.get('transaction_type', '')
    account_id = int(data.get('account_id', 1))
    
    # New Advanced Features
    time_of_day = int(data.get('time_of_day', 12))
    distance_from_home = float(data.get('distance_from_home', 0.0))

    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Insert transaction
        cursor.execute(
            'INSERT INTO "Transaction" (account_id, amount, location, transaction_type, time_of_day, distance_from_home) VALUES (?, ?, ?, ?, ?, ?)',
            (account_id, amount, location, t_type, time_of_day, distance_from_home)
        )
        transaction_id = cursor.lastrowid

        # ML Prediction (Fast Inference via Cached .pkl Model)
        prob, label = predict_fraud(amount, location, t_type, time_of_day, distance_from_home)

        # Store prediction
        cursor.execute(
            "INSERT INTO Prediction (transaction_id, fraud_probability, predicted_label) VALUES (?, ?, ?)",
            (transaction_id, prob, label)
        )

        # Alert
        if label == "Fraud":
            cursor.execute(
                "INSERT INTO Fraud_Alert (transaction_id, risk_level, reason) VALUES (?, ?, ?)",
                (transaction_id, "High", "ML detected fraud via RF Model")
            )

        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

    return jsonify({
        "transaction_id": transaction_id,
        "fraud_probability": round(prob, 4),
        "prediction": label
    })

@app.route('/dashboard', methods=['GET'])
def get_dashboard_data():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Fetch latest 10 transactions
    cursor.execute('''
        SELECT t.transaction_id, t.amount, t.location, p.fraud_probability, p.predicted_label, t.transaction_time
        FROM "Transaction" t
        JOIN Prediction p ON t.transaction_id = p.transaction_id
        ORDER BY t.transaction_time DESC LIMIT 15
    ''')
    transactions = cursor.fetchall()

    # Fetch total fraud alerts
    cursor.execute('SELECT COUNT(*) FROM Fraud_Alert')
    total_alerts = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM "Transaction"')
    total_txns = cursor.fetchone()[0]

    conn.close()

    return jsonify({
        "recent_transactions": [
            {"id": r[0], "amount": r[1], "location": r[2], "probability": round(r[3], 3), "label": r[4], "time": r[5]} 
            for r in transactions
        ],
        "total_alerts": total_alerts,
        "total_transactions": total_txns
    })

if __name__ == '__main__':
    app.run(debug=True, port=5001)