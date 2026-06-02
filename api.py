import json
import time
import uuid
import shutil
import hashlib
import asyncio
import aiofiles
import faiss
import numpy as np
import pandas as pd

from io import BytesIO
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Optional, Annotated
from pandas.errors import ParserError, EmptyDataError, DtypeWarning
from fastapi import APIRouter, HTTPException, Query, File, UploadFile

from schemas import *
from config import config
from instance import instance
from tasks import (
    create_index_task,
    process_index_task,
    task_processor,
)
from utils import (
    get_embedding_model,
    search_faiss_index,
    get_version_path,
    save_active_version,
    rename_version,
    get_pin_versions,
    save_pin_versions,
    generate_synonyms,
    get_version_metadata,
    build_article_data,
    delete_from_index,
    convert_synonym_to_sample,
    update_stop_words,
    save_tasks_db,
    delete_task_data,
    get_all_tasks,
)


router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check():
    """Health check endpoint (highest priority - always immediate)."""
    # This endpoint has highest priority (1) and is never blocked by reindex
    return HealthResponse(status="ok")


@router.post("/search", response_model=SearchResponse, tags=["search"])
async def search(
    request: SearchRequest,
    limit: Annotated[int, Query(ge=1, le=20)] = config.default_limit,
    threshold: Annotated[float, Query(ge=0.0, le=1.0)] = config.similarity_threshold
):
    """Search for top-N relevant articles based on query (highest priority - always immediate)."""
    # This endpoint has highest priority (1) and is never blocked by reindex
    if instance.active_index is None or instance.active_metadata is None:
        raise HTTPException(status_code=428, detail="No active index available. Please run reindex first.")
    
    start_time = time.time()
    
    # Preprocess query
    preprocessed_query = instance.preprocess_text(request.query)
    
    # Vectorize query
    try:
        model = get_embedding_model()
    except Exception as e:
        raise HTTPException(status_code=500, detail=e)
    query_vector = model.encode([preprocessed_query], show_progress_bar=False)[0]
    
    # Search in FAISS index for top-k results (get more than limit to filter by threshold)
    distances, indices = search_faiss_index(instance.active_index, query_vector, k=len(instance.active_metadata["data"]))
    
    # Group by article_id (keep max score per article)
    article_scores: Dict[str, float] = {}
    article_order = []
    
    for idx, score in zip(indices, distances):
        if score < threshold:
            continue
        
        entry = instance.active_metadata["data"][idx]
        article_id = entry["article_id"]
        
        if article_id not in article_scores:
            article_scores[article_id] = score
            article_order.append(article_id)
        elif score > article_scores[article_id]:
            article_scores[article_id] = score
    
    # Sort by score descending
    sorted_articles = sorted(article_order, key=lambda x: article_scores[x], reverse=True)[:limit]
    sorted_scores = [article_scores[a] for a in sorted_articles]
    
    processing_time = (time.time() - start_time) * 1000
    
    # Log request
    instance.logger.info(f"[SEARCH] {datetime.now(timezone.utc).isoformat()} | {len(sorted_articles)} results | version={instance.active_version_id} | latency={processing_time:.1f}ms")
    
    return SearchResponse(
        articles=sorted_articles,
        scores=sorted_scores,
        version_used=instance.active_version_id or "none",
        processing_time_ms=round(processing_time, 2)
    )


@router.post("/reindex", status_code=202, tags=["indexing"])
async def reindex(
    request: IndexRequest,
    update_current: Annotated[bool, Query()] = False,
    activate: Annotated[bool, Query()] = False,
    pin: Annotated[bool, Query()] = False,
    llm: Annotated[bool, Query()] = False,
):
    """Start reindexing process with provided data (low priority, background)."""
    if instance.task_queue.qsize() >= config.max_qsize:
        raise HTTPException(status_code=429, detail="Task queue is full")
    
    task = await create_index_task(request.data, update_current, activate, pin, llm)
    
    return task


