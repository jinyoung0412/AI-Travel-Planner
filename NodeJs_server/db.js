const Database = require('better-sqlite3');
const path = require('path');

const db = new Database(path.join(__dirname, 'users.db'));

db.exec(`
  CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kakao_id   TEXT UNIQUE NOT NULL,
    nickname   TEXT,
    profile_img TEXT,
    created_at TEXT DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS saved_spots (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    lat        REAL,
    lng        REAL,
    category   TEXT,
    kakao_url  TEXT,
    saved_at   TEXT DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS saved_courses (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    region     TEXT,
    created_at TEXT DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS saved_course_spots (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id  INTEGER NOT NULL REFERENCES saved_courses(id) ON DELETE CASCADE,
    spot_order INTEGER NOT NULL,
    name       TEXT NOT NULL,
    lat        REAL,
    lng        REAL,
    category   TEXT,
    kakao_url  TEXT
  );
`);

module.exports = db;
