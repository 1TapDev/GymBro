-- Users Table
CREATE TABLE users (
    user_id BIGINT PRIMARY KEY,
    username TEXT NOT NULL,
    points INTEGER DEFAULT 0
);

-- Check-ins Table
CREATE TABLE checkins (
    checkin_id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    image_hash TEXT DEFAULT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Progress Table
CREATE TABLE progress (
    user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    total_gym_checkins INTEGER DEFAULT 0,
    total_food_logs INTEGER DEFAULT 0,
    total_weight_change DECIMAL(10,2) DEFAULT 0.0,
    last_logged_weight DECIMAL(10,2) DEFAULT NULL
);

-- Personal Records Table (PRs)
CREATE TABLE personal_records (
    user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    deadlift INTEGER DEFAULT NULL,
    bench INTEGER DEFAULT NULL,
    squat INTEGER DEFAULT NULL
);