@router.post("/reindex/file", status_code=202, tags=["indexing"])
async def index_file(
    files: List[UploadFile] = File(...),
    update_current: Annotated[bool, Query()] = False,
    activate: Annotated[bool, Query()] = False,
    pin: Annotated[bool, Query()] = False,
    llm: Annotated[bool, Query()] = False,
):
    """Start reindexing process from uploaded file (JSON or XLSX) (low priority, background)."""
    if instance.task_queue.qsize() >= config.max_qsize:
        raise HTTPException(status_code=429, detail="Task queue is full")
    
    # Удаляем временные файлы из тома
    def delete_temp_files(_path: Path):
        if _path.exists() and _path.is_dir():
            shutil.rmtree(_path)

    # Временно сохраняем файлы в том
    saved_files_dir: Path = config.data_dir / "_temp"
    saved_files_dir.mkdir(parents=True, exist_ok=True)
    saved_files_path = []
    for file in files:
        file_name = file.filename
        saved_file_path = saved_files_dir / file_name
        async with aiofiles.open(saved_file_path, mode='wb') as f:
            while chunk := await file.read(1024 * 1024):
                await f.write(chunk)
        saved_files_path.append(saved_file_path)
    
    # Обрабатываем временные файлы из тома
    articles_data = []
    for file in saved_files_path:
        try:
            if file.name.endswith('.json') or file.name.endswith('.txt'):
                with open(file, 'r', encoding='utf-8') as f:
                    data_json = json.load(f)
                articles_data = [ArticleData(**item) for item in data_json]
            elif file.name.endswith('.xlsx'):
                for df in pd.read_excel(file, chunksize=100, engine='openpyxl'):
                    # Validate required columns
                    required_cols = {'id', 'samples'}
                    if not required_cols.issubset(df.columns):
                        raise HTTPException(
                            status_code=422,
                            detail=f"Missing required columns: {required_cols - set(df.columns)}"
                        )
                    
                    samples_for_article = {}
                    has_title_col = 'title' in df.columns
                    for _, row in df.iterrows():
                        article_id = row['id']
                        if not samples_for_article.get(article_id):
                            samples_for_article[article_id] = {
                                "title": str(row['title']) if has_title_col and pd.notna(row['title']) else None,
                                "samples": []
                            }

                        samples = row['samples']
                        if isinstance(samples, str):
                            try:
                                samples = json.loads(samples)
                                if isinstance(samples, list):
                                    samples_for_article[article_id]["samples"] += samples
                                elif samples:
                                    samples_for_article[article_id]["samples"] += [samples]
                            except:
                                if samples:
                                    samples_for_article[article_id]["samples"] += [samples]
                    
                    for artice_id in samples_for_article:
                        articles_data.append(ArticleData(
                            id=str(artice_id),
                            title=samples_for_article[artice_id]["title"],
                            samples=samples_for_article[artice_id]["samples"]
                        ))
            else:
                delete_temp_files(saved_files_dir)
                raise HTTPException(status_code=400, detail="Unsupported file format. Use .json or .xlsx")
            
        except json.JSONDecodeError as e:
            delete_temp_files(saved_files_dir)
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")
        except (ParserError, EmptyDataError, DtypeWarning) as e:
            delete_temp_files(saved_files_dir)
            raise HTTPException(status_code=400, detail=f"Invalid Excel: {str(e)}")
        except Exception as e:
            delete_temp_files(saved_files_dir)
            if isinstance(e, HTTPException):
                raise
            raise HTTPException(status_code=422, detail=f"Failed to parse file: {str(e)}")
    
    delete_temp_files(saved_files_dir)

    request_data = IndexRequest(data=articles_data)
    task = await create_index_task(request_data.data, update_current, activate, pin, llm)

    return task


