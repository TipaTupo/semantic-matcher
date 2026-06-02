from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api import router
from config import config
from instance import instance
from tasks import recover_interrupted_tasks
from utils import (
    get_embedding_model,
    ensure_data_dirs,
    load_active_version,
    load_tasks_db,
    cleanup_orphan_task_data,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    instance.logger.info("Starting up")
    ensure_data_dirs()
    load_active_version()
    load_tasks_db()
    
    # Clean up orphan task data files (no corresponding task in DB)
    cleanup_orphan_task_data()
    
    # Recover interrupted tasks from previous session
    await recover_interrupted_tasks()
    
    # Preload model
    instance.logger.info("Preloading embedding model...")
    get_embedding_model()
    
    yield
    
    # Shutdown
    instance.logger.info("Shutting down")


app = FastAPI(
    title="Semantic Article Matcher",
    description="Microservice for semantic search of articles based on user queries",
    version="0.1",
    lifespan=lifespan
)

@app.get("/", tags=["UI"])
def root():
    """Serve the frontend application."""
    index_path = instance.front_path / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    raise HTTPException(status_code=404, detail="Frontend not found")

app.mount("/front", StaticFiles(directory=str(instance.front_path)))
app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=config.port)
