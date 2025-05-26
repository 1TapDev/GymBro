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

-- Add missing columns to challenges table
ALTER TABLE challenges ADD COLUMN IF NOT EXISTS photo_collection_started BOOLEAN DEFAULT FALSE;
ALTER TABLE challenges ADD COLUMN IF NOT EXISTS photo_collection_deadline TIMESTAMP DEFAULT NULL;
ALTER TABLE challenges ADD COLUMN IF NOT EXISTS voting_started BOOLEAN DEFAULT FALSE;
ALTER TABLE challenges ADD COLUMN IF NOT EXISTS voting_end_time TIMESTAMP DEFAULT NULL;
ALTER TABLE challenges ADD COLUMN IF NOT EXISTS voting_messages JSONB DEFAULT NULL;
ALTER TABLE challenges ADD COLUMN IF NOT EXISTS results_posted BOOLEAN DEFAULT FALSE;
ALTER TABLE challenges ADD COLUMN IF NOT EXISTS message_id BIGINT DEFAULT NULL;
ALTER TABLE challenges ADD COLUMN IF NOT EXISTS channel_id BIGINT DEFAULT NULL;

-- Add missing columns to challenge_participants table
ALTER TABLE challenge_participants ADD COLUMN IF NOT EXISTS final_weight DECIMAL(5,2) DEFAULT NULL;
ALTER TABLE challenge_participants ADD COLUMN IF NOT EXISTS final_photos TEXT[] DEFAULT NULL;
ALTER TABLE challenge_participants ADD COLUMN IF NOT EXISTS submitted_final BOOLEAN DEFAULT FALSE;
ALTER TABLE challenge_participants ADD COLUMN IF NOT EXISTS disqualified BOOLEAN DEFAULT FALSE;
ALTER TABLE challenge_participants ADD COLUMN IF NOT EXISTS disqualification_reason TEXT DEFAULT NULL;
ALTER TABLE challenge_participants ADD COLUMN IF NOT EXISTS final_rank INTEGER DEFAULT NULL;
ALTER TABLE challenge_participants ADD COLUMN IF NOT EXISTS votes_received INTEGER DEFAULT 0;

-- Update challenges table to use TIMESTAMP instead of DATE for better precision
ALTER TABLE challenges ALTER COLUMN start_date TYPE TIMESTAMP USING start_date::TIMESTAMP;
ALTER TABLE challenges ALTER COLUMN end_date TYPE TIMESTAMP USING end_date::TIMESTAMP;

-- Make sure all boolean columns have proper defaults
UPDATE challenges SET photo_collection_started = FALSE WHERE photo_collection_started IS NULL;
UPDATE challenges SET voting_started = FALSE WHERE voting_started IS NULL;
UPDATE challenges SET results_posted = FALSE WHERE results_posted IS NULL;

UPDATE challenge_participants SET submitted_final = FALSE WHERE submitted_final IS NULL;
UPDATE challenge_participants SET disqualified = FALSE WHERE disqualified IS NULL;
UPDATE challenge_participants SET votes_received = 0 WHERE votes_received IS NULL;

-- Add indexes for better performance
CREATE INDEX IF NOT EXISTS idx_challenges_status ON challenges(status);
CREATE INDEX IF NOT EXISTS idx_challenges_end_date ON challenges(end_date);
CREATE INDEX IF NOT EXISTS idx_challenge_participants_challenge_id ON challenge_participants(challenge_id);
CREATE INDEX IF NOT EXISTS idx_challenge_participants_user_id ON challenge_participants(user_id);