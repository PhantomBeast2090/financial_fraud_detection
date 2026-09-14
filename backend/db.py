import os
import sqlite3
import uuid
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "database", "fraud_detection.db")
DB_PATH = os.environ.get("FRAUD_DB_PATH", DEFAULT_DB_PATH)

DEFAULT_ACCOUNT_TYPES = ("Savings", "Current", "Credit")
DEFAULT_LOCATIONS = (
    ("Chennai", "Tamil Nadu", "India", "Medium"),
    ("Mumbai", "Maharashtra", "India", "High"),
    ("Delhi", "Delhi", "India", "High"),
    ("Bangalore", "Karnataka", "India", "Medium"),
    ("Hyderabad", "Telangana", "India", "Medium"),
)
DEFAULT_TRANSACTION_TYPES = ("ATM", "Online", "POS")


def get_connection(initialize=True):
    """Return a SQLite connection with Review-3 DBMS safeguards enabled."""
    conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")

    if initialize:
        _ensure_review3_schema(conn)

    return conn


def _table_exists(conn, table_name):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(conn, table_name):
    if not _table_exists(conn, table_name):
        return set()
    return {row[1] for row in conn.execute(f'PRAGMA table_info("{table_name}")')}


def _add_column_if_missing(conn, table_name, column_name, definition):
    if column_name not in _table_columns(conn, table_name):
        conn.execute(f'ALTER TABLE "{table_name}" ADD COLUMN {column_name} {definition}')


def _safe_execute(conn, sql):
    try:
        conn.execute(sql)
    except sqlite3.DatabaseError:
        # Existing student/demo databases may contain duplicate historical rows.
        # The fresh schema has the stricter constraints; old DBs stay usable.
        pass


