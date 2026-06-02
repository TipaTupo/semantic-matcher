import json
import uuid
import faiss
import shutil
import asyncio
import hashlib
import traceback
import numpy as np

from pathlib import Path
from fastapi import HTTPException
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from config import config
from instance import instance
from schemas import ArticleData
from utils import (
    get_embedding_model,
    get_version_path,
    get_tmp_path,
    save_active_version,
    get_pin_versions,
    save_pin_versions,
    save_tasks_db,
    check_lock,
    acquire_lock,
    release_lock,
    delete_from_index,
    convert_synonym_to_sample,
    generate_synonyms,
    save_synonyms_to_index,
    create_faiss_index,
    save_task_data,
    load_task_data,
    delete_task_data,
    get_version_metadata,
    build_article_data,
)

class TaskCancelled(Exception):
    pass


async def recover_interrupted_tasks():
    """Recover tasks interrupted by a crash or restart.
    
    - processing tasks -> marked as failed (cannot resume from progress)
    - pending tasks with index_data -> re-queued for processing
    - failed tasks with stale index_data -> cleaned up
    - stale lock file -> removed
    
    Note: done tasks are in instance.done_tasks_db and are not recovered.
    """
    recovered_failed = 0
    recovered_queued = 0
    cleaned_stale = 0
    
    for task_id, task_info in instance.tasks_db.items():
        status = task_info.get("status")
        
        # Mark interrupted processing tasks as failed
        if status == "processing":
            instance.logger.info(f"Marking interrupted task as failed: {task_id}")
            task_info["status"] = "failed"
            task_info["error"] = "Task was interrupted by process restart"
            task_info["completed_at"] = datetime.now(timezone.utc).isoformat()
            # Keep index_data so user can manually restart if needed
            recovered_failed += 1
        
        # Re-queue pending tasks that have saved data
        elif status == "pending" and ("index_data_path" in task_info or "index_data" in task_info):
            instance.logger.info(f"Re-queuing pending task: {task_id}")
            try:
                # Try loading from file first, fall back to inline data (legacy)
                if "index_data_path" in task_info:
                    data = load_task_data(task_id)
                else:
                    # Legacy: data was stored inline in tasks.json
                    data = [ArticleData(**d) for d in task_info["index_data"]]
                    # Migrate: save to file and update reference
                    save_task_data(task_id, data)
                    task_info["index_data_path"] = f"task_data/{task_id}.json"
                    task_info.pop("index_data", None)
                
                update_current = task_info.get("update_current", False)
                activate = task_info.get("activate", False)
                pin = task_info.get("pin", False)
                llm = task_info.get("llm", False)
                await instance.task_queue.put((3, task_id, "reindex", data, update_current, activate, pin, llm))
                recovered_queued += 1
            except FileNotFoundError:
                instance.logger.error(f"Task data file missing for {task_id}, marking as failed")
                task_info["status"] = "failed"
                task_info["error"] = "Task data file not found (possibly corrupted or manually deleted)"
                task_info["completed_at"] = datetime.now(timezone.utc).isoformat()
                task_info.pop("index_data_path", None)
                task_info.pop("index_data", None)
                recovered_failed += 1
            except Exception as e:
                instance.logger.error(f"Failed to re-queue task {task_id}: {e}")
                task_info["status"] = "failed"
                task_info["error"] = f"Failed to recover task: {e}"
                task_info["completed_at"] = datetime.now(timezone.utc).isoformat()
                recovered_failed += 1
        
        # Clean stale task data from failed tasks
        elif status == "failed" and ("index_data_path" in task_info or "index_data" in task_info):
            instance.logger.warning(f"Removing stale task data from failed task: {task_id}")
            delete_task_data(task_id)
            task_info.pop("index_data_path", None)
            task_info.pop("index_data", None)  # legacy cleanup
            cleaned_stale += 1
    
    # Clean stale task data from done tasks
    for task_id, task_info in list(instance.done_tasks_db.items()):
        if "index_data_path" in task_info or "index_data" in task_info:
            instance.logger.warning(f"Removing stale task data from done task: {task_id}")
            delete_task_data(task_id)
            task_info.pop("index_data_path", None)
            task_info.pop("index_data", None)  # legacy cleanup
            cleaned_stale += 1
    
    # Save changes
    if recovered_failed or recovered_queued or cleaned_stale:
        save_tasks_db()
    
    if recovered_failed:
        instance.logger.info(f"Marked {recovered_failed} interrupted task(s) as failed")
    if recovered_queued:
        instance.logger.info(f"Re-queued {recovered_queued} pending task(s)")
    if cleaned_stale:
        instance.logger.info(f"Cleaned stale data from {cleaned_stale} task(s)")
    
    # Clean up stale lock file
    if instance.lock_file_path.exists():
        instance.lock_file_path.unlink()
        instance.logger.info("Removed stale lock file")
    
    # Start task processor if there are tasks in the queue
    if recovered_queued > 0:
        asyncio.create_task(task_processor())
        instance.logger.info("Task processor started for recovered tasks")


