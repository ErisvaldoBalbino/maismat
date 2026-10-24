-- Uma sessão de treino (um "jogo").
CREATE TABLE IF NOT EXISTS sessions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    mode           TEXT    NOT NULL CHECK (mode IN ('timed', 'count', 'table', 'weak')),
    operations     TEXT    NOT NULL,          -- ex.: "add,sub,mul,div"
    difficulty     TEXT    NOT NULL,          -- easy | medium | hard
    time_limit_s   INTEGER,                   -- modo contra o tempo
    question_count INTEGER,                   -- modo N questões / tabuada / revisão
    tables         TEXT,                      -- ex.: "7,8,9" (modo tabuada)
    started_at     TEXT    NOT NULL,          -- ISO 8601, horário local
    ended_at       TEXT
);

-- Cada resposta dada. É a tabela "bruta": todo o resto é calculado a partir dela.
CREATE TABLE IF NOT EXISTS attempts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    op         TEXT    NOT NULL CHECK (op IN ('add', 'sub', 'mul', 'div')),
    a          INTEGER NOT NULL,
    b          INTEGER NOT NULL,
    answer     INTEGER NOT NULL,              -- resposta correta
    given      INTEGER,                       -- resposta digitada (NULL = pulou)
    correct    INTEGER NOT NULL CHECK (correct IN (0, 1)),
    time_ms    INTEGER NOT NULL,
    created_at TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_attempts_session ON attempts (session_id);
CREATE INDEX IF NOT EXISTS idx_attempts_created ON attempts (created_at);
CREATE INDEX IF NOT EXISTS idx_attempts_fact ON attempts (op, a, b);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
