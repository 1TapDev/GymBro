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