@router.get("/queue", response_model=QueueStatusResponse, tags=["task-queue"])
async def get_queue_status():
    """Get status of the task queue (medium priority - does not block health/search)."""
    # This endpoint has medium priority (2) and doesn't interfere with reindex
    response = get_all_tasks()
    return response


@router.delete("/queue", response_model=QueueDeleteResponse, tags=["task-queue"])
async def delete_task_queue():
    """Delete a task queue (medium priority - does not block health/search)."""
    # This endpoint has medium priority (2) and doesn't interfere with reindex
    if not instance.task_queue.empty() and not instance.tasks_db:
        raise HTTPException(status_code=404, detail="Queue is empty")
    
    task_ids = []
    while not instance.task_queue.empty():
        _, task_id, *_ = instance.task_queue.get_nowait()
        delete_task_data(task_id)
        del instance.tasks_db[task_id]
        task_ids.append(task_id)

    tasks_db_keys = list(instance.tasks_db.keys())
    for task_id in tasks_db_keys:
        if instance.tasks_db[task_id]["status"] == "pending":
            delete_task_data(task_id)
            del instance.tasks_db[task_id]
            task_ids.append(task_id)

    status = "deleted" if instance.task_queue.empty() else "failed"
    task_ids = list(set(task_ids))
    
    # Persist changes
    save_tasks_db()
    data = get_all_tasks()
    
    return QueueDeleteResponse(
        status=status,
        task_ids=task_ids,
        data=data,
    )


@router.get("/queue/restart", response_model=QueueRestartResponse, tags=["task-queue"])
async def get_task_status():
    """Restart task queue (medium priority - does not block health/search)."""
    # This endpoint has medium priority (2) and doesn't interfere with reindex
    pending_tasks = []
    for task in instance.tasks_db.values():
        if task["status"] == "pending" :
            pending_tasks.append(task)

    if not pending_tasks:
        raise HTTPException(status_code=404, detail="No tasks to restart")
    
    data = get_all_tasks()

    return QueueRestartResponse(
        task_ids=[item["task_id"] for item in pending_tasks],
        data=data,
    )


@router.get("/task/{task_id}", response_model=TaskStatusResponse, tags=["task-queue"])
async def get_task_status(task_id: str):
    """Get status of a specific task (medium priority - does not block health/search)."""
    # This endpoint has medium priority (2) and doesn't interfere with reindex
    # Check in active tasks first
    if task_id in instance.tasks_db:
        task_info = instance.tasks_db[task_id]
    # Check in done tasks
    elif task_id in instance.done_tasks_db:
        task_info = instance.done_tasks_db[task_id]
    else:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return TaskStatusResponse(
        task_id=task_id,
        parameters=task_info.get("parameters"),
        status=task_info.get("status"),
        progress=task_info.get("progress"),
        queued_at=task_info.get("queued_at"),
        started_at=task_info.get("started_at"),
        completed_at=task_info.get("completed_at"),
        error=task_info.get("error"),
    )


@router.delete("/task/{task_id}", response_model=TaskDeleteResponse, tags=["task-queue"])
async def delete_task_queue(task_id: str):
    """Delete a task (medium priority - does not block health/search).
    
    - processing tasks -> cancelled (not deleted, to avoid race conditions with background processor)
    - pending tasks -> deleted and removed from queue
    - done/failed tasks -> deleted from history
    """
    status = "deleted"
    # Check in active tasks first
    if task_id in instance.tasks_db:
        if instance.tasks_db[task_id]["status"] == "processing":
            # Cannot delete a running task - cancel it instead
            instance.tasks_db[task_id]["status"] = "failed"
            instance.tasks_db[task_id]["error"] = "Task was cancelled by user"
            instance.tasks_db[task_id]["completed_at"] = datetime.now(timezone.utc).isoformat()
            save_tasks_db()
            status = "cancelled"
        else:
            # pending/failed/cancelled tasks can be fully deleted
            delete_task_data(task_id)
            del instance.tasks_db[task_id]
            # Remove from task queue (PriorityQueue) if still pending
            new_queue = asyncio.PriorityQueue()
            while not instance.task_queue.empty():
                item = instance.task_queue.get_nowait()
                if item[1] != task_id:
                    new_queue.put_nowait(item)
            instance.task_queue = new_queue
    # Check in done tasks
    elif task_id in instance.done_tasks_db:
        del instance.done_tasks_db[task_id]
    else:
        raise HTTPException(status_code=404, detail="Task does not exist")

    # Persist changes to disk
    save_tasks_db()
    data = get_all_tasks()

    return TaskDeleteResponse(
        status=status,
        task_id=task_id,
        data=data,
    )


