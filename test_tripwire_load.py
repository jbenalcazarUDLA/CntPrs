from backend.database import SessionLocal
from backend import crud, models

db = SessionLocal()
sources = db.query(models.VideoSource).all()
for s in sources:
    t = crud.get_tripwire(db, s.id)
    print(f"Source ID: {s.id}, Type: {s.type}, Tripwire: {t.x1 if t else None}")
