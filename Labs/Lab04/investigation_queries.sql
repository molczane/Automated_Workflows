-- Write and retain your diagnostic queries here. Use the notebook questions.
-- Enable enforcement when opening your own SQLite session:
PRAGMA foreign_keys = ON;

-- Q1. List requests with their number of attempts, grouped by outcome.

-- Q2. Starting from an NDVI artifact ID, find its successful producing attempt,
-- normalized request, each input role, original Lab 3 subset, scene, band and AOI.

-- Q3. Find failed/interrupted attempts with stage and error; retain recovery rows.

-- Q4. Find succeeded attempts whose returned artifact has no available location.
-- Explain why SQL alone cannot prove current filesystem availability.

-- Q5. Find running attempts and inspect temp/final path, receipt and output links.

-- Q6. Compare original calibration metadata with the reviewed configuration.
