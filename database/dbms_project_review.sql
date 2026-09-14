-- ==========================================================
-- DBMS PROJECT REVIEW - WEEKS 4 TO 6
-- ==========================================================

-- 🔥 WEEK 4 IMPLEMENTATION

-- ✅ 1. CONSTRAINTS
ALTER TABLE "Transaction"
ADD CONSTRAINT chk_amount CHECK (amount > 0);

-- ✅ 2. AGGREGATE FUNCTIONS
-- Total transaction per account
SELECT account_id, SUM(amount) AS total_amount
FROM "Transaction"
GROUP BY account_id;

-- Average transaction
SELECT AVG(amount) AS avg_transaction FROM "Transaction";

-- Maximum transaction
SELECT MAX(amount) AS highest_transaction FROM "Transaction";

-- ✅ 3. SET OPERATIONS (MySQL compatible)
-- Accounts with Chennai transactions
SELECT account_id FROM "Transaction" WHERE location='Chennai';

-- Accounts in both Chennai and Mumbai
SELECT account_id 
FROM "Transaction" 
WHERE location='Chennai'
AND account_id IN (
    SELECT account_id FROM "Transaction" WHERE location='Mumbai'
);

-- Chennai but not Delhi
SELECT account_id 
FROM "Transaction" 
WHERE location='Chennai'
AND account_id NOT IN (
    SELECT account_id FROM "Transaction" WHERE location='Delhi'
);


-- 🔥 WEEK 5 IMPLEMENTATION

-- ✅ 4. SUBQUERIES
-- Transactions above average
SELECT * FROM "Transaction"
WHERE amount > (SELECT AVG(amount) FROM "Transaction");

-- Accounts with high balance
SELECT * FROM Account
WHERE balance > (SELECT AVG(balance) FROM Account);

-- ✅ 5. JOINS (IMPORTANT FOR VIVA)
-- Customer + Account
SELECT c.name, a.account_id, a.balance
FROM Customer c
JOIN Account a ON c.customer_id = a.customer_id;

-- Full fraud analysis 🔥
SELECT c.name, t.transaction_id, p.fraud_probability, f.risk_level
FROM Customer c
JOIN Account a ON c.customer_id = a.customer_id
JOIN "Transaction" t ON a.account_id = t.account_id
JOIN Prediction p ON t.transaction_id = p.transaction_id
LEFT JOIN Fraud_Alert f ON t.transaction_id = f.transaction_id;

-- ✅ 6. VIEWS
CREATE VIEW HighRiskTransactions AS
SELECT t.transaction_id, p.fraud_probability
FROM "Transaction" t
JOIN Prediction p ON t.transaction_id = p.transaction_id
WHERE p.fraud_probability > 0.7;

-- Use it
SELECT * FROM HighRiskTransactions;

-- Count
SELECT COUNT(*) FROM HighRiskTransactions;


-- 🔥 WEEK 6 IMPLEMENTATION (MySQL Syntax for Stored Procedures & Functions)

-- ✅ 7. FUNCTIONS (MySQL Stored Function)
DELIMITER //

CREATE FUNCTION get_risk_level(prob FLOAT)
RETURNS VARCHAR(10)
DETERMINISTIC
BEGIN
    DECLARE risk VARCHAR(10);

    IF prob > 0.8 THEN
        SET risk = 'High';
    ELSEIF prob > 0.5 THEN
        SET risk = 'Medium';
    ELSE
        SET risk = 'Low';
    END IF;

    RETURN risk;
END //

DELIMITER ;

-- ✅ 8. TRIGGERS (VERY IMPORTANT 🔥)
DELIMITER //

CREATE TRIGGER fraud_trigger
AFTER INSERT ON Prediction
FOR EACH ROW
BEGIN
    IF NEW.fraud_probability > 0.8 THEN
        INSERT INTO Fraud_Alert(transaction_id, risk_level, reason)
        VALUES (NEW.transaction_id, 'High', 'ML detected fraud');
    END IF;
END //

DELIMITER ;

-- ✅ 9. CURSORS
DELIMITER //

CREATE PROCEDURE high_transactions()
BEGIN
    DECLARE done INT DEFAULT FALSE;
    DECLARE t_id INT;
    DECLARE amt FLOAT;

    DECLARE cur CURSOR FOR 
        SELECT transaction_id, amount FROM "Transaction" WHERE amount > 10000;

    DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = TRUE;

    OPEN cur;

    read_loop: LOOP
        FETCH cur INTO t_id, amt;
        IF done THEN
            LEAVE read_loop;
        END IF;
    END LOOP;

    CLOSE cur;
