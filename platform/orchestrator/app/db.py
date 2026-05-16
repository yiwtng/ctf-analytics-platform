from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config import ANALYTICS_DATABASE_URL

engine = create_engine(ANALYTICS_DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

def get_db():
    return engine.connect()