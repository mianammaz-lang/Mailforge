from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.orm import relationship
from database.database import Base
from datetime import datetime

class Domain(Base):
    __tablename__ = "domains"
    id = Column(Integer, primary_key=True, index=True)
    mailforge_id = Column(String, unique=True, index=True, nullable=True)
    name = Column(String, unique=True, index=True)
    status = Column(String)  # PASS, WARN, FAIL, UNKNOWN
    mailforge_status = Column(String)
    health_score = Column(Float, default=0.0)
    campaign_ready = Column(Boolean, default=False)
    registrar = Column(String, nullable=True)
    expiration = Column(DateTime, nullable=True)
    last_checked = Column(DateTime, default=datetime.utcnow)
    
    mailboxes = relationship("Mailbox", back_populates="domain")
    checks = relationship("DomainCheck", back_populates="domain")
    issues = relationship("Issue", back_populates="domain")

class Mailbox(Base):
    __tablename__ = "mailboxes"
    id = Column(Integer, primary_key=True, index=True)
    domain_id = Column(Integer, ForeignKey("domains.id"))
    mailforge_id = Column(String, unique=True, index=True, nullable=True)
    email = Column(String, unique=True, index=True)
    status = Column(String)
    mailforge_status = Column(String)
    health_score = Column(Float, default=0.0)
    campaign_ready = Column(Boolean, default=False)
    created_at = Column(DateTime, nullable=True)
    forwarding_status = Column(String, nullable=True)
    last_checked = Column(DateTime, default=datetime.utcnow)
    
    domain = relationship("Domain", back_populates="mailboxes")
    checks = relationship("MailboxCheck", back_populates="mailbox")
    issues = relationship("Issue", back_populates="mailbox")

class DomainCheck(Base):
    __tablename__ = "domain_checks"
    id = Column(Integer, primary_key=True, index=True)
    domain_id = Column(Integer, ForeignKey("domains.id"))
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    a_record = Column(String)
    aaaa_record = Column(String)
    mx_record = Column(String)
    txt_record = Column(String)
    ns_record = Column(String)
    cname_record = Column(String)
    
    spf_status = Column(String)
    dkim_status = Column(String)
    dmarc_status = Column(String)
    
    dnssec_status = Column(String)
    mta_sts_status = Column(String)
    tls_rpt_status = Column(String)
    bimi_status = Column(String)
    
    blacklist_status = Column(String)
    smtp_status = Column(String)
    mx_health = Column(String)
    
    domain = relationship("Domain", back_populates="checks")

class MailboxCheck(Base):
    __tablename__ = "mailbox_checks"
    id = Column(Integer, primary_key=True, index=True)
    mailbox_id = Column(Integer, ForeignKey("mailboxes.id"))
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    smtp_connectivity = Column(String)
    mailbox_verification = Column(String)
    
    mailbox = relationship("Mailbox", back_populates="checks")

class HealthSnapshot(Base):
    __tablename__ = "health_snapshots"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    overall_score = Column(Float)
    healthy_domains = Column(Integer)
    total_domains = Column(Integer)
    healthy_mailboxes = Column(Integer)
    total_mailboxes = Column(Integer)
    campaign_ready_mailboxes = Column(Integer)

class ApiRun(Base):
    __tablename__ = "api_runs"
    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
    status = Column(String)
    error_message = Column(Text, nullable=True)
    response_time_ms = Column(Float, nullable=True)

class Issue(Base):
    __tablename__ = "issues"
    id = Column(Integer, primary_key=True, index=True)
    domain_id = Column(Integer, ForeignKey("domains.id"), nullable=True)
    mailbox_id = Column(Integer, ForeignKey("mailboxes.id"), nullable=True)
    severity = Column(String) # CRITICAL, HIGH, MEDIUM, LOW
    issue_type = Column(String)
    description = Column(Text)
    recommendation = Column(Text)
    status = Column(String) # OPEN, RESOLVED
    detected_at = Column(DateTime, default=datetime.utcnow)
    last_seen_at = Column(DateTime, default=datetime.utcnow)
    
    domain = relationship("Domain", back_populates="issues")
    mailbox = relationship("Mailbox", back_populates="issues")

class SystemSetting(Base):
    __tablename__ = "settings"
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True)
    value = Column(String, nullable=True)