@router.get("/versions", response_model=VersionsResponse, tags=["data-management"])
async def get_versions():
    """Get list of all versions (medium priority - does not block health/search)."""
    # This endpoint has medium priority (2) and doesn't interfere with reindex
    versions_dir = config.data_dir / "versions"
    if not versions_dir.exists():
        return VersionsResponse(versions=[], total_versions=0, pin_versions=0)
    
    pin_versions_set = set(get_pin_versions())
    versions_list = []
    
    for v_dir in versions_dir.iterdir():
        if v_dir.is_dir() and v_dir.name != "tmp":
            version_id = v_dir.name
            metadata_file = v_dir / "metadata.json"
            
            version_name = ""
            created_at = ""
            vectors_count = 0
            articles_count = 0
            
            if metadata_file.exists():
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                version_name = metadata.get("version_name", "")
                created_at = metadata.get("created_at", "")
                vectors_count = metadata.get("vectors_count", 0)
                
                # Count unique articles
                article_ids = set()
                for entry in metadata.get("data", []):
                    article_ids.add(entry.get("article_id"))
                articles_count = len(article_ids)
            
            versions_list.append(VersionInfo(
                version_id=version_id,
                version_name=version_name,
                created_at=created_at,
                is_active=(version_id == instance.active_version_id),
                is_pin=(version_id in pin_versions_set),
                vectors_count=vectors_count,
                articles_count=articles_count
            ))
    
    # Sort by created_at descending
    versions_list.sort(key=lambda v: v.created_at, reverse=True)
    
    return VersionsResponse(
        versions=versions_list,
        total_versions=len(versions_list),
        pin_versions=len(pin_versions_set)
    )


@router.post("/versions/{version_id}", tags=["data-management"])
async def manage_version(
    version_id: str, 
    request: VersionActionRequest
):
    """Manage version (medium priority): activate, delete, pin, unpin."""
    # This endpoint has medium priority (2) and doesn't interfere with reindex pin
    version_path = get_version_path(version_id)
    
    if not version_path.exists():
        raise HTTPException(status_code=404, detail="Version not found")
    
    pin_versions = get_pin_versions()
    
    if request.action == "activate":
        # Load version
        metadata_file = version_path / "metadata.json"
        index_file = version_path / "index.faiss"
        
        if not metadata_file.exists() or not index_file.exists():
            raise HTTPException(status_code=400, detail="Version files are corrupted")
        
        with open(metadata_file, 'r', encoding='utf-8') as f:
            new_metadata = json.load(f)
        
        new_index = faiss.read_index(str(index_file))
        
        instance.active_index = new_index
        instance.active_metadata = new_metadata
        instance.active_version_id = version_id
        
        save_active_version(version_id)
        
        return {"message": f"Version {version_id} activated successfully"}
    
    elif request.action == "rename":
        rename_version(version_id, request.name)
        return {"message": f"Version {version_id} renamed as {request.name}"}
    
    elif request.action == "pin":
        if version_id not in pin_versions:
            pin_versions.append(version_id)
            save_pin_versions(pin_versions)
        return {"message": f"Version {version_id} marked as pin"}
    
    elif request.action == "unpin":
        if version_id in pin_versions:
            pin_versions.remove(version_id)
            save_pin_versions(pin_versions)
        return {"message": f"Version {version_id} unmarked as pin"}
    
    elif request.action == "delete":
        if version_id in pin_versions:
            raise HTTPException(status_code=400, detail="Cannot delete pinned version")
        
        if version_id == instance.active_version_id:
            raise HTTPException(status_code=400, detail="Cannot delete active version")
        
        shutil.rmtree(version_path)
        
        return {"message": f"Version {version_id} deleted successfully"}
    
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {request.action}")


