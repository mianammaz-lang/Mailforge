import pandas as pd
from typing import List
from database.models import Domain, Mailbox

def generate_csv(domains: List[Domain], mailboxes: List[Mailbox], filepath: str):
    data = []
    for d in domains:
        data.append({
            "Type": "Domain",
            "Name": d.name,
            "Health Score": d.health_score,
            "Status": d.status,
            "Campaign Ready": d.campaign_ready
        })
    for m in mailboxes:
        data.append({
            "Type": "Mailbox",
            "Name": m.email,
            "Health Score": m.health_score,
            "Status": m.status,
            "Campaign Ready": m.campaign_ready
        })
    df = pd.DataFrame(data)
    df.to_csv(filepath, index=False)
