import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), "fraud_detection.db")
schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")

with sqlite3.connect(db_path) as conn:
    with open(schema_path, 'r') as f:
        schema = f.read()
    conn.executescript(schema)
    
    # Initialize some dummy accounts for testing
    conn.execute("INSERT OR IGNORE INTO Customer (customer_id, name, email, phone) VALUES (1, 'Test User', 'test@example.com', '1234567890')")
    conn.execute("INSERT OR IGNORE INTO Account (account_id, customer_id, account_type, balance) VALUES (1, 1, 'Savings', 50000)")
    conn.commit()
    print("Database initialized successfully at:", db_path)
