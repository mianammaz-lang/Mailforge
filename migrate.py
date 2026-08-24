from sqlalchemy import text
from database.database import engine

with engine.connect() as c:
    try:
        c.execute(text('ALTER TABLE domains ADD COLUMN receives_inbound_mail BOOLEAN DEFAULT TRUE'))
        print("Added receives_inbound_mail")
    except Exception as e:
        print(e)
    try:
        c.execute(text('ALTER TABLE issues ADD COLUMN resolved_at TIMESTAMP'))
        print("Added resolved_at")
    except Exception as e:
        print(e)
    c.commit()