def _ensure_review3_schema(conn):
    """Upgrade older project databases without deleting existing demo data.

    The fresh schema in database/schema.sql is fully normalized. This function
    adds the same review tables/columns to an older local SQLite file so the app
    can still run without requiring a destructive rebuild.
    """
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS Customer (
            customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            phone TEXT
        );

        CREATE TABLE IF NOT EXISTS Account_Type (
            account_type_id INTEGER PRIMARY KEY AUTOINCREMENT,
            type_name TEXT UNIQUE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS Account (
            account_id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            account_type_id INTEGER,
            balance REAL NOT NULL DEFAULT 0 CHECK(balance >= 0),
            status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE', 'FROZEN', 'CLOSED')),
            FOREIGN KEY (customer_id) REFERENCES Customer(customer_id),
            FOREIGN KEY (account_type_id) REFERENCES Account_Type(account_type_id)
        );

        CREATE TABLE IF NOT EXISTS Location (
            location_id INTEGER PRIMARY KEY AUTOINCREMENT,
            city TEXT UNIQUE NOT NULL,
            state TEXT NOT NULL DEFAULT 'Unknown',
            country TEXT NOT NULL DEFAULT 'India',
            risk_zone TEXT NOT NULL DEFAULT 'Medium'
                CHECK(risk_zone IN ('Low', 'Medium', 'High'))
        );

        CREATE TABLE IF NOT EXISTS Transaction_Type (
            transaction_type_id INTEGER PRIMARY KEY AUTOINCREMENT,
            type_name TEXT UNIQUE NOT NULL
                CHECK(type_name IN ('ATM', 'Online', 'POS', 'UPI', 'NEFT', 'IMPS'))
        );

        CREATE TABLE IF NOT EXISTS "Transaction" (
            transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            amount REAL NOT NULL CHECK(amount > 0),
            location_id INTEGER,
            transaction_type_id INTEGER,
            time_of_day INTEGER NOT NULL CHECK(time_of_day BETWEEN 0 AND 23),
            distance_from_home REAL NOT NULL DEFAULT 0 CHECK(distance_from_home >= 0),
            status TEXT NOT NULL DEFAULT 'APPROVED'
                CHECK(status IN ('APPROVED', 'BLOCKED', 'REVIEW')),
            transaction_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_id) REFERENCES Account(account_id),
            FOREIGN KEY (location_id) REFERENCES Location(location_id),
            FOREIGN KEY (transaction_type_id) REFERENCES Transaction_Type(transaction_type_id)
        );

        CREATE TABLE IF NOT EXISTS Prediction (
            prediction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER NOT NULL,
            fraud_probability REAL NOT NULL CHECK(fraud_probability BETWEEN 0 AND 1),
            predicted_label TEXT NOT NULL CHECK(predicted_label IN ('Fraud', 'Legitimate')),
            model_version TEXT NOT NULL DEFAULT 'RF-v1',
            predicted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (transaction_id) REFERENCES "Transaction"(transaction_id)
        );

        CREATE TABLE IF NOT EXISTS Fraud_Alert (
            alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER NOT NULL,
            risk_level TEXT NOT NULL CHECK(risk_level IN ('Low', 'Medium', 'High')),
            reason TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (transaction_id) REFERENCES "Transaction"(transaction_id)
        );

        CREATE TABLE IF NOT EXISTS Transaction_Audit (
            audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER NOT NULL,
            account_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            before_balance REAL NOT NULL,
            after_balance REAL NOT NULL,
            owner_session TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (transaction_id) REFERENCES "Transaction"(transaction_id),
            FOREIGN KEY (account_id) REFERENCES Account(account_id)
        );

        CREATE TABLE IF NOT EXISTS Table_Lock (
            lock_name TEXT PRIMARY KEY,
            lock_mode TEXT NOT NULL CHECK(lock_mode IN ('SHARED', 'EXCLUSIVE')),
            owner_session TEXT NOT NULL,
            acquired_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS Account_Lock (
            account_id INTEGER PRIMARY KEY,
            lock_mode TEXT NOT NULL CHECK(lock_mode IN ('SHARED', 'EXCLUSIVE')),
            owner_session TEXT NOT NULL,
            acquired_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_id) REFERENCES Account(account_id)
        );

        CREATE TABLE IF NOT EXISTS Lock_Log (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            lock_scope TEXT NOT NULL CHECK(lock_scope IN ('TABLE', 'ROW')),
            lock_mode TEXT NOT NULL CHECK(lock_mode IN ('SHARED', 'EXCLUSIVE')),
            resource_name TEXT NOT NULL,
            owner_session TEXT NOT NULL,
            action TEXT NOT NULL CHECK(action IN ('ACQUIRED', 'RELEASED', 'READ_DEMO')),
            note TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    # Older builds used a trigger for balance updates. The Review-3 version keeps
    # balance changes inside the explicit ACID transaction to avoid double debit.
    conn.execute("DROP TRIGGER IF EXISTS update_account_balance")

    for type_name in DEFAULT_ACCOUNT_TYPES:
        conn.execute(
            "INSERT OR IGNORE INTO Account_Type(type_name) VALUES (?)",
            (type_name,),
        )

    for city, state, country, risk_zone in DEFAULT_LOCATIONS:
        conn.execute(
            """
            INSERT OR IGNORE INTO Location(city, state, country, risk_zone)
            VALUES (?, ?, ?, ?)
            """,
            (city, state, country, risk_zone),
        )

    for type_name in DEFAULT_TRANSACTION_TYPES:
        conn.execute(
            "INSERT OR IGNORE INTO Transaction_Type(type_name) VALUES (?)",
            (type_name,),
        )

    _add_column_if_missing(conn, "Account", "account_type_id", "INTEGER")
    _add_column_if_missing(
        conn,
        "Account",
        "status",
        "TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE', 'FROZEN', 'CLOSED'))",
    )
    _add_column_if_missing(conn, "Transaction", "location_id", "INTEGER")
    _add_column_if_missing(conn, "Transaction", "transaction_type_id", "INTEGER")
    _add_column_if_missing(
        conn,
        "Transaction",
        "status",
        "TEXT NOT NULL DEFAULT 'APPROVED' CHECK(status IN ('APPROVED', 'BLOCKED', 'REVIEW'))",
    )
    _add_column_if_missing(conn, "Prediction", "predicted_at", "DATETIME")
    _add_column_if_missing(conn, "Prediction", "model_version", "TEXT NOT NULL DEFAULT 'RF-v1'")

    account_cols = _table_columns(conn, "Account")
    if "account_type" in account_cols:
        rows = conn.execute(
            "SELECT DISTINCT account_type FROM Account WHERE account_type IS NOT NULL"
        ).fetchall()
        for row in rows:
            conn.execute(
                "INSERT OR IGNORE INTO Account_Type(type_name) VALUES (?)",
                (row[0],),
            )
        conn.execute(
            """
            UPDATE Account
            SET account_type_id = (
                SELECT account_type_id
                FROM Account_Type
                WHERE type_name = Account.account_type
            )
            WHERE account_type_id IS NULL AND account_type IS NOT NULL
            """
        )

    txn_cols = _table_columns(conn, "Transaction")
    if "location" in txn_cols:
        rows = conn.execute(
            'SELECT DISTINCT location FROM "Transaction" WHERE location IS NOT NULL'
        ).fetchall()
        for row in rows:
            conn.execute(
                "INSERT OR IGNORE INTO Location(city, state, country, risk_zone) VALUES (?, 'Unknown', 'India', 'Medium')",
                (row[0],),
            )
        conn.execute(
            """
            UPDATE "Transaction"
            SET location_id = (
                SELECT location_id FROM Location WHERE city = "Transaction".location
            )
            WHERE location_id IS NULL AND location IS NOT NULL
            """
        )

    if "transaction_type" in txn_cols:
        rows = conn.execute(
            'SELECT DISTINCT transaction_type FROM "Transaction" WHERE transaction_type IS NOT NULL'
        ).fetchall()
        for row in rows:
            conn.execute(
                "INSERT OR IGNORE INTO Transaction_Type(type_name) VALUES (?)",
                (row[0],),
            )
        conn.execute(
            """
            UPDATE "Transaction"
            SET transaction_type_id = (
                SELECT transaction_type_id
                FROM Transaction_Type
                WHERE type_name = "Transaction".transaction_type
            )
            WHERE transaction_type_id IS NULL AND transaction_type IS NOT NULL
            """
        )

    savings_type_id = _lookup_id(conn, "Account_Type", "type_name", "Savings")
    conn.execute(
        """
        INSERT OR IGNORE INTO Customer(customer_id, name, email, phone)
        VALUES (1, 'Test User', 'test@example.com', '1234567890')
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO Account(account_id, customer_id, account_type_id, balance, status)
        VALUES (1, 1, ?, 50000, 'ACTIVE')
        """,
        (savings_type_id,),
    )
    conn.execute(
        "UPDATE Account SET account_type_id = COALESCE(account_type_id, ?) WHERE account_id = 1",
        (savings_type_id,),
    )

    _safe_execute(
        conn,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_prediction_one_per_transaction ON Prediction(transaction_id)",
    )
    _safe_execute(
        conn,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_alert_one_per_transaction ON Fraud_Alert(transaction_id)",
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_transaction_account ON \"Transaction\"(account_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_transaction_location ON \"Transaction\"(location_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_prediction_label ON Prediction(predicted_label)")

    conn.execute("DROP TRIGGER IF EXISTS prediction_high_risk_alert")
    conn.executescript(
        """
        CREATE TRIGGER prediction_high_risk_alert
        AFTER INSERT ON Prediction
        WHEN NEW.predicted_label = 'Fraud' OR NEW.fraud_probability >= 0.75
        BEGIN
            INSERT OR IGNORE INTO Fraud_Alert(transaction_id, risk_level, reason)
            VALUES (
                NEW.transaction_id,
                CASE
                    WHEN NEW.fraud_probability >= 0.85 THEN 'High'
                    WHEN NEW.fraud_probability >= 0.65 THEN 'Medium'
                    ELSE 'Low'
                END,
                'ML risk score crossed fraud threshold'
            );
        END;
        """
    )

    _create_review_views(conn)
    conn.commit()


def _create_review_views(conn):
    txn_cols = _table_columns(conn, "Transaction")
    account_cols = _table_columns(conn, "Account")

    location_expr = "COALESCE(l.city, t.location)" if "location" in txn_cols else "l.city"
    type_expr = (
        "COALESCE(tt.type_name, t.transaction_type)"
        if "transaction_type" in txn_cols
        else "tt.type_name"
    )
    account_type_expr = (
        "COALESCE(at.type_name, a.account_type)" if "account_type" in account_cols else "at.type_name"
    )

    conn.execute("DROP VIEW IF EXISTS Transaction_Details")
    conn.execute("DROP VIEW IF EXISTS Fraudulent_Transactions_View")
    conn.execute("DROP VIEW IF EXISTS Review3_Fraud_Report")

    conn.execute(
        f"""
        CREATE VIEW Transaction_Details AS
        SELECT
            t.transaction_id,
            c.customer_id,
            c.name AS customer_name,
            c.email,
            a.account_id,
            {account_type_expr} AS account_type,
            a.balance AS current_balance,
            t.amount,
            {location_expr} AS location,
            type_expr_placeholder AS transaction_type,
            t.time_of_day,
            t.distance_from_home,
            t.status,
            t.transaction_time,
            p.fraud_probability,
            p.predicted_label,
            f.risk_level,
            f.reason AS alert_reason
        FROM "Transaction" t
        JOIN Account a ON t.account_id = a.account_id
        JOIN Customer c ON a.customer_id = c.customer_id
        LEFT JOIN Account_Type at ON a.account_type_id = at.account_type_id
        LEFT JOIN Location l ON t.location_id = l.location_id
        LEFT JOIN Transaction_Type tt ON t.transaction_type_id = tt.transaction_type_id
        LEFT JOIN Prediction p ON t.transaction_id = p.transaction_id
        LEFT JOIN Fraud_Alert f ON t.transaction_id = f.transaction_id
        """.replace("type_expr_placeholder", type_expr)
    )

    conn.execute(
        """
        CREATE VIEW Fraudulent_Transactions_View AS
        SELECT
            transaction_id,
            customer_name AS name,
            account_type,
            amount,
            location,
            risk_level,
            alert_reason AS reason
        FROM Transaction_Details
        WHERE predicted_label = 'Fraud'
        """
    )

    conn.execute(
        """
        CREATE VIEW Review3_Fraud_Report AS
        SELECT
            transaction_id,
            customer_name,
            account_id,
            amount,
            location,
            transaction_type,
            status,
            ROUND(COALESCE(fraud_probability, 0) * 100, 2) AS fraud_score_percent,
            COALESCE(risk_level, 'Low') AS risk_level,
            transaction_time
        FROM Transaction_Details
        """
    )


def _lookup_id(conn, table_name, value_column, value):
    value = (value or "Unknown").strip()
    row = conn.execute(
        f'SELECT rowid AS id FROM "{table_name}" WHERE {value_column} = ?',
        (value,),
    ).fetchone()
    if row:
        return row["id"]

    conn.execute(f'INSERT INTO "{table_name}"({value_column}) VALUES (?)', (value,))
    return conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]


