from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from .database import engine, get_db
from . import models, schemas, crud
from .api import ingestion, stream, tripwire

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="People Counting System - Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ingestion API
app.include_router(ingestion.router, prefix="/api/sources", tags=["ingestion"])
app.include_router(stream.router, prefix="/api/stream", tags=["streaming"])
app.include_router(tripwire.router, prefix="/api/tripwires", tags=["tripwire"])

# Static Files
app.mount("/static", StaticFiles(directory="backend/static"), name="static")

@app.get("/")
def read_root():
    return FileResponse("backend/static/index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
