#!/usr/bin/env python3
import sqlite3, os

db_path = 'data/price/price.db'
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""SELECT p.price, i.name, i.url FROM price_history p
                 JOIN items i ON p.item_id = i.id
                 WHERE i.name LIKE '%リーリエ%' AND i.name LIKE '%決心%' AND i.name LIKE '%SAR%'
                 ORDER BY p.price ASC LIMIT 3""")
    results = c.fetchall()
    if results:
        print('\n✅ TOP3 リーリエの決心 SAR メガブレイブ:\n')
        for i, (price, name, url) in enumerate(results, 1):
            print(f'{i}位: ¥{price:,}')
            print(f'  {name[:65]}')
            print(f'  {url}\n')
    else:
        print('❌ No results found in database')
    conn.close()
else:
    print('❌ Database not found at', db_path)
