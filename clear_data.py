from sqlalchemy import text
from database.database import engine, SessionLocal

with engine.connect() as c:
    try:
        c.execute(text("TRUNCATE TABLE issues CASCADE"))
        c.execute(text("TRUNCATE TABLE mailbox_checks CASCADE"))
        c.execute(text("TRUNCATE TABLE domain_checks CASCADE"))
        c.execute(text("TRUNCATE TABLE health_snapshots CASCADE"))
        c.execute(text("TRUNCATE TABLE instantly_tests CASCADE"))
        c.execute(text("TRUNCATE TABLE provider_runs CASCADE"))
        c.execute(text("TRUNCATE TABLE scan_runs CASCADE"))
        c.execute(text("TRUNCATE TABLE mailboxes CASCADE"))
        c.execute(text("TRUNCATE TABLE domains CASCADE"))
        print("Successfully truncated previous data (except users and settings).")
    except Exception as e:
        print(f"Error truncating tables: {e}")
    c.commit()
