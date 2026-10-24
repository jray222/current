"""Creating a household. Knowledge decks are shared by everyone on the server;
a household only groups the people who were invited together."""
from sqlalchemy.orm import Session

from app.models import Household


def create_household(db: Session, name: str) -> Household:
    household = Household(name=name.strip()[:100] or "My Household")
    db.add(household)
    db.flush()
    return household
