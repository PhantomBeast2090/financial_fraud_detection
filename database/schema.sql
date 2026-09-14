CREATE TABLE Customer (
    customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(50),
    email VARCHAR(100) UNIQUE NOT NULL,
    phone VARCHAR(15)
);
CREATE TABLE sqlite_sequence(name,seq);
CREATE TABLE Account (
    account_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER,
    account_type VARCHAR(20),
    balance REAL, account_type_id INTEGER, status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE', 'FROZEN', 'CLOSED')),
    FOREIGN KEY (customer_id) REFERENCES Customer(customer_id)
);
CREATE TABLE IF NOT EXISTS "Transaction" (
    transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER,
    amount REAL CHECK(amount > 0),
    location VARCHAR(50),
    transaction_type VARCHAR(20),
    time_of_day INTEGER,
    distance_from_home REAL,
    transaction_time DATETIME DEFAULT CURRENT_TIMESTAMP, location_id INTEGER, transaction_type_id INTEGER, status TEXT NOT NULL DEFAULT 'APPROVED' CHECK(status IN ('APPROVED', 'BLOCKED', 'REVIEW')),
    FOREIGN KEY (account_id) REFERENCES Account(account_id)
);
CREATE TABLE Prediction (
    prediction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id INTEGER,
    fraud_probability REAL,
    predicted_label VARCHAR(10), model_version TEXT NOT NULL DEFAULT 'RF-v1', predicted_at DATETIME,
    FOREIGN KEY (transaction_id) REFERENCES "Transaction"(transaction_id)
);
CREATE TABLE Fraud_Alert (
    alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id INTEGER,
    risk_level VARCHAR(10),
    reason VARCHAR(100),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE Account_Type (
            account_type_id INTEGER PRIMARY KEY AUTOINCREMENT,
            type_name TEXT UNIQUE NOT NULL
        );
CREATE TABLE Location (
            location_id INTEGER PRIMARY KEY AUTOINCREMENT,
            city TEXT UNIQUE NOT NULL,
            state TEXT NOT NULL DEFAULT 'Unknown',
            country TEXT NOT NULL DEFAULT 'India',
            risk_zone TEXT NOT NULL DEFAULT 'Medium'
                CHECK(risk_zone IN ('Low', 'Medium', 'High'))
        );
CREATE TABLE Transaction_Type (
            transaction_type_id INTEGER PRIMARY KEY AUTOINCREMENT,
            type_name TEXT UNIQUE NOT NULL
                CHECK(type_name IN ('ATM', 'Online', 'POS', 'UPI', 'NEFT', 'IMPS'))
        );
CREATE TABLE Transaction_Audit (
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
CREATE TABLE Table_Lock (
            lock_name TEXT PRIMARY KEY,
            lock_mode TEXT NOT NULL CHECK(lock_mode IN ('SHARED', 'EXCLUSIVE')),
            owner_session TEXT NOT NULL,
            acquired_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
CREATE TABLE Account_Lock (
            account_id INTEGER PRIMARY KEY,
            lock_mode TEXT NOT NULL CHECK(lock_mode IN ('SHARED', 'EXCLUSIVE')),
            owner_session TEXT NOT NULL,
            acquired_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_id) REFERENCES Account(account_id)
        );
CREATE TABLE Lock_Log (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            lock_scope TEXT NOT NULL CHECK(lock_scope IN ('TABLE', 'ROW')),
            lock_mode TEXT NOT NULL CHECK(lock_mode IN ('SHARED', 'EXCLUSIVE')),
            resource_name TEXT NOT NULL,
            owner_session TEXT NOT NULL,
            action TEXT NOT NULL CHECK(action IN ('ACQUIRED', 'RELEASED', 'READ_DEMO')),
            note TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
CREATE UNIQUE INDEX idx_prediction_one_per_transaction ON Prediction(transaction_id);
CREATE UNIQUE INDEX idx_alert_one_per_transaction ON Fraud_Alert(transaction_id);
CREATE INDEX idx_transaction_account ON "Transaction"(account_id);
CREATE INDEX idx_transaction_location ON "Transaction"(location_id);
CREATE INDEX idx_prediction_label ON Prediction(predicted_label);
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
CREATE VIEW Transaction_Details AS
        SELECT
            t.transaction_id,
            c.customer_id,
            c.name AS customer_name,
            c.email,
            a.account_id,
            COALESCE(at.type_name, a.account_type) AS account_type,
            a.balance AS current_balance,
            t.amount,
            COALESCE(l.city, t.location) AS location,
            COALESCE(tt.type_name, t.transaction_type) AS transaction_type,
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
/* Transaction_Details(transaction_id,customer_id,customer_name,email,account_id,account_type,current_balance,amount,location,transaction_type,time_of_day,distance_from_home,status,transaction_time,fraud_probability,predicted_label,risk_level,alert_reason) */;
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
/* Fraudulent_Transactions_View(transaction_id,name,account_type,amount,location,risk_level,reason) */;
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
/* Review3_Fraud_Report(transaction_id,customer_name,account_id,amount,location,transaction_type,status,fraud_score_percent,risk_level,transaction_time) */;
CREATE TABLE users (
	id INTEGER NOT NULL, 
	username VARCHAR(64) NOT NULL, 
	email VARCHAR(128) NOT NULL, 
	hashed_password VARCHAR(256) NOT NULL, 
	role VARCHAR(16) NOT NULL, 
	is_active BOOLEAN, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_user_role CHECK (role IN ('admin', 'user')), 
	UNIQUE (email)
);
CREATE INDEX ix_users_id ON users (id);
CREATE UNIQUE INDEX ix_users_username ON users (username);
CREATE TABLE transactions (
	id INTEGER NOT NULL, 
	transaction_id VARCHAR(36) NOT NULL, 
	account_id INTEGER NOT NULL, 
	amount FLOAT NOT NULL, 
	location VARCHAR(64) NOT NULL, 
	transaction_type VARCHAR(16) NOT NULL, 
	time_of_day INTEGER NOT NULL, 
	distance_from_home FLOAT NOT NULL, 
	device_trust_score FLOAT, 
	failed_attempts_24h INTEGER, 
	txn_velocity_1h INTEGER, 
	merchant_risk_score FLOAT, 
	is_international INTEGER, 
	card_present INTEGER, 
	fraud_probability FLOAT, 
	predicted_label VARCHAR(16), 
	risk_level VARCHAR(8), 
	model_version VARCHAR(32), 
	alert_reasons TEXT, 
	status VARCHAR(16), 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_txn_amount_positive CHECK (amount > 0), 
	CONSTRAINT ck_txn_time CHECK (time_of_day BETWEEN 0 AND 23), 
	CONSTRAINT ck_txn_status CHECK (status IN ('APPROVED', 'BLOCKED', 'REVIEW'))
);
CREATE UNIQUE INDEX ix_transactions_transaction_id ON transactions (transaction_id);
CREATE INDEX ix_transactions_id ON transactions (id);
CREATE INDEX ix_transactions_account_id ON transactions (account_id);
CREATE TABLE model_runs (
	id INTEGER NOT NULL, 
	model_name VARCHAR(64) NOT NULL, 
	model_version VARCHAR(32) NOT NULL, 
	accuracy FLOAT, 
	precision FLOAT, 
	recall FLOAT, 
	f1_score FLOAT, 
	roc_auc FLOAT, 
	threshold FLOAT, 
	training_rows INTEGER, 
	metrics_json TEXT, 
	trained_by VARCHAR(64), 
	trained_at DATETIME, 
	PRIMARY KEY (id)
);
CREATE TABLE fraud_alerts (
	id INTEGER NOT NULL, 
	transaction_id VARCHAR(36) NOT NULL, 
	risk_level VARCHAR(8) NOT NULL, 
	reason TEXT NOT NULL, 
	is_resolved BOOLEAN, 
	resolved_by VARCHAR(64), 
	created_at DATETIME, 
	resolved_at DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_alert_risk CHECK (risk_level IN ('Low', 'Medium', 'High')), 
	FOREIGN KEY(transaction_id) REFERENCES transactions (transaction_id)
);
CREATE INDEX ix_fraud_alerts_id ON fraud_alerts (id);
