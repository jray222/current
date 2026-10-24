from sqlalchemy import Column, Integer, String, Text
from app.database import Base


class RuntimeConfig(Base):
    __tablename__ = "runtime_config"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)

    # Example keys:
    # - "anthropic_api_key" : the owner's Anthropic key (encrypted)
    # - "anthropic_model" : "claude-haiku-5-5"
    # - "registration_mode" : "invite" or "open"; "public_url" : the address invite links use