END //

DELIMITER ;

-- ✅ 10. EXCEPTION HANDLING
DELIMITER //

CREATE PROCEDURE safe_insert()
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        SELECT 'Error occurred, rolling back';
        ROLLBACK;
    END;

    START TRANSACTION;

    INSERT INTO "Transaction"(account_id, amount)
    VALUES (1, -5000); -- will fail

    COMMIT;
END //

DELIMITER ;

-- ==========================================================
-- REVIEW 3 RUBRICS IMPLEMENTATION
-- ==========================================================

-- 🔥 1. NORMALIZATION (Dependencies & Anomalies)
/*
Normalization up to 3NF achieved:

1. Customer Table:
   FD: customer_id -> name, email, phone
   (In 3NF: All non-key attributes depend strictly on the primary key; no partial or transitive dependencies.)

2. Account Table:
   FD: account_id -> customer_id, account_type, balance
   (In 3NF: 'balance' and 'account_type' depend strictly on 'account_id'.)

3. Transaction Table:
   FD: transaction_id -> account_id, amount, location, transaction_type, time_of_day, distance_from_home, transaction_time
   (In 3NF: No transitive dependencies.)

Anomalies Addressed:
- Update Anomaly: Customer information (e.g., email) is stored in one place. Updating it doesn't cause inconsistencies across multiple transaction records.
- Insertion Anomaly: A new Customer can be registered without immediately requiring a Transaction or Account record.
- Deletion Anomaly: Deleting a Transaction record does not lead to the loss of Account or Customer data.
*/

-- 🔥 2. TRANSACTION MANAGEMENT (ACID Properties)
DELIMITER //

CREATE PROCEDURE execute_secure_transfer(IN sender_acc INT, IN receiver_acc INT, IN transfer_amount REAL)
BEGIN
    -- ATOMICITY & DURABILITY: Handled via the EXIT HANDLER and explicit transaction controls.
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        SELECT 'Transaction Failed: Rollback executed (Atomicity restored)';
    END;

    -- START TRANSACTION represents ISOLATION scope
    START TRANSACTION;
    
    -- CONSISTENCY: State transition check
    -- Ensure sender has enough balance
    UPDATE Account 
    SET balance = balance - transfer_amount 
    WHERE account_id = sender_acc AND balance >= transfer_amount;
    
    -- Update receiver
    UPDATE Account 
    SET balance = balance + transfer_amount 
    WHERE account_id = receiver_acc;
    
    -- Add transaction records
    INSERT INTO "Transaction"(account_id, amount, transaction_type) 
    VALUES (sender_acc, transfer_amount, 'Debit');
    INSERT INTO "Transaction"(account_id, amount, transaction_type) 
    VALUES (receiver_acc, transfer_amount, 'Credit');
    
    -- COMMIT ensures DURABILITY
    COMMIT;
    
    SELECT 'Transaction Successful: Commit executed';
END //

DELIMITER ;

-- 🔥 3. CONCURRENCY CONTROL (Locking Mechanisms)

-- Example 3.1: Table-Level Locking
-- ----------------------------------------------------
-- Exclusive (WRITE) lock to safely modify high-volume batch data
LOCK TABLES Account WRITE;
UPDATE Account SET balance = balance * 1.05 WHERE account_type = 'Savings';
UNLOCK TABLES;

-- Shared (READ) lock to safely generate reports without data mutating underneath
LOCK TABLES "Transaction" READ;
SELECT SUM(amount) AS total_amount FROM "Transaction" WHERE location = 'Chennai';
UNLOCK TABLES;


-- Example 3.2: Row-Level Locking
-- ----------------------------------------------------
-- Shared Lock (READ) - using LOCK IN SHARE MODE
-- Other transactions can read this row but cannot modify it until we COMMIT
START TRANSACTION;
SELECT balance FROM Account WHERE account_id = 101 LOCK IN SHARE MODE;
-- [Application logic to evaluate balance]
COMMIT;

-- Exclusive Lock (WRITE) - using FOR UPDATE
-- Prevents other transactions from reading, updating, or deleting this row until COMMIT
START TRANSACTION;
SELECT balance FROM Account WHERE account_id = 102 FOR UPDATE;
UPDATE Account SET balance = balance - 1000 WHERE account_id = 102;
COMMIT;
