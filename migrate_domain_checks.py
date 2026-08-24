from sqlalchemy import text
from database.database import engine

with engine.connect() as c:
    try:
        c.execute(text("ALTER TABLE domain_checks ADD COLUMN blacklist_details JSON"))
    except Exception as e: print(e)
    try:
        c.execute(text("ALTER TABLE domain_checks ADD COLUMN ip_reputation JSON"))
    except Exception as e: print(e)
    try:
        c.execute(text("ALTER TABLE domain_checks ADD COLUMN resolved_ips JSON"))
    except Exception as e: print(e)
    c.commit()
