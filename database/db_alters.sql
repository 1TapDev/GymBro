--Question Expansion
ALTER TABLE checkins ADD COLUMN workout TEXT DEFAULT NULL;

ALTER TABLE checkins ADD COLUMN weight DECIMAL(10,2) DEFAULT NULL;

ALTER TABLE checkins ADD COLUMN meal TEXT DEFAULT NULL;

--Image Saving Expansion
ALTER TABLE checkins ADD COLUMN image_path TEXT;

--ORDER BY timestamp DESC
CREATE OR REPLACE VIEW checkins_desc AS
SELECT * FROM checkins ORDER BY timestamp DESC;

CREATE INDEX checkins_timestamp_desc_idx ON checkins (timestamp DESC);

CREATE INDEX checkins_timestamp_desc_idx ON checkins (timestamp DESC);

--Challenges tables
CREATE TABLE challenges (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    goal TEXT NOT NULL,
    start_date date DEFAULT NOW(),
    end_date date NOT NULL,
    status TEXT DEFAULT 'active'
);

CREATE TABLE challenge_participants (
    id SERIAL PRIMARY KEY,
    challenge_id INT REFERENCES challenges(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    username TEXT NOT NULL,
    initial_photos TEXT[],
    current_weight DECIMAL(5,2),
    goal_weight DECIMAL(5,2),
    personal_goal TEXT,
    progress_photos TEXT[],
    final_photos TEXT[],
    votes INT DEFAULT 0
);

CREATE TABLE challenge_votes (
    id SERIAL PRIMARY KEY,
    challenge_id INT REFERENCES challenges(id) ON DELETE CASCADE,
    voter_id BIGINT NOT NULL,
    participant_id BIGINT NOT NULL,
    UNIQUE (challenge_id, voter_id) -- Ensures one vote per challenge per user
);

--Convert timestamp to date in challenges
ALTER TABLE challenges
ALTER COLUMN start_date TYPE DATE USING start_date::DATE,
ALTER COLUMN end_date TYPE DATE USING end_date::DATE;

GRANT ALL PRIVILEGES ON TABLE challenges TO your_db_user;
GRANT ALL PRIVILEGES ON SEQUENCE challenges_id_seq TO your_db_user;

--Add Video Paths to personal_records
ALTER TABLE personal_records
ADD COLUMN deadlift_video TEXT DEFAULT NULL,
ADD COLUMN bench_video TEXT DEFAULT NULL,
ADD COLUMN squat_video TEXT DEFAULT NULL;

--Create Prize suggestion table
CREATE TABLE IF NOT EXISTS prize_suggestions (
    user_id BIGINT PRIMARY KEY,
    username TEXT,
    prize TEXT
);

DROP TABLE IF EXISTS prize_suggestions;