@router.get("/articles/{version_id}", response_model=ArticlesListResponse, tags=["data-management"])
async def get_articles(version_id: str):
    """Get list of articles in the specified version."""
    metadata = get_version_metadata(version_id)
    articles_data = build_article_data(metadata)
    
    articles_list = []
    for article_id, data in articles_data.items():
        articles_list.append(ArticleSummary(
            article_id=article_id,
            article_title=data["article_title"],
            samples_count=len(data["samples"]),
            synonyms_count=len(data["synonyms"])
        ))
    
    return ArticlesListResponse(
        version_id=version_id,
        articles_count=len(articles_list),
        articles=articles_list
    )


@router.get("/articles/{version_id}/{article_id}", response_model=ArticleDetailResponse, tags=["data-management"])
async def get_article_details(
    version_id: str,
    article_id: str,
):
    """Get detailed information about an article including samples and synonyms."""
    metadata = get_version_metadata(version_id)
    articles_data = build_article_data(metadata)
    
    if not article_id or article_id not in articles_data:
        raise HTTPException(status_code=404, detail="Article not found")
    
    article_data = articles_data[article_id]
    
    return ArticleDetailResponse(
        version_id=version_id,
        article_id=article_id,
        article_title=article_data["article_title"],
        samples_count=len(article_data["samples"]),
        samples=article_data["samples"],
        synonyms_count=len(article_data["synonyms"]),
        synonyms=article_data["synonyms"]
    )


@router.post("/articles/{version_id}/{article_id}/convert", status_code=202, response_model=SynonymToSampleResponse, tags=["data-management"])
async def convert_synonym_to_sample_endpoint(
    version_id: str,
    article_id: str,
    request: SynonymToSampleRequest,
):
    """Convert one or more synonyms to samples in an article."""
    # Use active version if not specified
    if version_id is None:
        if instance.active_version_id is None:
            raise HTTPException(status_code=400, detail="No active version and no version_id specified")
        version_id = instance.active_version_id

    metadata = get_version_metadata(version_id)
    articles_data = build_article_data(metadata)
    if article_id not in articles_data:
        raise HTTPException(status_code=404, detail="Article not found")

    article_data = articles_data[article_id]
    article_title = article_data["article_title"]
    synonyms_dict = article_data["synonyms"]

    # Validate synonym IDs
    valid_synonym_ids = []
    for synonym_id in request.ids:
        if not synonym_id.startswith("syn_"):
            continue

        if synonym_id not in synonyms_dict:
            continue

        valid_synonym_ids.append(synonym_id)

    if not valid_synonym_ids:
        raise HTTPException(status_code=404, detail="Synonyms not found")

    # Queue convert_synonym task with medium priority (2)
    task_id = f"s-syn_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"
    instance.tasks_db[task_id] = {
        "task_id": task_id,
        "parameters": {
            "version_id": version_id,
            "article_id": article_id,
            "synonyms_len": len(valid_synonym_ids),
        },
        "status": "pending",
        "queued_at": datetime.now(timezone.utc).isoformat(),
        "priority": 2,
    }
    save_tasks_db()

    await instance.task_queue.put((2, task_id, "convert_synonym", version_id, article_id, valid_synonym_ids))

    # Start background processor if not already running
    asyncio.create_task(task_processor())

    return SynonymToSampleResponse(
        status="processing",
        task_id=task_id,
        version_id=version_id,
        article_id=article_id,
        article_title=article_title,
        count=len(valid_synonym_ids),
    )


