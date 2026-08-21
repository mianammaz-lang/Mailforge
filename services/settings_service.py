from sqlalchemy.orm import Session
from database.models import SystemSetting
from config.settings import settings

def get_setting(db: Session, key: str, default=None):
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if setting and setting.value is not None:
        return setting.value
    # Fallback to env config
    env_val = getattr(settings, key.upper(), None)
    if env_val is not None:
        return env_val
    return default

def set_setting(db: Session, key: str, value: str):
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not setting:
        setting = SystemSetting(key=key, value=value)
        db.add(setting)
    else:
        setting.value = value
    db.commit()
    return value
