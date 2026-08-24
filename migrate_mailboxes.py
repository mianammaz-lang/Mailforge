from sqlalchemy import text
from database.database import engine

with engine.connect() as c:
    queries = [
        "ALTER TABLE mailboxes ADD COLUMN password VARCHAR",
        "ALTER TABLE mailboxes ADD COLUMN imap_host VARCHAR",
        "ALTER TABLE mailboxes ADD COLUMN imap_port INTEGER",
        "ALTER TABLE mailboxes ADD COLUMN smtp_host VARCHAR",
        "ALTER TABLE mailboxes ADD COLUMN smtp_port INTEGER",
        "ALTER TABLE mailboxes ADD COLUMN warmup_enabled BOOLEAN DEFAULT FALSE",
        "ALTER TABLE mailbox_checks ADD COLUMN imap_connectivity VARCHAR",
        "ALTER TABLE mailbox_checks ADD COLUMN auth_status VARCHAR"
    ]
    for q in queries:
        try:
            c.execute(text(q))
            print(f"Executed: {q}")
        except Exception as e:
            print(f"Failed: {q} - {e}")
    c.commit()
