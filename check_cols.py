import sqlite3

conn = sqlite3.connect('shop.db')
cursor = conn.cursor()
cursor.execute("PRAGMA table_info(inventory);") # Changed 'shop' to 'inventory'
columns = [info[1] for info in cursor.fetchall()]
print("THE ACTUAL COLUMN NAMES IN 'inventory' ARE:", columns)
conn.close()