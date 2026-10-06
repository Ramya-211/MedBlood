-- ============================================================
-- Integrated Medicine & Blood Management — MySQL Schema
-- Raw SQL only. No ORM. Run this once to create the database
-- structure before running the importers.
-- ============================================================

CREATE DATABASE IF NOT EXISTS medblood_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE medblood_db;

-- ------------------------------------------------------------
-- AUTH / USERS
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(64) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(128) NOT NULL,
    role ENUM('ADMIN', 'PHARMACIST', 'BLOOD_STAFF') NOT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at DATETIME NULL,
    INDEX idx_users_role (role)
) ENGINE=InnoDB;

-- Revoked JWTs (server-side logout). A token whose jti is listed here is rejected
-- even if its signature and expiry are still valid. Expired rows are purged lazily.
CREATE TABLE IF NOT EXISTS revoked_tokens (
    jti CHAR(36) PRIMARY KEY,
    user_id INT NOT NULL,
    expires_at DATETIME NOT NULL,
    revoked_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_revoked_expires (expires_at)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- MEDICINE MODULE
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS medicines (
    medicine_id VARCHAR(20) PRIMARY KEY,
    medicine_name VARCHAR(128) NOT NULL,
    composition VARCHAR(255),
    manufacturer VARCHAR(128),
    dosage_form VARCHAR(32),
    pack_size VARCHAR(32),
    category VARCHAR(64),
    provenance VARCHAR(32) NOT NULL DEFAULT 'SYNTHETIC_PLACEHOLDER'
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS medicine_demand (
    id INT AUTO_INCREMENT PRIMARY KEY,
    record_id INT NOT NULL,
    demand_date DATE NOT NULL,
    medicine_id VARCHAR(20) NOT NULL,
    category VARCHAR(64),
    units_requested INT NOT NULL,
    units_issued INT NOT NULL,
    units_dispensed INT NOT NULL,
    FOREIGN KEY (medicine_id) REFERENCES medicines(medicine_id),
    INDEX idx_med_demand_date (demand_date),
    INDEX idx_med_demand_medicine_date (medicine_id, demand_date)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS medicine_demand_features (
    id INT AUTO_INCREMENT PRIMARY KEY,
    feature_date DATE NOT NULL,
    medicine_id VARCHAR(20) NOT NULL,
    daily_demand INT,
    weekly_demand DOUBLE,
    monthly_demand DOUBLE,
    rolling_mean_7 DOUBLE,
    rolling_mean_30 DOUBLE,
    growth_rate_7d DOUBLE,
    growth_rate_30d DOUBLE,
    trend_slope DOUBLE,
    month_num TINYINT,
    day_of_week TINYINT,
    season VARCHAR(20),
    seasonality_index DOUBLE,
    lag_1 DOUBLE,
    lag_7 DOUBLE,
    lag_14 DOUBLE,
    lag_30 DOUBLE,
    anomaly_flag TINYINT,
    anomaly_score DOUBLE,
    FOREIGN KEY (medicine_id) REFERENCES medicines(medicine_id),
    INDEX idx_med_feat_date (feature_date),
    INDEX idx_med_feat_medicine_date (medicine_id, feature_date)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS medicine_inventory (
    inventory_id INT PRIMARY KEY,
    inv_date DATE NOT NULL,
    medicine_id VARCHAR(20) NOT NULL,
    opening_stock INT NOT NULL,
    units_received INT NOT NULL,
    units_issued INT NOT NULL,
    units_adjusted INT NOT NULL,
    closing_stock INT NOT NULL,
    stock_status ENUM('Critical','Low','Normal','Overstock') NOT NULL,
    FOREIGN KEY (medicine_id) REFERENCES medicines(medicine_id),
    INDEX idx_med_inv_date (inv_date),
    INDEX idx_med_inv_medicine_date (medicine_id, inv_date),
    INDEX idx_med_inv_status (stock_status)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS medicine_batches (
    batch_id VARCHAR(40) PRIMARY KEY,
    medicine_id VARCHAR(20) NOT NULL,
    batch_number VARCHAR(64),
    manufacturing_date DATE NOT NULL,
    expiry_date DATE NOT NULL,
    units_in_batch INT NOT NULL,
    units_remaining INT NOT NULL,
    expiry_status ENUM('Safe','Near Expiry','Expired') NOT NULL,
    FOREIGN KEY (medicine_id) REFERENCES medicines(medicine_id),
    INDEX idx_med_batch_medicine (medicine_id),
    INDEX idx_med_batch_expiry (expiry_date),
    INDEX idx_med_batch_status (expiry_status)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS medicine_expiry_alerts (
    alert_id INT PRIMARY KEY,
    alert_date DATE NOT NULL,
    medicine_id VARCHAR(20) NOT NULL,
    batch_id VARCHAR(40) NOT NULL,
    expiry_date DATE NOT NULL,
    days_to_expiry INT NOT NULL,
    severity ENUM('Info','Warning','Critical') NOT NULL,
    message VARCHAR(500),
    FOREIGN KEY (medicine_id) REFERENCES medicines(medicine_id),
    FOREIGN KEY (batch_id) REFERENCES medicine_batches(batch_id),
    INDEX idx_med_exp_alert_date (alert_date),
    INDEX idx_med_exp_alert_severity (severity)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS medicine_alerts (
    alert_id INT PRIMARY KEY,
    alert_date DATE NOT NULL,
    medicine_id VARCHAR(20) NOT NULL,
    alert_type VARCHAR(40) NOT NULL,
    severity ENUM('Info','Warning','Critical') NOT NULL,
    message VARCHAR(500),
    FOREIGN KEY (medicine_id) REFERENCES medicines(medicine_id),
    INDEX idx_med_alert_date (alert_date),
    INDEX idx_med_alert_type (alert_type),
    INDEX idx_med_alert_severity (severity)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS medicine_recommendations (
    recommendation_id INT PRIMARY KEY,
    rec_date DATE NOT NULL,
    medicine_id VARCHAR(20) NOT NULL,
    recommendation_type VARCHAR(60) NOT NULL,
    severity ENUM('Info','Warning','Critical') NOT NULL,
    reason VARCHAR(500),
    recommended_action VARCHAR(255),
    FOREIGN KEY (medicine_id) REFERENCES medicines(medicine_id),
    INDEX idx_med_rec_date (rec_date),
    INDEX idx_med_rec_type (recommendation_type)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS medicine_volume_tiers (
    medicine_id VARCHAR(20) PRIMARY KEY,
    total_units_dispensed INT NOT NULL,
    volume_tier ENUM('Fast Moving','Medium Moving','Slow Moving') NOT NULL,
    FOREIGN KEY (medicine_id) REFERENCES medicines(medicine_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS medicine_trend_analysis (
    medicine_id VARCHAR(20) PRIMARY KEY,
    trend_slope DOUBLE NOT NULL,
    trend_direction ENUM('Increasing','Decreasing','Stable') NOT NULL,
    growth_rate_7d DOUBLE,
    growth_rate_30d DOUBLE,
    FOREIGN KEY (medicine_id) REFERENCES medicines(medicine_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS medicine_seasonality (
    id INT AUTO_INCREMENT PRIMARY KEY,
    medicine_id VARCHAR(20) NOT NULL,
    month_num TINYINT NOT NULL,
    season VARCHAR(20) NOT NULL,
    seasonality_index DOUBLE,
    FOREIGN KEY (medicine_id) REFERENCES medicines(medicine_id),
    INDEX idx_med_season_medicine (medicine_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS medicine_demand_anomalies (
    id INT AUTO_INCREMENT PRIMARY KEY,
    anomaly_date DATE NOT NULL,
    medicine_id VARCHAR(20) NOT NULL,
    actual_demand INT NOT NULL,
    expected_demand DOUBLE,
    anomaly_score DOUBLE,
    anomaly_flag TINYINT NOT NULL,
    anomaly_type VARCHAR(40),
    FOREIGN KEY (medicine_id) REFERENCES medicines(medicine_id),
    INDEX idx_med_anomaly_date (anomaly_date),
    INDEX idx_med_anomaly_medicine (medicine_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS medicine_model_comparison (
    id INT AUTO_INCREMENT PRIMARY KEY,
    model_name VARCHAR(60) NOT NULL,
    rmse DOUBLE NOT NULL,
    mae DOUBLE NOT NULL,
    r2 DOUBLE NOT NULL,
    generated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS medicine_actual_vs_predicted (
    id INT AUTO_INCREMENT PRIMARY KEY,
    avp_date DATE NOT NULL,
    medicine_id VARCHAR(20) NOT NULL,
    actual_demand DOUBLE NOT NULL,
    predicted_demand DOUBLE NOT NULL,
    prediction_error DOUBLE NOT NULL,
    source ENUM('BACKTEST') NOT NULL DEFAULT 'BACKTEST',
    FOREIGN KEY (medicine_id) REFERENCES medicines(medicine_id),
    INDEX idx_med_avp_date (avp_date),
    INDEX idx_med_avp_medicine (medicine_id)
) ENGINE=InnoDB;

-- Model-generated FUTURE forecasts (never mixed with the supplied BACKTEST rows above).
-- Written only by `python -m app.ml.medicine_ml train`; one run = one trained model + horizon.
CREATE TABLE IF NOT EXISTS medicine_forecast_runs (
    run_id INT AUTO_INCREMENT PRIMARY KEY,
    generated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    model_name VARCHAR(60) NOT NULL,
    trained_through_date DATE NOT NULL,
    training_rows INT NOT NULL,
    horizon_days INT NOT NULL,
    hyperparameters JSON NULL,
    selection_basis VARCHAR(500) NOT NULL,
    reproduction_check JSON NULL,
    notes VARCHAR(500) NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS medicine_forecasts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    run_id INT NOT NULL,
    medicine_id VARCHAR(20) NOT NULL,
    origin_date DATE NOT NULL,
    forecast_date DATE NOT NULL,
    horizon_step INT NOT NULL,
    uses_predicted_inputs TINYINT NOT NULL,
    predicted_demand DOUBLE NOT NULL,
    FOREIGN KEY (run_id) REFERENCES medicine_forecast_runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY (medicine_id) REFERENCES medicines(medicine_id),
    UNIQUE KEY uq_med_forecast (run_id, medicine_id, forecast_date),
    INDEX idx_med_fc_date (forecast_date),
    INDEX idx_med_fc_medicine (medicine_id)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- BLOOD MODULE (composite natural key: blood_group + rh_type + blood_component)
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS blood_demand (
    id INT AUTO_INCREMENT PRIMARY KEY,
    record_id INT NOT NULL,
    demand_date DATE NOT NULL,
    blood_group ENUM('A','B','AB','O') NOT NULL,
    rh_type ENUM('Positive','Negative') NOT NULL,
    blood_component ENUM('Whole Blood','RBC','Platelets','Plasma') NOT NULL,
    units_requested INT NOT NULL,
    units_issued INT NOT NULL,
    units_transfused INT NOT NULL,
    emergency_requests INT NOT NULL,
    routine_requests INT NOT NULL,
    INDEX idx_blood_demand_date (demand_date),
    INDEX idx_blood_demand_segment_date (blood_group, rh_type, blood_component, demand_date)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS blood_demand_features (
    id INT AUTO_INCREMENT PRIMARY KEY,
    feature_date DATE NOT NULL,
    blood_group ENUM('A','B','AB','O') NOT NULL,
    rh_type ENUM('Positive','Negative') NOT NULL,
    blood_component ENUM('Whole Blood','RBC','Platelets','Plasma') NOT NULL,
    daily_demand INT,
    weekly_demand DOUBLE,
    monthly_demand DOUBLE,
    rolling_mean_7 DOUBLE,
    rolling_mean_30 DOUBLE,
    growth_rate_7d DOUBLE,
    growth_rate_30d DOUBLE,
    trend_slope DOUBLE,
    month_num TINYINT,
    day_of_week TINYINT,
    season VARCHAR(20),
    seasonality_index DOUBLE,
    lag_1 DOUBLE,
    lag_7 DOUBLE,
    lag_14 DOUBLE,
    lag_30 DOUBLE,
    anomaly_flag TINYINT,
    anomaly_score DOUBLE,
    INDEX idx_blood_feat_date (feature_date),
    INDEX idx_blood_feat_segment_date (blood_group, rh_type, blood_component, feature_date)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS blood_collection (
    id INT AUTO_INCREMENT PRIMARY KEY,
    collection_date DATE NOT NULL,
    blood_type VARCHAR(4) NOT NULL,
    donation_volume INT NOT NULL,
    data_type VARCHAR(32) NOT NULL,
    INDEX idx_blood_collection_date (collection_date)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS blood_inventory (
    inventory_id INT PRIMARY KEY,
    inv_date DATE NOT NULL,
    blood_group ENUM('A','B','AB','O') NOT NULL,
    rh_type ENUM('Positive','Negative') NOT NULL,
    blood_component ENUM('Whole Blood','RBC','Platelets','Plasma') NOT NULL,
    opening_stock INT NOT NULL,
    units_received INT NOT NULL,
    units_issued INT NOT NULL,
    units_discarded INT NOT NULL,
    units_expired INT NOT NULL,
    closing_stock INT NOT NULL,
    INDEX idx_blood_inv_date (inv_date),
    INDEX idx_blood_inv_segment_date (blood_group, rh_type, blood_component, inv_date)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS blood_batches (
    batch_id VARCHAR(40) PRIMARY KEY,
    collection_date DATE NOT NULL,
    expiry_date DATE NOT NULL,
    blood_group ENUM('A','B','AB','O') NOT NULL,
    rh_type ENUM('Positive','Negative') NOT NULL,
    blood_component ENUM('Whole Blood','RBC','Platelets','Plasma') NOT NULL,
    units_in_batch INT NOT NULL,
    units_remaining INT NOT NULL,
    expiry_status ENUM('Safe','Near Expiry','Expired') NOT NULL,
    INDEX idx_blood_batch_segment (blood_group, rh_type, blood_component),
    INDEX idx_blood_batch_expiry (expiry_date),
    INDEX idx_blood_batch_status (expiry_status)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS blood_alerts (
    alert_id INT PRIMARY KEY,
    alert_date DATE NOT NULL,
    blood_group ENUM('A','B','AB','O') NOT NULL,
    rh_type ENUM('Positive','Negative') NOT NULL,
    blood_component ENUM('Whole Blood','RBC','Platelets','Plasma') NOT NULL,
    alert_type VARCHAR(40) NOT NULL,
    severity ENUM('Info','Warning','Critical') NOT NULL,
    message VARCHAR(500),
    INDEX idx_blood_alert_date (alert_date),
    INDEX idx_blood_alert_type (alert_type),
    INDEX idx_blood_alert_severity (severity)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS blood_recommendations (
    recommendation_id INT PRIMARY KEY,
    rec_date DATE NOT NULL,
    blood_group ENUM('A','B','AB','O') NOT NULL,
    rh_type ENUM('Positive','Negative') NOT NULL,
    blood_component ENUM('Whole Blood','RBC','Platelets','Plasma') NOT NULL,
    current_stock INT,
    predicted_demand DOUBLE NULL,
    days_of_cover DOUBLE,
    recommendation_type VARCHAR(60) NOT NULL,
    severity ENUM('Info','Warning','Critical') NOT NULL,
    reason VARCHAR(500) NOT NULL,
    INDEX idx_blood_rec_date (rec_date),
    INDEX idx_blood_rec_type (recommendation_type)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS blood_model_comparison (
    id INT AUTO_INCREMENT PRIMARY KEY,
    model_name VARCHAR(60) NOT NULL,
    rmse DOUBLE NOT NULL,
    mae DOUBLE NOT NULL,
    r2 DOUBLE NOT NULL,
    generated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS blood_actual_vs_predicted (
    id INT AUTO_INCREMENT PRIMARY KEY,
    avp_date DATE NOT NULL,
    blood_group ENUM('A','B','AB','O') NOT NULL,
    rh_type ENUM('Positive','Negative') NOT NULL,
    blood_component ENUM('Whole Blood','RBC','Platelets','Plasma') NOT NULL,
    actual_demand DOUBLE NOT NULL,
    predicted_demand DOUBLE NOT NULL,
    prediction_error DOUBLE NOT NULL,
    source ENUM('BACKTEST') NOT NULL DEFAULT 'BACKTEST',
    INDEX idx_blood_avp_date (avp_date),
    INDEX idx_blood_avp_segment (blood_group, rh_type, blood_component)
) ENGINE=InnoDB;

-- Model-generated FUTURE forecasts for BLOOD (mirrors medicine_forecast_runs/medicine_forecasts).
-- Never mixed with the supplied BACKTEST rows in blood_actual_vs_predicted.
CREATE TABLE IF NOT EXISTS blood_forecast_runs (
    run_id INT AUTO_INCREMENT PRIMARY KEY,
    generated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    model_name VARCHAR(60) NOT NULL,
    trained_through_date DATE NOT NULL,
    training_rows INT NOT NULL,
    horizon_days INT NOT NULL,
    hyperparameters JSON NULL,
    selection_basis VARCHAR(500) NOT NULL,
    reproduction_check JSON NULL,
    notes VARCHAR(500) NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS blood_forecasts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    run_id INT NOT NULL,
    blood_group ENUM('A','B','AB','O') NOT NULL,
    rh_type ENUM('Positive','Negative') NOT NULL,
    blood_component ENUM('Whole Blood','RBC','Platelets','Plasma') NOT NULL,
    origin_date DATE NOT NULL,
    forecast_date DATE NOT NULL,
    horizon_step INT NOT NULL,
    uses_predicted_inputs TINYINT NOT NULL,
    predicted_demand DOUBLE NOT NULL,
    FOREIGN KEY (run_id) REFERENCES blood_forecast_runs(run_id) ON DELETE CASCADE,
    UNIQUE KEY uq_blood_forecast (run_id, blood_group, rh_type, blood_component, forecast_date),
    INDEX idx_blood_fc_date (forecast_date),
    INDEX idx_blood_fc_segment (blood_group, rh_type, blood_component)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- CHATBOT (conversation memory)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chat_conversations (
    id VARCHAR(36) PRIMARY KEY,
    user_id INT NOT NULL,
    started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_message_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- Small structured "focus" used to resolve follow-up questions ("its demand", "and next month").
    -- Never holds secrets; only entity references (medicine_id, blood segment, metric, date range).
    context_state JSON NULL,
    FOREIGN KEY (user_id) REFERENCES users(id),
    INDEX idx_chat_conv_user (user_id, last_message_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS chat_messages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    conversation_id VARCHAR(36) NOT NULL,
    role ENUM('user','assistant') NOT NULL,
    content TEXT NOT NULL,
    intent VARCHAR(60) NULL,
    tool_calls JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES chat_conversations(id) ON DELETE CASCADE,
    INDEX idx_chat_msg_conv (conversation_id, created_at)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- IMPORT LOG (used by importers to record what happened)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS import_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    dataset_name VARCHAR(64) NOT NULL,
    file_name VARCHAR(128) NOT NULL,
    rows_read INT NOT NULL,
    rows_inserted INT NOT NULL,
    rows_rejected INT NOT NULL,
    started_at DATETIME NOT NULL,
    finished_at DATETIME NOT NULL,
    notes TEXT
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- UPGRADE STATEMENTS (idempotent) for databases created in earlier phases
-- ------------------------------------------------------------
ALTER TABLE medicine_actual_vs_predicted MODIFY COLUMN source ENUM('BACKTEST') NOT NULL DEFAULT 'BACKTEST';
ALTER TABLE blood_actual_vs_predicted MODIFY COLUMN source ENUM('BACKTEST') NOT NULL DEFAULT 'BACKTEST';

ALTER TABLE blood_actual_vs_predicted MODIFY COLUMN source ENUM('BACKTEST') NOT NULL DEFAULT 'BACKTEST';