def _clear_index_data(task_id: str):
    """Remove task data file and index_data_path from a task."""
    # Delete the actual data file from storage
    delete_task_data(task_id)
    
    # Remove index_data_path from task record
    # Check active tasks first
    if task_id in instance.tasks_db:
        instance.tasks_db[task_id].pop("index_data_path", None)
        instance.tasks_db[task_id].pop("index_data", None)  # legacy cleanup
        save_tasks_db()
        return
    # Check done tasks
    if task_id in instance.done_tasks_db:
        instance.done_tasks_db[task_id].pop("index_data_path", None)
        instance.done_tasks_db[task_id].pop("index_data", None)  # legacy cleanup
        save_tasks_db()


def _check_task_not_cancelled(task_id: str):
    """Check if a task has been cancelled by the user. Raises TaskCancelled if so."""
    task = instance.tasks_db.get(task_id)
    if task is None:
        raise TaskCancelled("Task was removed")
    if task.get("status") in ("falied", "cancelled"):
        raise TaskCancelled("Task was cancelled by user")


async def create_index_task(
    data: List[ArticleData], 
    update_current: bool,
    activate: bool,
    pin: bool, 
    llm: bool,
) -> Dict[str, Any]:
    """Create a reindex task in the database.
    
    Training data is saved to a separate file in task_data/ directory,
    and only a reference (index_data_path) is stored in tasks.json.
    """
    task_id = f"c-idx_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"
    
    # Save task record first (for orphan prevention)
    instance.tasks_db[task_id] = {
        "task_id": task_id,
        "parameters": {
            "update_current": update_current,
            "activate": activate,
            "pin": pin,
            "llm": llm
        },
        "status": "pending",
        "progress": {
            "total": sum(len(item.samples) for item in data)
        },
        "queued_at": datetime.now(timezone.utc).isoformat(),
        "priority": 3,  # Lowest priority
    }
    save_tasks_db()
    
    # Save training data to separate file storage
    save_task_data(task_id, data)
    
    # Update task with data reference
    instance.tasks_db[task_id]["index_data_path"] = f"task_data/{task_id}.json"
    save_tasks_db()
    
    instance.logger.info(f"Задача {task_id}")
    instance.logger.info(f"БД тасков сохранено")

    # Use priority 3 for reindex tasks (lowest priority)
    await instance.task_queue.put((3, task_id, "reindex", data, update_current, activate, pin, llm))
    instance.logger.info(f"Задача поставлена в очередь, задач {instance.task_queue.qsize()}")
    
    # Start background processor if not already running
    asyncio.create_task(task_processor())
    instance.logger.info(f"Процессор создан")
    
    return {
        "task_id": task_id,
        "status": "pending",
        "message": "Task added to queue (low priority)"
    }


