import sqlite3
import os

# DORY_DB_PATH moves the database (e.g. onto a server's permanent disk); default: next to this file.
DB_PATH = os.getenv("DORY_DB_PATH") or os.path.join(os.path.dirname(__file__), "dory.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    conn = get_connection()
    with open(schema_path, "r") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()

def add_fact(persona_id: str, fact_text: str, source_type: str, source_quote: str) -> str:
    conn = get_connection()
    cursor = conn.cursor()
    fact_id = f"fact_{os.urandom(4).hex()}"
    cursor.execute(
        "INSERT INTO facts (id, persona_id, fact_text, source_type, source_quote) VALUES (?, ?, ?, ?, ?)",
        (fact_id, persona_id, fact_text, source_type, source_quote)
    )
    conn.commit()
    conn.close()
    return fact_id

def get_facts(persona_id: str) -> list[str]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT fact_text FROM facts WHERE persona_id = ?", (persona_id,))
    rows = cursor.fetchall()
    conn.close()
    return [row["fact_text"] for row in rows]

if __name__ == "__main__":
    init_db()
    # Test adding a dummy fact
    add_fact("mary_1", "Anu visited yesterday and brought fish curry.", "evening_chat", "Anu visited yesterday")
    print("Stored facts for mary_1:", get_facts("mary_1"))