@router.delete("/articles/{version_id}/{article_id}", status_code=202, response_model=ArticleDeleteResponse, tags=["data-management"])
async def delete_article(
    version_id: str,
    article_id: str,
):
    """Delete an entire article, including all samples and synonyms."""
    # Use active version if not specified
    if version_id is None:
        if instance.active_version_id is None:
            raise HTTPException(status_code=400, detail="No active version and no version_id specified")
        version_id = instance.active_version_id

    metadata = get_version_metadata(version_id)
    articles_data = build_article_data(metadata)
    if article_id not in articles_data:
        raise HTTPException(status_code=404, detail="Article not found")

    article_data = articles_data[article_id]
    article_title = article_data["article_title"]
    samples_dict = article_data["samples"]
    synonyms_dict = article_data["synonyms"]

    # Count total entries to delete
    sample_count = len([eid for eid in samples_dict if eid.startswith("smp_")])
    synonym_count = len([sid for sid in synonyms_dict if sid.startswith("syn_")])
    total_count = sample_count + synonym_count

    if total_count == 0:
        raise HTTPException(status_code=404, detail="No data found for this article")

    # Queue delete_article task with medium priority (2)
    task_id = f"d-art_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"
    instance.tasks_db[task_id] = {
        "task_id": task_id,
        "parameters": {
            "version_id": version_id,
            "article_id": article_id,
            "total_entries": total_count,
        },
        "status": "pending",
        "queued_at": datetime.now(timezone.utc).isoformat(),
        "priority": 2,
    }
    save_tasks_db()

    await instance.task_queue.put((2, task_id, "delete_article", version_id, article_id))

    # Start background processor if not already running
    asyncio.create_task(task_processor())

    return ArticleDeleteResponse(
        status="processing",
        task_id=task_id,
        version_id=version_id,
        article_id=article_id,
        article_title=article_title,
        deleted_count=total_count,
    )


@router.delete("/articles/{version_id}/{article_id}/ids", status_code=202, response_model=SampleDeleteResponse, tags=["data-management"])
async def delete_sample_or_synonym(
    version_id: str,
    article_id: str,
    request: SampleDeleteRequest,
):
    """Delete an sample or synonym from an article."""
    # Use active version if not specified
    if version_id is None:
        if instance.active_version_id is None:
            raise HTTPException(status_code=400, detail="No active version and no version_id specified")
        version_id = instance.active_version_id

    metadata = get_version_metadata(version_id)
    articles_data = build_article_data(metadata)
    if article_id not in articles_data:
        raise HTTPException(status_code=404, detail="Article not found")

    article_data = articles_data[article_id]    
    article_title = article_data["article_title"]
    samples_dict = article_data["samples"]
    synonyms_dict = article_data["synonyms"]
    
    # Determine if it's an sample or synonym based on ID prefix
    valid_sample_ids = []
    for sample_or_synonym_id in request.ids:
        if not sample_or_synonym_id.startswith("smp_") and not sample_or_synonym_id.startswith("syn_"):
            # raise HTTPException(status_code=400, detail="Invalid sample or synonym ids format")
            continue
        
        if (sample_or_synonym_id not in samples_dict) and (sample_or_synonym_id not in synonyms_dict):
            # raise HTTPException(status_code=404, detail="Sample or synonym not found")
            continue
        
        valid_sample_ids.append(sample_or_synonym_id)
    
    if not valid_sample_ids:
        raise HTTPException(status_code=404, detail="Samples or synonyms not found")
        
    # Queue delete task with medium priority (2) - does not block health/search
    task_id = f"d-eos_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"
    instance.tasks_db[task_id] = {
        "task_id": task_id,
        "parameters": {
            "version_id": version_id,
            "article_id": article_id,
            "samples_or_synonyms_len": len(valid_sample_ids),
        },
        "status": "pending",
        "queued_at": datetime.now(timezone.utc).isoformat(),
        "priority": 2,
    }
    save_tasks_db()
    
    await instance.task_queue.put((2, task_id, "delete", version_id, article_id, valid_sample_ids))
    
    # Start background processor if not already running
    asyncio.create_task(task_processor())
    
    return SampleDeleteResponse(
        status="processing",
        task_id=task_id,
        version_id=version_id,
        article_id=article_id,
        article_title=article_title,
        samples_number=len(valid_sample_ids),
    )