async def process_index_task(
    task_id: str, 
    data: List[ArticleData], 
    update_current: bool, 
    activate: bool, 
    pin: bool, 
    llm: bool,
):
    """Process a reindex task in the background."""
    instance.tasks_db[task_id]["status"] = "processing"
    instance.tasks_db[task_id]["started_at"] = datetime.now(timezone.utc).isoformat()
    instance.tasks_db[task_id]["progress"] = {"step": "starting", "current": 0, "total": len(data)}
    save_tasks_db()
    
    try:
        if not acquire_lock(task_id):
            raise Exception("Failed to acquire lock - another reindex is in progress")
        
        all_texts = []
        metadata_entries = []
        article_ids_set = set()
        
        total_samples = sum(len(article.samples) for article in data)
        processed = 0
        
        for article in data:
            article_ids_set.add(article.id)
            
            for sample in article.samples:                
                # Add original text
                preprocessed = instance.preprocess_text(sample)
                all_texts.append(preprocessed)
                metadata_entry = {
                    "article_id": article.id,
                    "text": preprocessed,
                    "source_type": "original",
                    "parent_sample_id": None
                }
                if article.title:
                    metadata_entry["article_title"] = article.title
                metadata_entries.append(metadata_entry)
                
                # Check if task was cancelled
                _check_task_not_cancelled(task_id)
                instance.tasks_db[task_id]["progress"] = {
                    "step": "saving_db",
                    "current": processed,
                    "total": total_samples
                }
                save_tasks_db()
                
                processed += 1
        
        # Generate synonyms
        try:
            if metadata_entries and llm:
                processed = 0
                metadata_synonyms = []

                for entry in metadata_entries:
                    # Create synonym
                    sample = entry["text"]
                    synonyms = await generate_synonyms(sample)
                    
                    # Add valid synonyms
                    for syn in synonyms:
                        all_texts.append(syn)
                        synonym_entry = {
                            "article_id": entry["article_id"],
                            "text": syn,
                            "source_type": "synonym",
                            "parent_sample_text": sample
                        }
                        if entry.get("article_title"):
                            synonym_entry["article_title"] = entry["article_title"]
                        metadata_synonyms.append(synonym_entry)

                    # Check if task was cancelled
                    _check_task_not_cancelled(task_id)
                    instance.tasks_db[task_id]["progress"] = {
                        "step": "generating_synonyms",
                        "current": processed,
                        "total": total_samples
                    }
                    save_tasks_db()

                    processed += 1
                
                metadata_entries += metadata_synonyms
        except TaskCancelled:
            raise
        except Exception as e:
            pass

        # Check cancellation before embedding operation
        _check_task_not_cancelled(task_id)
        instance.tasks_db[task_id]["progress"] = {"step": "generating_embeddings", "current": 0, "total": len(all_texts)}
        save_tasks_db()
        
        # Generate embeddings
        model = get_embedding_model()
        batch_size = config.batch_size
        all_vectors = []
        
        for i in range(0, len(all_texts), batch_size):
            
            batch = all_texts[i:i+batch_size]
            vectors = model.encode(batch, show_progress_bar=False)
            all_vectors.extend(vectors)
            
            # Check cancellation between batches
            _check_task_not_cancelled(task_id)
            instance.tasks_db[task_id]["progress"] = {
                "step": "generating_embeddings",
                "current": min(i + batch_size, len(all_texts)),
                "total": len(all_texts)
            }
            save_tasks_db()
        
        # Create version ID
        version_id = f"version_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"

        # Check if task was cancelled
        _check_task_not_cancelled(task_id)
        instance.tasks_db[task_id]["parameters"]["version_id"] = version_id
        instance.tasks_db[task_id]["parameters"]["version_name"] = version_id
        save_tasks_db()
        
        if update_current:
            # --- UPDATE CURRENT MODE: merge with active version ---
            if not instance.active_version_id:
                raise Exception("No active version to update. Create a base version first.")
            
            # Load active version's index and metadata
            active_version_path = get_version_path(instance.active_version_id)
            active_index_file = active_version_path / "index.faiss"
            active_metadata_file = active_version_path / "metadata.json"
            
            if not active_index_file.exists() or not active_metadata_file.exists():
                raise Exception(f"Active version {instance.active_version_id} files are corrupted")
            
            existing_index = faiss.read_index(str(active_index_file))
            with open(active_metadata_file, 'r', encoding='utf-8') as f:
                existing_metadata = json.load(f)
            
            # Build a set of existing texts for duplicate detection
            existing_texts = set()
            for entry in existing_metadata.get("data", []):
                existing_texts.add(entry.get("text", ""))
            
            # Filter out duplicates from new data
            unique_texts = []
            unique_metadata_entries = []
            duplicates_count = 0
            
            for i, entry in enumerate(metadata_entries):
                text = entry.get("text", "")
                if text in existing_texts:
                    duplicates_count += 1
                    continue
                unique_texts.append(text)
                unique_metadata_entries.append(entry)
                existing_texts.add(text)  # prevent duplicates within new data too
            
            instance.logger.info(
                f"Update current: {len(metadata_entries)} new items, "
                f"{len(unique_texts)} unique, {duplicates_count} duplicates skipped"
            )
            
            # Generate embeddings for unique texts only
            if unique_texts:
                # Check if task was cancelled
                _check_task_not_cancelled(task_id)
                instance.tasks_db[task_id]["progress"] = {
                    "step": "generating_embeddings",
                    "current": 0,
                    "total": len(unique_texts)
                }
                save_tasks_db()
                
                model = get_embedding_model()
                batch_size = config.batch_size
                new_vectors = []
                
                for i in range(0, len(unique_texts), batch_size):
                    batch = unique_texts[i:i+batch_size]
                    vectors = model.encode(batch, show_progress_bar=False)
                    new_vectors.extend(vectors)
                    
                    # Check cancellation between batches
                    _check_task_not_cancelled(task_id)
                    instance.tasks_db[task_id]["progress"] = {
                        "step": "generating_embeddings",
                        "current": min(i + batch_size, len(unique_texts)),
                        "total": len(unique_texts)
                    }
                    save_tasks_db()
                
                # Add new vectors to existing index with IDs
                new_vectors_array = np.array(new_vectors, dtype=np.float32)
                faiss.normalize_L2(new_vectors_array)
                start_index = len(existing_metadata.get("data", []))
                new_ids = np.arange(start_index, start_index + len(new_vectors), dtype=np.int64)
                existing_index.add_with_ids(new_vectors_array, new_ids)
                faiss_index = existing_index
                
                # Rebuild metadata with correct vector_index
                merged_data = list(existing_metadata.get("data", []))
                for idx, entry in enumerate(unique_metadata_entries):
                    merged_data.append({
                        "vector_index": start_index + idx,
                        **entry
                    })
                
                # Update existing entries' vector_index to match
                for idx in range(len(merged_data)):
                    merged_data[idx]["vector_index"] = idx
                
                metadata = {
                    "version_id": version_id,
                    "version_name": existing_metadata.get("version_name", version_id) + "_updated",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "embedding_model": config.model_name,
                    "vectors_count": len(merged_data),
                    "similarity_threshold": config.similarity_threshold,
                    "data": merged_data
                }
                
                index_array = new_vectors_array
            else:
                # All data was duplicate — clone the active version
                instance.logger.info("Update current: all data is duplicate, cloning active version")
                faiss_index = existing_index
                metadata = {
                    "version_id": version_id,
                    "version_name": existing_metadata.get("version_name", version_id) + "_updated",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "embedding_model": config.model_name,
                    "vectors_count": len(existing_metadata.get("data", [])),
                    "similarity_threshold": config.similarity_threshold,
                    "data": list(existing_metadata.get("data", []))
                }
                index_array = np.zeros((0, existing_index.d), dtype=np.float32)
        else:
            # --- NORMAL MODE: create index from scratch ---
            index_array = np.array(all_vectors, dtype=np.float32)
            faiss_index = create_faiss_index(index_array)
            
            metadata = {
                "version_id": version_id,
                "version_name": version_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "embedding_model": config.model_name,
                "vectors_count": len(index_array),
                "similarity_threshold": config.similarity_threshold,
                "data": [
                    {
                        "vector_index": idx,
                        **entry
                    }
                    for idx, entry in enumerate(metadata_entries)
                ]
            }
        
        # Write to tmp directory
        tmp_path = get_tmp_path(version_id)
        tmp_path.mkdir(parents=True, exist_ok=True)
        
        # Save FAISS index
        index_file = tmp_path / "index.faiss"
        faiss.write_index(faiss_index, str(index_file))
        
        # Save metadata
        metadata_file = tmp_path / "metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        # Save config
        local_config = {
            "version_id": version_id,
            "similarity_threshold": config.similarity_threshold,
            "data_hash": hashlib.blake2b(json.dumps([a.dict() for a in data], sort_keys=True).encode(), digest_size=64).hexdigest()
        }
        
        config_file = tmp_path / "config.json"
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(local_config, f, indent=2)
        
        # Atomic rename: tmp → versions
        version_path = get_version_path(version_id)
        if version_path.exists():
            import shutil
            shutil.rmtree(version_path)
        
        tmp_path.rename(version_path)
        
        # Activate: always activate when update_current, or when activate is True
        if update_current or activate:
            # Hot swap
            instance.active_index = faiss_index
            instance.active_metadata = metadata
            instance.active_version_id = version_id
            
            # Update active version pointer
            save_active_version(version_id)
        
        # Mark as pin if requested
        if pin:
            pin_versions = get_pin_versions()
            if version_id not in pin_versions:
                pin_versions.append(version_id)
                save_pin_versions(pin_versions)
        
        # Apply retention policy
        print(f"apply_retention_policy: called")
        retention_policy_applied, retention_policy_error = apply_retention_policy()
        print(f"apply_retention_policy: {"save" if retention_policy_applied else "deleted"}, {retention_policy_error}")
        if not retention_policy_applied:
            raise Exception(f"Number of versions exceeds its maximum: {retention_policy_error}")
        
        # Release lock
        release_lock()
        
        # Clean up task data file after successful processing
        _clear_index_data(task_id)
        
        # Check if task was cancelled
        _check_task_not_cancelled(task_id)
        # Move task to done_tasks_db
        instance.done_tasks_db[task_id] = {
            "task_id": task_id,
            "parameters": instance.tasks_db[task_id]["parameters"],
            "status": "done",
            "progress": {
                "step": "completed",
                "current": len(all_texts),
                "total": len(all_texts)
            },
            "queued_at": instance.tasks_db[task_id].get("queued_at"),
            "started_at": instance.tasks_db[task_id].get("started_at"),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        del instance.tasks_db[task_id]
        save_tasks_db()
        
        instance.logger.info(f"Index task {task_id} completed successfully. Version: {version_id}")
        
    except Exception as e:
        error = traceback.format_exc(3)
        instance.logger.error(f"Index task {task_id} failed: {error}")
        # instance.logger.error(error)
        # Only update task status if it still exists in tasks_db
        if task_id in instance.tasks_db:
            instance.tasks_db[task_id]["status"] = "failed"
            instance.tasks_db[task_id]["error"] = str(e)
            instance.tasks_db[task_id]["completed_at"] = datetime.now(timezone.utc).isoformat()
            save_tasks_db()
        release_lock()
        # Clear index_data after failure
        _clear_index_data(task_id)


def apply_retention_policy():
    """Apply retention policy to remove old versions."""
    versions_dir = config.data_dir / "versions"
    if not versions_dir.exists():
        return
    
    pin_versions = set(get_pin_versions())
    all_versions = []
    
    for v_dir in versions_dir.iterdir():
        if v_dir.is_dir() and v_dir.name != "tmp":
            all_versions.append(v_dir.name)
    all_versions.sort()
    
    max_versions = config.max_versions
    active_version_id = instance.active_version_id
    versions_to_delete = sorted(set(all_versions) - pin_versions - {active_version_id})

    all_versions_len = len(all_versions)
    if all_versions_len <= max_versions:
        return True, ""

    # Keep only MAX_VERSIONS
    for version in versions_to_delete:
        oldest = versions_to_delete.pop(0)
        version_path = versions_dir / oldest
        shutil.rmtree(version_path)
        instance.logger.info(f"Removed old version: {oldest}")

        all_versions_len -= 1
        if all_versions_len <= max_versions:
            return True, ""

    return False, f"{all_versions_len} out of {max_versions}, of which: {len(pin_versions)} pinned, {int(bool(active_version_id))} active"


async def task_processor():
    """Background task processor for all queued tasks.
    
    Task format: (priority, task_id, task_type, *args)
    - task_type="reindex": (priority, task_id, "reindex", data, update_current, activate, pin, llm)
    - task_type="save_synonyms": (priority, task_id, "save_synonyms", version_id, article_id, article_title, sample_text)
    - task_type="delete": (priority, task_id, "delete", version_id, article_id, sample_or_synonym_id)
    
    This processor runs in a separate thread pool and yields control
    frequently to allow high-priority requests (health, search) to execute immediately.
    """
    while True:
        try:
            item = await asyncio.wait_for(
                instance.task_queue.get(), 
                timeout=1.0
            )
            
            priority = item[0]
            task_id = item[1]
            task_type = item[2]
            
            # Get the running event loop (safe in async context)
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # Event loop is not running - put task back at front of queue
                # and wait using a non-async sleep to avoid awaiting on closed loop.
                # Task will be re-processed on next iteration when loop recovers,
                # or recovered after restart by recover_interrupted_tasks()
                instance.task_queue.put_nowait(item)
                instance.logger.warning("Event loop is not running, will retry...")
                import time
                time.sleep(1)
                continue
            
            if task_type == "reindex":
                # (priority, task_id, "reindex", data, update_current, activate, pin, llm)
                data, update_current, activate, pin, llm = item[3], item[4], item[5], item[6], item[7]
                
                # Check if lock is held by another process (only for reindex)
                if check_lock():
                    await instance.task_queue.put(item)
                    await asyncio.sleep(0.5)
                    continue
                
                # Process the task in executor to avoid blocking event loop
                try:
                    await loop.run_in_executor(
                        instance.executor,
                        lambda: process_index_task_sync(task_id, data, update_current, activate, pin, llm)
                    )
                except Exception as e:
                    instance.logger.error(f"Index task {task_id} executor failed: {e}")
                    # Mark task as failed if it's still in processing state
                    _mark_task_failed_if_processing(task_id, str(e))
            
            elif task_type == "save_synonyms":
                # (priority, task_id, "save_synonyms", version_id, article_id, article_title, sample_texts)
                version_id = item[3]
                article_id = item[4]
                article_title = item[5]
                sample_texts = item[6]
                
                # Process save_synonyms task (generates synonyms via LLM and saves to index)
                try:
                    await loop.run_in_executor(
                        instance.executor,
                        lambda: process_save_synonyms_task_sync(
                            task_id, version_id, article_id, article_title, sample_texts
                        )
                    )
                except Exception as e:
                    instance.logger.error(f"Save synonyms task {task_id} executor failed: {e}")
                    _mark_task_failed_if_processing(task_id, str(e))
            
            elif task_type == "delete":
                # (priority, task_id, "delete", version_id, article_id, sample_or_synonym_ids)
                version_id = item[3]
                article_id = item[4]
                sample_or_synonym_ids = item[5]
                
                # Process delete task
                try:
                    await loop.run_in_executor(
                        instance.executor,
                        lambda: process_delete_task_sync(
                            task_id, version_id, article_id, sample_or_synonym_ids
                        )
                    )
                except Exception as e:
                    instance.logger.error(f"Delete task {task_id} executor failed: {e}")
                    _mark_task_failed_if_processing(task_id, str(e))
            
            elif task_type == "convert_synonym":
                # (priority, task_id, "convert_synonym", version_id, article_id, synonym_ids)
                version_id = item[3]
                article_id = item[4]
                synonym_ids = item[5]
                
                # Process convert_synonym task
                try:
                    await loop.run_in_executor(
                        instance.executor,
                        lambda: process_convert_synonym_task_sync(
                            task_id, version_id, article_id, synonym_ids
                        )
                    )
                except Exception as e:
                    instance.logger.error(f"Convert synonym task {task_id} executor failed: {e}")
                    _mark_task_failed_if_processing(task_id, str(e))
            
            elif task_type == "delete_article":
                # (priority, task_id, "delete_article", version_id, article_id)
                version_id = item[3]
                article_id = item[4]
                
                # Process delete_article task
                try:
                    await loop.run_in_executor(
                        instance.executor,
                        lambda: process_delete_article_task_sync(
                            task_id, version_id, article_id
                        )
                    )
                except Exception as e:
                    instance.logger.error(f"Delete article task {task_id} executor failed: {e}")
                    _mark_task_failed_if_processing(task_id, str(e))
            
            else:
                instance.logger.error(f"Unknown task type: {task_type}")
            
            instance.task_queue.task_done()
            
        except asyncio.TimeoutError:
            # No tasks in queue, continue waiting
            continue
        
        except RuntimeError as e:
            if "Event loop is closed" in str(e):
                instance.logger.error("Event loop closed, stopping task processor")
                break
            instance.logger.error(f"Task processor RuntimeError: {e}")
            await asyncio.sleep(1)
        
        except Exception as e:
            instance.logger.error(f"Task processor error: {e}")
            await asyncio.sleep(1)


def _mark_task_failed_if_processing(task_id: str, error_msg: str):
    """Mark a task as failed if it's still in processing status.
    
    This is a safety net for when the sync wrapper fails before
    it can update the task status itself.
    """
    if task_id in instance.tasks_db:
        task = instance.tasks_db[task_id]
        if task.get("status") == "processing":
            task["status"] = "failed"
            task["error"] = error_msg
            task["completed_at"] = datetime.now(timezone.utc).isoformat()
            save_tasks_db()
            instance.logger.warning(f"Task {task_id} marked as failed by safety net: {error_msg}")


def process_index_task_sync(task_id: str, data: List[ArticleData], update_current: bool, activate: bool, pin: bool, llm: bool):
    """Synchronous wrapper for reindex task processing."""
    # Create new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(process_index_task(task_id, data, update_current, activate, pin, llm))
    finally:
        loop.close()


def process_save_synonyms_task_sync(task_id: str, version_id: str, article_id: str, article_title: str, sample_texts: List[str]):
    """Synchronous handler for save_synonyms task.

    Generates synonyms via LLM and saves them to the index.
    """
    # Create new event loop for this thread to call async generate_synonyms
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        # Update task status to processing
        if task_id in instance.tasks_db:
            instance.tasks_db[task_id]["status"] = "processing"
            instance.tasks_db[task_id]["started_at"] = datetime.now(timezone.utc).isoformat()
            instance.tasks_db[task_id]["progress"] = {
                "step": "generating_synonyms",
                "current": 0,
                "total": len(sample_texts),
            }
            save_tasks_db()

        # Generate synonyms via LLM
        synonyms_to_samples = loop.run_until_complete(generate_synonyms(sample_texts, task_id))

        # Update task status to processing
        if task_id in instance.tasks_db:
            instance.tasks_db[task_id]["progress"]["step"] = "saving_synonyms"
            instance.tasks_db[task_id]["progress"]["current"] = 0
            save_tasks_db()

        # Save synonyms to index
        count = save_synonyms_to_index(version_id, article_id, article_title, synonyms_to_samples, task_id)
        instance.tasks_db[task_id]["parameters"]["synonyms_len"] = count
        save_tasks_db()

        # Update task status to done
        if task_id in instance.tasks_db:
            instance.tasks_db[task_id]["status"] = "done"
            instance.tasks_db[task_id]["progress"]["step"] = "completed"
            instance.tasks_db[task_id]["completed_at"] = datetime.now(timezone.utc).isoformat()
            save_tasks_db()
            instance.logger.info(f"save_synonyms task {task_id} completed: {count} synonyms added")
    except Exception as e:
        instance.logger.error(f"save_synonyms task {task_id} failed: {e}")
        if task_id in instance.tasks_db:
            instance.tasks_db[task_id]["status"] = "failed"
            instance.tasks_db[task_id]["error"] = str(e)
            instance.tasks_db[task_id]["completed_at"] = datetime.now(timezone.utc).isoformat()
            save_tasks_db()
    finally:
        loop.close()


def process_delete_task_sync(task_id: str, version_id: str, article_id: str, sample_or_synonym_ids: str):
    """Synchronous handler for delete task.

    Deletes an sample or synonym from the index and metadata.
    """
    try:
        # Update task status to processing
        if task_id in instance.tasks_db:
            instance.tasks_db[task_id]["status"] = "processing"
            instance.tasks_db[task_id]["started_at"] = datetime.now(timezone.utc).isoformat()
            instance.tasks_db[task_id]["progress"] = {
                "step": "deleting",
                "current": 0,
                "total": len(sample_or_synonym_ids),
            }
            save_tasks_db()

        # Delete from index
        article_title, deleted_count = delete_from_index(version_id, article_id, sample_or_synonym_ids, task_id)

        # Update task status to done
        if task_id in instance.tasks_db:
            instance.tasks_db[task_id]["status"] = "done"
            instance.tasks_db[task_id]["progress"]["step"] = "completed"
            instance.tasks_db[task_id]["completed_at"] = datetime.now(timezone.utc).isoformat()
            save_tasks_db()
            instance.logger.info(f"delete task {task_id} completed: {deleted_count} entries removed")
    except Exception as e:
        error = traceback.format_exc(3)
        instance.logger.error(f"delete task {task_id} failed: {error}")
        if task_id in instance.tasks_db:
            instance.tasks_db[task_id]["status"] = "failed"
            instance.tasks_db[task_id]["error"] = str(e)
            instance.tasks_db[task_id]["completed_at"] = datetime.now(timezone.utc).isoformat()
            save_tasks_db()


def process_convert_synonym_task_sync(task_id: str, version_id: str, article_id: str, synonym_ids: List[str]):
    """Synchronous handler for convert_synonym task.

    Converts one or more synonyms to samples in the index and metadata.
    """
    try:
        # Update task status to processing
        if task_id in instance.tasks_db:
            instance.tasks_db[task_id]["status"] = "processing"
            instance.tasks_db[task_id]["started_at"] = datetime.now(timezone.utc).isoformat()
            instance.tasks_db[task_id]["progress"] = {
                "step": "converting",
                "current": 0,
                "total": len(synonym_ids),
            }
            save_tasks_db()

        # Convert synonyms to samples
        article_title, converted_count = convert_synonym_to_sample(version_id, article_id, synonym_ids, task_id)

        # Update task status to done
        if task_id in instance.tasks_db:
            instance.tasks_db[task_id]["status"] = "done"
            instance.tasks_db[task_id]["progress"]["step"] = "completed"
            instance.tasks_db[task_id]["completed_at"] = datetime.now(timezone.utc).isoformat()
            save_tasks_db()
            instance.logger.info(f"convert_synonym task {task_id} completed: {converted_count} synonyms converted")
    except Exception as e:
        instance.logger.error(f"convert_synonym task {task_id} failed: {e}")
        if task_id in instance.tasks_db:
            instance.tasks_db[task_id]["status"] = "failed"
            instance.tasks_db[task_id]["error"] = str(e)
            instance.tasks_db[task_id]["completed_at"] = datetime.now(timezone.utc).isoformat()
            save_tasks_db()


def process_delete_article_task_sync(task_id: str, version_id: str, article_id: str):
    """Synchronous handler for delete_article task.

    Deletes an entire article by removing all its samples (and dependent synonyms)
    from the index and metadata.
    """
    try:
        # Load article data to get all sample IDs
        metadata = get_version_metadata(version_id)
        articles_data = build_article_data(metadata)

        if article_id not in articles_data:
            raise Exception(f"Article {article_id} not found in version {version_id}")

        article_data = articles_data[article_id]
        article_title = article_data["article_title"]
        samples_dict = article_data["samples"]

        # Collect all sample IDs
        sample_ids = [eid for eid in samples_dict if eid.startswith("smp_")]

        if not sample_ids:
            raise Exception(f"No samples found for article {article_id}")

        # Update task status to processing
        if task_id in instance.tasks_db:
            instance.tasks_db[task_id]["status"] = "processing"
            instance.tasks_db[task_id]["started_at"] = datetime.now(timezone.utc).isoformat()
            instance.tasks_db[task_id]["progress"] = {
                "step": "deleting_article",
                "current": 0,
                "total": len(sample_ids),
            }
            save_tasks_db()

        # Delete all samples from index (synonyms will be removed automatically)
        deleted_article_title, deleted_count = delete_from_index(version_id, article_id, sample_ids, task_id)

        # Update task status to done
        if task_id in instance.tasks_db:
            instance.tasks_db[task_id]["status"] = "done"
            instance.tasks_db[task_id]["progress"]["step"] = "completed"
            instance.tasks_db[task_id]["completed_at"] = datetime.now(timezone.utc).isoformat()
            instance.tasks_db[task_id]["parameters"]["deleted_count"] = deleted_count
            save_tasks_db()
            instance.logger.info(f"delete_article task {task_id} completed: article {article_id} removed ({deleted_count} entries)")
    except Exception as e:
        instance.logger.error(f"delete_article task {task_id} failed: {e}")
        if task_id in instance.tasks_db:
            instance.tasks_db[task_id]["status"] = "failed"
            instance.tasks_db[task_id]["error"] = str(e)
            instance.tasks_db[task_id]["completed_at"] = datetime.now(timezone.utc).isoformat()
            save_tasks_db()
