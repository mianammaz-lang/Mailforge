import csv
from database.database import engine, SessionLocal
from database.models import Mailbox, Domain

csv_data = """Email,First Name,Last Name,IMAP Username,IMAP Password,IMAP Host,IMAP Port,SMTP Username,SMTP Password,SMTP Host,SMTP Port,Daily Limit,Warmup Enabled,Warmup Limit,Warmup Increment
bilal@alsharqimail01.com,bilal,khan,bilal@alsharqimail01.com,!498Jp99Rj74Vq84Vt,core.thecentralunity.com,993,bilal@alsharqimail01.com,!498Jp99Rj74Vq84Vt,core.thecentralunity.com,587,30,true,20,2
vineeka@qafilamail.com,vineeka,kumar,vineeka@qafilamail.com,!012Qm77Ly02Gu85Ou,aaven.coreviewspace.com,993,vineeka@qafilamail.com,!012Qm77Ly02Gu85Ou,aaven.coreviewspace.com,587,30,true,20,2
ammaz@salesqafila.com,Amma,z,ammaz@salesqafila.com,!125Hn43Hx63Fp70Oo,mail.theplanetelebor.com,993,ammaz@salesqafila.com,!125Hn43Hx63Fp70Oo,mail.theplanetelebor.com,587,30,true,20,2
maheen@salesqafila.com,Maheen,khan,maheen@salesqafila.com,!930Vr70Pi14Nh12Hg,mail.theplanetelebor.com,993,maheen@salesqafila.com,!930Vr70Pi14Nh12Hg,mail.theplanetelebor.com,587,30,true,20,2
ammaz.waleed1@alsharqimail02.com,Ammaz,Waleed,ammaz.waleed1@alsharqimail02.com,Alsharqi@20202,core.thecentralunity.com,993,ammaz.waleed1@alsharqimail02.com,Alsharqi@20202,core.thecentralunity.com,587,30,true,20,2
ammaz.waleed3@alsharqimail05.com,Ammaz,Waleed,ammaz.waleed3@alsharqimail05.com,Alsharqi@20202,core.thecentralunity.com,993,ammaz.waleed3@alsharqimail05.com,Alsharqi@20202,core.thecentralunity.com,587,30,true,20,2
maheen.akhtar4@alsharqimail02.com,Maheen,Akhtar,maheen.akhtar4@alsharqimail02.com,!215Pc16Xs59Vf04Pk,core.thecentralunity.com,993,maheen.akhtar4@alsharqimail02.com,!215Pc16Xs59Vf04Pk,core.thecentralunity.com,587,30,true,20,2
ammaz.waleed2@alsharqimail01.com,Ammaz,Waleed,ammaz.waleed2@alsharqimail01.com,Alsharqi@20202,core.thecentralunity.com,993,ammaz.waleed2@alsharqimail01.com,Alsharqi@20202,core.thecentralunity.com,587,30,true,20,2
maheen.akhtar4@alsharqimail04.com,Maheen,Akhtar,maheen.akhtar4@alsharqimail04.com,Alsharqi@20202,core.thecentralunity.com,993,maheen.akhtar4@alsharqimail04.com,Alsharqi@20202,core.thecentralunity.com,587,30,true,20,2
atif@alsharqimail01.com,atif,khan,atif@alsharqimail01.com,Alsharqi@20202,core.thecentralunity.com,993,atif@alsharqimail01.com,Alsharqi@20202,core.thecentralunity.com,587,30,true,20,2
rabia.sales@qafilamail.com,Rabia,Anwar,rabia.sales@qafilamail.com,Alsharqi@20202,aaven.coreviewspace.com,993,rabia.sales@qafilamail.com,Alsharqi@20202,aaven.coreviewspace.com,587,30,true,20,2
quotation.updates@alsharqimail05.com,Simran,Quotations,quotation.updates@alsharqimail05.com,Alsharqi@20202,core.thecentralunity.com,993,quotation.updates@alsharqimail05.com,Alsharqi@20202,core.thecentralunity.com,587,30,true,20,2
maheen@alsharqimail04.com,Maheen,Akhtar,maheen@alsharqimail04.com,Alsharqi@20202,core.thecentralunity.com,993,maheen@alsharqimail04.com,Alsharqi@20202,core.thecentralunity.com,587,30,true,20,2
maheen@alsharqimail03.com,Maheen,Akhtar,maheen@alsharqimail03.com,Alsharqi@20202,core.thecentralunity.com,993,maheen@alsharqimail03.com,Alsharqi@20202,core.thecentralunity.com,587,30,true,20,2
rabia@alsharqimail02.com,rabia,Anwar,rabia@alsharqimail02.com,Alsharqi@20202,core.thecentralunity.com,993,rabia@alsharqimail02.com,Alsharqi@20202,core.thecentralunity.com,587,30,true,20,2
vineeka@alsharqimail02.com,vineeka,Kumar,vineeka@alsharqimail02.com,Alsharqi@20202,core.thecentralunity.com,993,vineeka@alsharqimail02.com,Alsharqi@20202,core.thecentralunity.com,587,30,true,20,2
rabia@alsharqimail05.com,Rabia,Anwar,rabia@alsharqimail05.com,Alsharqi@20202,core.thecentralunity.com,993,rabia@alsharqimail05.com,Alsharqi@20202,core.thecentralunity.com,587,30,true,20,2
vineeka@alsharqimail05.com,Vineeka,kumar,vineeka@alsharqimail05.com,Alsharqi@20202,core.thecentralunity.com,993,vineeka@alsharqimail05.com,Alsharqi@20202,core.thecentralunity.com,587,30,true,20,2
sales@alsharqimail04.com,Sales,team,sales@alsharqimail04.com,Alsharqi@20202,core.thecentralunity.com,993,sales@alsharqimail04.com,Alsharqi@20202,core.thecentralunity.com,587,30,true,20,2"""

db = SessionLocal()
import io
reader = csv.DictReader(io.StringIO(csv_data))
for row in reader:
    email = row["Email"]
    domain_name = email.split("@")[1]
    
    domain = db.query(Domain).filter(Domain.name == domain_name).first()
    if not domain:
        domain = Domain(name=domain_name, status="UNKNOWN", mailforge_status="UNKNOWN", receives_inbound_mail=False)
        db.add(domain)
        db.commit()
        db.refresh(domain)
    
    mailbox = db.query(Mailbox).filter(Mailbox.email == email).first()
    if not mailbox:
        mailbox = Mailbox(email=email, domain_id=domain.id, status="UNKNOWN", mailforge_status="UNKNOWN")
        db.add(mailbox)
        
    mailbox.password = row["IMAP Password"]
    mailbox.imap_host = row["IMAP Host"]
    mailbox.imap_port = int(row["IMAP Port"])
    mailbox.smtp_host = row["SMTP Host"]
    mailbox.smtp_port = int(row["SMTP Port"])
    mailbox.warmup_enabled = row["Warmup Enabled"].lower() == "true"
    
db.commit()
print("Imported CSV into Mailboxes!")