@router.delete("/articles/{version_id}/{article_id}/synonyms", status_code=202, response_model=SampleDeleteResponse, tags=["data-management"])
async def delete_all_synonyms(
    version_id: str,
    article_id: str,
):
    """Delete all synonyms for a given article."""
    # Use active version if not specified
    if version_id is None:
        if instance.active_version_id is None:
            raise HTTPException(status_code=400, detail="No active version and no version_id specified")
        version_id = instance.active_version_id

    metadata = get_version_metadata(version_id)
    articles_data = build_article_data(metadata)
    if article_id not in articles_data:
        raise HTTPException(status_code=404, detail="Article not found")

    article_data = articles_data[article_id]
    article_title = article_data["article_title"]
    synonyms_dict = article_data["synonyms"]

    # Collect all synonym IDs
    synonym_ids = [sid for sid in synonyms_dict if sid.startswith("syn_")]

    if not synonym_ids:
        raise HTTPException(status_code=404, detail="No synonyms found for this article")

    # Queue delete task with medium priority (2)
    task_id = f"d-syn_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"
    instance.tasks_db[task_id] = {
        "task_id": task_id,
        "parameters": {
            "version_id": version_id,
            "article_id": article_id,
            "samples_or_synonyms_len": len(synonym_ids),
        },
        "status": "pending",
        "queued_at": datetime.now(timezone.utc).isoformat(),
        "priority": 2,
    }
    save_tasks_db()

    await instance.task_queue.put((2, task_id, "delete", version_id, article_id, synonym_ids))

    # Start background processor if not already running
    asyncio.create_task(task_processor())

    return SampleDeleteResponse(
        status="processing",
        task_id=task_id,
        version_id=version_id,
        article_id=article_id,
        article_title=article_title,
        samples_number=len(synonym_ids),
    )


@router.delete("/articles/{version_id}/{article_id}/all", status_code=202, response_model=SampleDeleteResponse, tags=["data-management"])
async def delete_all_samples_and_synonyms(
    version_id: str,
    article_id: str,
):
    """Delete all samples (and their dependent synonyms) for a given article.
    
    Since deleting an sample cascades to its synonyms in delete_from_index,
    we only need to collect all sample IDs — synonyms will be removed automatically.
    """
    # Use active version if not specified
    if version_id is None:
        if instance.active_version_id is None:
            raise HTTPException(status_code=400, detail="No active version and no version_id specified")
        version_id = instance.active_version_id

    metadata = get_version_metadata(version_id)
    articles_data = build_article_data(metadata)
    if article_id not in articles_data:
        raise HTTPException(status_code=404, detail="Article not found")

    article_data = articles_data[article_id]
    article_title = article_data["article_title"]
    samples_dict = article_data["samples"]

    # Collect all sample IDs
    sample_ids = [eid for eid in samples_dict if eid.startswith("smp_")]

    if not sample_ids:
        raise HTTPException(status_code=404, detail="No samples found for this article")

    # Queue delete task with medium priority (2)
    task_id = f"d-eas_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"
    instance.tasks_db[task_id] = {
        "task_id": task_id,
        "parameters": {
            "version_id": version_id,
            "article_id": article_id,
            "samples_or_synonyms_len": len(sample_ids),
        },
        "status": "pending",
        "queued_at": datetime.now(timezone.utc).isoformat(),
        "priority": 2,
    }
    save_tasks_db()

    await instance.task_queue.put((2, task_id, "delete", version_id, article_id, sample_ids))

    # Start background processor if not already running
    asyncio.create_task(task_processor())

    return SampleDeleteResponse(
        status="processing",
        task_id=task_id,
        version_id=version_id,
        article_id=article_id,
        article_title=article_title,
        samples_number=len(sample_ids),
    )


