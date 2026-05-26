import sqlite3

DB_PATH = "shop.db"

conn = sqlite3.connect(DB_PATH)

conn.execute("""
    CREATE TABLE temp_inventory (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        item_name      TEXT,
        category       TEXT,
        price          REAL,
        stock_quantity INTEGER,
        image_path     TEXT
    )
""")

conn.execute("""
    INSERT INTO temp_inventory (item_name, category, price, stock_quantity, image_path)
    SELECT item_name, category, price, stock_quantity, image_path FROM inventory
""")

conn.execute("DROP TABLE inventory")
conn.execute("ALTER TABLE temp_inventory RENAME TO inventory")
conn.commit()
conn.close()

print("Repair complete: inventory table rebuilt with fresh sequential IDs.")