def _insert_lock_log(conn, lock_scope, lock_mode, resource_name, owner_session, action, note):
    conn.execute(
        """
        INSERT INTO Lock_Log(lock_scope, lock_mode, resource_name, owner_session, action, note)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (lock_scope, lock_mode, resource_name, owner_session, action, note),
    )


def record_transaction_atomic(
    account_id,
    amount,
    location,
    transaction_type,
    time_of_day,
    distance_from_home,
    fraud_probability,
    predicted_label,
):
    """Store one fraud decision using one ACID transaction.

    Atomicity: transaction, prediction, alert, audit, lock logs, and balance move
    commit together or roll back together.
    Consistency: FK/CHECK constraints plus balance and account-status checks.
    Isolation: BEGIN IMMEDIATE gives SQLite a write lock; Account_Lock records the
    logical row-level exclusive lock used for the viva/demo.
    Durability: COMMIT persists the approved or blocked decision.
    """
    if amount <= 0:
        raise ValueError("Amount must be greater than 0")
    if not 0 <= time_of_day <= 23:
        raise ValueError("time_of_day must be between 0 and 23")
    if distance_from_home < 0:
        raise ValueError("distance_from_home cannot be negative")

    conn = get_connection()
    owner_session = f"api-{uuid.uuid4().hex[:8]}"
    status = "BLOCKED" if predicted_label == "Fraud" else "APPROVED"

    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            INSERT INTO Table_Lock(lock_name, lock_mode, owner_session)
            VALUES ('Transaction_WRITE', 'EXCLUSIVE', ?)
            """,
            (owner_session,),
        )
        _insert_lock_log(
            conn,
            "TABLE",
            "EXCLUSIVE",
            "Transaction_WRITE",
            owner_session,
            "ACQUIRED",
            "BEGIN IMMEDIATE allows only one writer, demonstrating table-level exclusive locking in SQLite.",
        )

        account = conn.execute(
            """
            SELECT account_id, balance, status
            FROM Account
            WHERE account_id = ?
            """,
            (account_id,),
        ).fetchone()
        if account is None:
            raise ValueError(f"Account {account_id} does not exist")
        if account["status"] != "ACTIVE":
            raise ValueError(f"Account {account_id} is not active")

        conn.execute(
            """
            INSERT INTO Account_Lock(account_id, lock_mode, owner_session)
            VALUES (?, 'EXCLUSIVE', ?)
            """,
            (account_id, owner_session),
        )
        _insert_lock_log(
            conn,
            "ROW",
            "EXCLUSIVE",
            f"Account:{account_id}",
            owner_session,
            "ACQUIRED",
            "Logical row lock prevents two fraud decisions from debiting the same account concurrently.",
        )

        before_balance = float(account["balance"])
        if status == "APPROVED" and before_balance < amount:
            raise ValueError("Insufficient account balance for an approved transaction")

        location_id = _lookup_id(conn, "Location", "city", location)
        type_id = _lookup_id(conn, "Transaction_Type", "type_name", transaction_type)
        txn_cols = _table_columns(conn, "Transaction")

        columns = [
            "account_id",
            "amount",
            "location_id",
            "transaction_type_id",
            "time_of_day",
            "distance_from_home",
            "status",
        ]
        values = [
            account_id,
            amount,
            location_id,
            type_id,
            time_of_day,
            distance_from_home,
            status,
        ]
        if "location" in txn_cols:
            columns.append("location")
            values.append(location)
        if "transaction_type" in txn_cols:
            columns.append("transaction_type")
            values.append(transaction_type)

        placeholders = ", ".join("?" for _ in columns)
        column_sql = ", ".join(columns)
        cursor = conn.execute(
            f'INSERT INTO "Transaction" ({column_sql}) VALUES ({placeholders})',
            values,
        )
        transaction_id = cursor.lastrowid

        prediction_cols = _table_columns(conn, "Prediction")
        pred_columns = ["transaction_id", "fraud_probability", "predicted_label"]
        pred_values = [transaction_id, fraud_probability, predicted_label]
        if "model_version" in prediction_cols:
            pred_columns.append("model_version")
            pred_values.append("RF-v1")
        pred_placeholders = ", ".join("?" for _ in pred_columns)
        conn.execute(
            f'INSERT INTO Prediction ({", ".join(pred_columns)}) VALUES ({pred_placeholders})',
            pred_values,
        )

        after_balance = before_balance
        if status == "APPROVED":
            conn.execute(
                """
                UPDATE Account
                SET balance = balance - ?
                WHERE account_id = ? AND balance >= ?
                """,
                (amount, account_id, amount),
            )
            after_balance = before_balance - amount

        conn.execute(
            """
            INSERT INTO Transaction_Audit(
                transaction_id,
                account_id,
                event_type,
                before_balance,
                after_balance,
                owner_session
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                transaction_id,
                account_id,
                "FRAUD_BLOCKED_NO_DEBIT" if status == "BLOCKED" else "APPROVED_AND_DEBITED",
                before_balance,
                after_balance,
                owner_session,
            ),
        )

        conn.execute("DELETE FROM Account_Lock WHERE account_id = ?", (account_id,))
        _insert_lock_log(
            conn,
            "ROW",
            "EXCLUSIVE",
            f"Account:{account_id}",
            owner_session,
            "RELEASED",
            "Account row lock released before commit.",
        )
        conn.execute("DELETE FROM Table_Lock WHERE lock_name = 'Transaction_WRITE'")
        _insert_lock_log(
            conn,
            "TABLE",
            "EXCLUSIVE",
            "Transaction_WRITE",
            owner_session,
            "RELEASED",
            "Table write lock released before commit.",
        )

        conn.commit()
        return {
            "transaction_id": transaction_id,
            "status": status,
            "before_balance": before_balance,
            "after_balance": after_balance,
            "owner_session": owner_session,
        }
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()


def get_dashboard_metrics(limit=15):
    conn = get_connection()
    try:
        transactions = conn.execute(
            """
            SELECT
                transaction_id,
                amount,
                location,
                transaction_type,
                fraud_probability,
                predicted_label,
                transaction_time,
                status
            FROM Transaction_Details
            ORDER BY transaction_time DESC, transaction_id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        total_alerts = conn.execute("SELECT COUNT(*) AS count FROM Fraud_Alert").fetchone()["count"]
        total_txns = conn.execute('SELECT COUNT(*) AS count FROM "Transaction"').fetchone()["count"]
        latest_locks = conn.execute(
            """
            SELECT lock_scope, lock_mode, resource_name, action, note, created_at
            FROM Lock_Log
            ORDER BY log_id DESC
            LIMIT 8
            """
        ).fetchall()
        return {
            "recent_transactions": [dict(row) for row in transactions],
            "total_alerts": total_alerts,
            "total_transactions": total_txns,
            "lock_log": [dict(row) for row in latest_locks],
        }
    finally:
        conn.close()


def run_lock_demo(account_id=1):
    """Create visible shared/exclusive lock evidence for the dashboard/viva."""
    conn = get_connection()
    owner_session = f"demo-{uuid.uuid4().hex[:8]}"
    try:
        conn.execute("BEGIN IMMEDIATE")

        conn.execute('SELECT COUNT(*) FROM "Transaction"').fetchone()
        _insert_lock_log(
            conn,
            "TABLE",
            "SHARED",
            "Transaction_READ",
            owner_session,
            "READ_DEMO",
            "A SELECT inside a transaction demonstrates a shared table read lock concept.",
        )

        conn.execute(
            """
            INSERT INTO Table_Lock(lock_name, lock_mode, owner_session)
            VALUES ('Transaction_WRITE_DEMO', 'EXCLUSIVE', ?)
            """,
            (owner_session,),
        )
        _insert_lock_log(
            conn,
            "TABLE",
            "EXCLUSIVE",
            "Transaction_WRITE_DEMO",
            owner_session,
            "ACQUIRED",
            "Only one writer can hold this logical table lock.",
        )

        account = conn.execute(
            "SELECT account_id, balance FROM Account WHERE account_id = ?",
            (account_id,),
        ).fetchone()
        if account is None:
            raise ValueError(f"Account {account_id} does not exist")
        _insert_lock_log(
            conn,
            "ROW",
            "SHARED",
            f"Account:{account_id}",
            owner_session,
            "READ_DEMO",
            "Reading one account row demonstrates shared row-lock intent.",
        )

        conn.execute(
            """
            INSERT INTO Account_Lock(account_id, lock_mode, owner_session)
            VALUES (?, 'EXCLUSIVE', ?)
            """,
            (account_id, owner_session),
        )
        _insert_lock_log(
            conn,
            "ROW",
            "EXCLUSIVE",
            f"Account:{account_id}",
            owner_session,
            "ACQUIRED",
            "Logical row-level exclusive lock for account balance updates.",
        )

        conn.execute("DELETE FROM Account_Lock WHERE account_id = ?", (account_id,))
        conn.execute("DELETE FROM Table_Lock WHERE lock_name = 'Transaction_WRITE_DEMO'")
        _insert_lock_log(
            conn,
            "ROW",
            "EXCLUSIVE",
            f"Account:{account_id}",
            owner_session,
            "RELEASED",
            "Released row-level exclusive demo lock.",
        )
        _insert_lock_log(
            conn,
            "TABLE",
            "EXCLUSIVE",
            "Transaction_WRITE_DEMO",
            owner_session,
            "RELEASED",
            "Released table-level exclusive demo lock.",
        )

        conn.commit()
        return {
            "owner_session": owner_session,
            "account_id": account_id,
            "demonstrated": [
                "table shared read lock",
                "table exclusive write lock",
                "row shared read intent",
                "row exclusive account lock",
            ],
        }
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()


def get_review3_summary():
    conn = get_connection()
    try:
        table_count = conn.execute(
            "SELECT COUNT(*) AS count FROM sqlite_master WHERE type = 'table'"
        ).fetchone()["count"]
        latest_audit = conn.execute(
            """
            SELECT transaction_id, event_type, before_balance, after_balance, owner_session, created_at
            FROM Transaction_Audit
            ORDER BY audit_id DESC
            LIMIT 5
            """
        ).fetchall()
        latest_locks = conn.execute(
            """
            SELECT lock_scope, lock_mode, resource_name, action, created_at
            FROM Lock_Log
            ORDER BY log_id DESC
            LIMIT 6
            """
        ).fetchall()
    finally:
        conn.close()

    return {
        "rubric_target": "Review 3 - Normalization, ACID transactions, and concurrency locking",
        "normalized_tables": table_count,
        "normalization": {
            "highest_normal_form": "3NF/BCNF-style lookup design",
            "functional_dependencies": [
                "customer_id -> name, email, phone",
                "email -> customer_id",
                "account_type_id -> type_name",
                "account_id -> customer_id, account_type_id, balance, status",
                "location_id -> city, state, country, risk_zone",
                "transaction_type_id -> type_name",
                "transaction_id -> account_id, amount, location_id, transaction_type_id, time_of_day, distance_from_home, status, transaction_time",
                "transaction_id -> fraud_probability, predicted_label, model_version",
            ],
            "anomalies_removed": [
                "Update anomaly: city/type names are stored once in Location and Transaction_Type.",
                "Insert anomaly: new locations and transaction types can be inserted before any transaction uses them.",
                "Delete anomaly: deleting one transaction does not delete master data such as customer, account type, or location.",
            ],
        },
        "acid": {
            "atomicity": "record_transaction_atomic commits transaction, prediction, audit, alert, lock log, and balance together or rolls all back.",
            "consistency": "Foreign keys, CHECK constraints, account status checks, and non-negative balances keep data valid.",
            "isolation": "BEGIN IMMEDIATE plus Account_Lock serializes concurrent account balance writes.",
            "durability": "SQLite COMMIT persists the fraud decision and audit trail to fraud_detection.db.",
            "latest_audit": [dict(row) for row in latest_audit],
        },
        "locking": {
            "table_level": "Table_Lock and BEGIN IMMEDIATE demonstrate shared reads and exclusive writes.",
            "row_level": "Account_Lock demonstrates shared read intent and exclusive account-row updates.",
            "mysql_equivalent_file": "database/review3_full_marks.sql",
            "latest_lock_log": [dict(row) for row in latest_locks],
        },
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