@router.get("/stopwords", response_model=GetStopWordsResponse, tags=["settings"])
async def get_stop_words():
    """Get a stop-words list"""
    stop_words = instance.stop_words
    
    return GetStopWordsResponse(
        count=len(stop_words),
        stop_words=stop_words
    )


@router.put("/stopwords", response_model=UpdateStopWordsResponse, tags=["settings"])
async def put_stop_words(
    data: UpdateStopWordsRequest,
):
    """Get a stop-words list"""
    try:
        count, added, deleted = update_stop_words(data.stop_words)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to save stop-words: {e}")
    
    return UpdateStopWordsResponse(
        status="saved",
        total_count=count,
        added=added,
        deleted=deleted
    )


@router.get("/llm/config", response_model=LLMConfigResponse, tags=["settings"])
async def get_llm_config():
    """Get current LLM configuration."""
    return config.get_llm_config()


@router.put("/llm/config", response_model=LLMConfigResponse, tags=["settings"])
async def update_llm_config(request: LLMConfigRequest):
    """Update LLM configuration."""
    config.change_llm_params(**request.model_dump(exclude_none=True))
    return config.get_llm_config()


@router.post("/llm/{version_id}/{article_id}", status_code=202, response_model=SamplesSynonymizeResponse, tags=["settings"])
async def generate_sample_synonyms(
    version_id: str,
    article_id: str,
    request: SamplesSynonymizeRequest,
):
    """Generate synonyms for an sample."""
    # Use active version if not specified
    if version_id is None:
        if instance.active_version_id is None:
            raise HTTPException(status_code=400, detail="No active version and no version_id specified")
        version_id = instance.active_version_id
    
    metadata = get_version_metadata(version_id)
    articles_data = build_article_data(metadata)
    
    if article_id not in articles_data:
        raise HTTPException(status_code=404, detail="Article not found")
    
    article_data = articles_data[article_id]
    target_dict = article_data["samples"]
    article_title = article_data["article_title"]

    valid_sample_ids = []
    valid_sample_texts = []
    for sample_id in request.ids:
        # Determine if it's an sample or synonym based on ID prefix
        if not sample_id.startswith("smp_"):
            # raise HTTPException(status_code=400, detail="Invalid sample_id format")
            continue
                
        if sample_id not in target_dict:
            # raise HTTPException(status_code=404, detail="Sample not found")
            continue
        
        valid_sample_ids.append(sample_id)
        sample_text = target_dict[sample_id]
        valid_sample_texts.append(sample_text)
    
    if not valid_sample_ids or not valid_sample_texts:
        raise HTTPException(status_code=404, detail="Samples not found")
        
    # Queue save_synonyms task with medium priority (2) - does not block health/search
    # Synonym generation (LLM) will happen inside the task, not in this endpoint
    task_id = f"c-syn_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"
    instance.tasks_db[task_id] = {
        "task_id": task_id,
        "parameters": {
            "version_id": version_id,
            "article_id": article_id,
            "samples_len": len(valid_sample_ids),
        },
        "status": "pending",
        "queued_at": datetime.now(timezone.utc).isoformat(),
        "priority": 2,
    }
    save_tasks_db()
    
    await instance.task_queue.put((2, task_id, "save_synonyms", version_id, article_id, article_title, valid_sample_texts))
    
    # Start background processor if not already running
    asyncio.create_task(task_processor())
    
    return SamplesSynonymizeResponse(
        status="processing",
        task_id=task_id,
        version_id=version_id,
        article_id=article_id,
        article_title=article_title,
        samples_number=len(valid_sample_ids),
    )
