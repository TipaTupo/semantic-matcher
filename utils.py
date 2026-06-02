import os
import re
import json
import faiss
import hashlib
import traceback
import numpy as np

from pathlib import Path
from ollama import ChatResponse
from functools import singledispatch
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple
from sentence_transformers import SentenceTransformer

from config import config
from instance import instance
from schemas import ArticleData, QueueStatusResponse


def load_embedding_model() -> SentenceTransformer:
    """
    Load model from local folder specified in MODEL_PATH
    No internet connection required
    
    Returns:
        SentenceTransformer: Loaded embedding model
    """
    model_path = config.model_path
    
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Local model path does not exist: {model_path}.")
    
    instance.logger.info(f"Loading model from local path: {model_path}")
    model = SentenceTransformer(
        model_path,
        local_files_only=True  # Force offline loading
    )
    
    instance.logger.info(f"Model loaded successfully. Device: {model.device}")
    return model


def get_embedding_model() -> SentenceTransformer:
    """
    Get the global embedding model instance.
    Loads the model on first call, then returns cached instance.
    
    Returns:
        SentenceTransformer: The loaded embedding model
    """
    if instance.model is None:
        instance.model = load_embedding_model()
    return instance.model


def create_faiss_index(vectors: np.ndarray) -> faiss.IndexIDMap2:
    """
    Create FAISS index with normalized vectors for cosine similarity.
    Uses IndexIDMap2 wrapper over IndexFlatIP to support efficient add/remove by ID.
    Uses Inner Product (IP) which is equivalent to cosine similarity for normalized vectors.
    
    Args:
        vectors: numpy array of shape (n_vectors, dimension)
    
    Returns:
        faiss.IndexIDMap2: FAISS index with added vectors
    """
    dimension = vectors.shape[1]
    inner_index = faiss.IndexFlatIP(dimension)
    index = faiss.IndexIDMap2(inner_index)
    
    # Normalize vectors for cosine similarity
    faiss.normalize_L2(vectors)
    
    # Add with sequential IDs (0, 1, 2, ...) which correspond to vector_index in metadata
    ids = np.arange(vectors.shape[0], dtype=np.int64)
    index.add_with_ids(vectors, ids)
    
    instance.logger.info(f"FAISS index created with {index.ntotal} vectors, dimension {dimension}")
    return index


def search_faiss_index(
    index: faiss.IndexIDMap2, 
    query_vector: np.ndarray, 
    k: int
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Search in FAISS index for top-k most similar vectors.
    
    With IndexIDMap2, the returned indices are the IDs assigned via add_with_ids(),
    which correspond to vector_index in metadata.
    
    Args:
        index: FAISS index (IndexIDMap2)
        query_vector: query vector of shape (dimension,)
        k: number of results to return
    
    Returns:
        Tuple of (distances, ids) arrays — IDs can be used directly as metadata["data"] indices
    """
    # Reshape query vector to (1, dimension)
    query = query_vector.reshape(1, -1).astype(np.float32)
    
    # Normalize query vector
    faiss.normalize_L2(query)
    
    # Search
    distances, indices = index.search(query, k)
    
    return distances[0], indices[0]


def get_version_path(version_id: str) -> Path:
    """Get path to version directory."""
    return config.data_dir / "versions" / version_id


def get_tmp_path(version_id: str) -> Path:
    """Get path to temporary version directory."""
    return config.data_dir / "tmp" / version_id


def ensure_data_dirs():
    """Ensure all required data directories exist."""
    config.data_dir.mkdir(parents=True, exist_ok=True)
    (config.data_dir / "versions").mkdir(exist_ok=True)
    (config.data_dir / "tmp").mkdir(exist_ok=True)
    (config.data_dir / "task_data").mkdir(exist_ok=True)


def _get_task_data_path(task_id: str) -> Path:
    """Get path to task data file."""
    return config.data_dir / "task_data" / f"{task_id}.json"


def save_task_data(task_id: str, data: List[ArticleData]):
    """Save task training data to a separate file storage."""
    task_data_path = _get_task_data_path(task_id)
    task_data_path.parent.mkdir(parents=True, exist_ok=True)
    with open(task_data_path, 'w', encoding='utf-8') as f:
        json.dump([item.dict() for item in data], f, indent=2, ensure_ascii=False)
    instance.logger.info(f"Task data saved: {task_data_path}")


def load_task_data(task_id: str) -> List[ArticleData]:
    """Load task training data from file storage."""
    task_data_path = _get_task_data_path(task_id)
    if not task_data_path.exists():
        raise FileNotFoundError(f"Task data file not found: {task_data_path}")
    with open(task_data_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return [ArticleData(**item) for item in data]


def delete_task_data(task_id: str):
    """Delete task training data file."""
    task_data_path = _get_task_data_path(task_id)
    if task_data_path.exists():
        task_data_path.unlink()
        instance.logger.info(f"Task data deleted: {task_data_path}")


def cleanup_orphan_task_data():
    """Remove task data files that have no corresponding task in tasks_db or done_tasks_db."""
    task_data_dir = config.data_dir / "task_data"
    if not task_data_dir.exists():
        return
    
    all_task_ids = set(instance.tasks_db.keys()) | set(instance.done_tasks_db.keys())
    orphaned = 0
    
    for f in task_data_dir.glob("*.json"):
        task_id = f.stem
        if task_id not in all_task_ids:
            f.unlink()
            orphaned += 1
            instance.logger.info(f"Removed orphan task data: {f}")
    
    if orphaned > 0:
        instance.logger.info(f"Cleaned up {orphaned} orphan task data file(s)")


def load_active_version():
    """Load the active version from disk."""
    active_version_file = config.data_dir / "active_version.json"
    
    if not active_version_file.exists():
        instance.logger.info("No active version found, starting fresh")
        return
    
    try:
        with open(active_version_file, 'r', encoding='utf-8') as f:
            active_info = json.load(f)
        
        instance.active_version_id = active_info.get("version")
        if not instance.active_version_id:
            instance.logger.warning("No version ID in active_version.json")
            return
        
        version_path = get_version_path(instance.active_version_id)
        
        if not version_path.exists():
            instance.logger.error(f"Version directory not found: {version_path}")
            return
        
        # Load FAISS index
        index_file = version_path / "index.faiss"
        if index_file.exists():
            instance.active_index = faiss.read_index(str(index_file))
            instance.logger.info(f"Loaded FAISS index with {instance.active_index.ntotal} vectors")
        
        # Load metadata
        metadata_file = version_path / "metadata.json"
        if metadata_file.exists():
            with open(metadata_file, 'r', encoding='utf-8') as f:
                instance.active_metadata = json.load(f)
            instance.logger.info(f"Loaded metadata with {len(instance.active_metadata.get('data', []))} entries")
        
        instance.logger.info(f"Active version loaded: {instance.active_version_id}")
        
    except Exception as e:
        instance.logger.error(f"Failed to load active version: {e}")


def save_active_version(version_id: str):
    """Save active version pointer to disk."""
    active_version_file = config.data_dir / "active_version.json"
    with open(active_version_file, 'w', encoding='utf-8') as f:
        json.dump({
            "version": version_id,
            "activated_at": datetime.now(timezone.utc).isoformat()
        }, f, indent=2)


def rename_version(version_id: str, version_name: str):
    version_path = get_version_path(version_id)
    metadata_file = version_path / "metadata.json"

    with open(metadata_file, 'r', encoding='utf-8') as f:
        metadata = json.load(f)

    metadata["version_name"] = version_name

    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)


def get_pin_versions() -> List[str]:
    """Get list of pinned version IDs."""
    pin_file = config.data_dir / "pinned_versions.json"
    if not pin_file.exists():
        return []
    
    try:
        with open(pin_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []


def save_pin_versions(versions: List[str]):
    """Save stable versions list to disk."""
    pin_file = config.data_dir / "pinned_versions.json"
    with open(pin_file, 'w', encoding='utf-8') as f:
        json.dump(versions, f, indent=2)


def load_tasks_db():
    """Load tasks databases from disk.
    
    - tasks.json → instance.tasks_db (active, pending, failed)
    - done_tasks.json → instance.done_tasks_db (done)
    
    Handles overlap: if a done-task exists in both files (e.g., restart after save but before removal),
    the copy in done_tasks.json takes priority.
    """
    tasks_file = config.data_dir / "tasks.json"
    done_tasks_file = config.data_dir / "done_tasks.json"
    
    # Load active tasks
    active_tasks = {}
    if tasks_file.exists():
        try:
            with open(tasks_file, 'r', encoding='utf-8') as f:
                active_tasks = json.load(f)
        except:
            active_tasks = {}
    
    # Load done tasks
    done_tasks = {}
    if done_tasks_file.exists():
        try:
            with open(done_tasks_file, 'r', encoding='utf-8') as f:
                done_tasks = json.load(f)
        except:
            done_tasks = {}
    
    # Migrate done tasks from active_tasks to done_tasks (overlap handling)
    tasks_to_remove = []
    for task_id, task_info in active_tasks.items():
        if task_info.get("status") == "done":
            # Only add if not already in done_tasks (done_tasks takes priority)
            if task_id not in done_tasks:
                done_tasks[task_id] = task_info
            tasks_to_remove.append(task_id)
    
    for task_id in tasks_to_remove:
        del active_tasks[task_id]
    
    # Save cleaned active tasks if we migrated any
    if tasks_to_remove:
        with open(tasks_file, 'w', encoding='utf-8') as f:
            json.dump(active_tasks, f, indent=2)
        instance.logger.info(f"Migrated {len(tasks_to_remove)} done task(s) from tasks.json to done_tasks.json")
    
    instance.tasks_db = active_tasks
    instance.done_tasks_db = done_tasks


def save_tasks_db():
    """Save tasks databases to disk.
    
    - instance.tasks_db → tasks.json (active, pending, failed)
    - instance.done_tasks_db → done_tasks.json (done)
    """
    tasks_file = config.data_dir / "tasks.json"
    done_tasks_file = config.data_dir / "done_tasks.json"
    
    with open(tasks_file, 'w', encoding='utf-8') as f:
        json.dump(instance.tasks_db, f, indent=2)
    
    with open(done_tasks_file, 'w', encoding='utf-8') as f:
        json.dump(instance.done_tasks_db, f, indent=2)


def check_lock() -> bool:
    """Check if lock file exists and is valid. Returns True if locked."""
    if not instance.lock_file_path.exists():
        return False
    
    try:
        with open(instance.lock_file_path, 'r', encoding='utf-8') as f:
            lock_info = json.load(f)
        
        pid = lock_info.get("pid")
        started_at = lock_info.get("started_at")
        
        # Check if process is still running
        import signal
        try:
            os.kill(pid, 0)
            process_alive = True
        except (OSError, ProcessLookupError):
            process_alive = False
        
        # Check for stale lock
        if not process_alive:
            started_dt = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
            age_minutes = (datetime.now(started_dt.tzinfo) - started_dt).total_seconds() / 60
            
            if age_minutes > config.stale_lock_timeout_mins:
                instance.logger.info(f"Removing stale lock (age: {age_minutes:.1f} min)")
                instance.lock_file_path.unlink()
                return False
        
        return process_alive
        
    except Exception as e:
        instance.logger.error(f"Error checking lock: {e}")
        return False


def acquire_lock(task_id: str) -> bool:
    """Acquire lock for reindexing. Returns True if successful."""
    if check_lock():
        return False
    
    instance.lock_file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(instance.lock_file_path, 'w', encoding='utf-8') as f:
        json.dump({
            "pid": os.getpid(),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "task_id": task_id
        }, f, indent=2)
    
    return True


def release_lock():
    """Release the reindex lock."""
    if instance.lock_file_path.exists():
        instance.lock_file_path.unlink()


def parse_llm_response(response: ChatResponse) -> List[str]:
    """Parse LLM response and extract synonyms list.
    
    Handles multiple response formats:
    - Clean JSON
    - JSON wrapped in markdown code blocks (```json ... ```)
    - JSON with extra text before/after
    """
    # Step 1: Strip markdown code blocks if present
    text = response.strip()
    if text.startswith("```"):
        # Remove opening ```json or ```
        text = re.sub(r'^```(?:json|JSON)?\s*', '', text)
        # Remove closing ```
        text = re.sub(r'\s*```$', '', text)
        text = text.strip()
    
    # Step 2: Try to find JSON object in the text (in case of extra prose)
    json_match = re.search(r'\{[^{}]*"synonyms"\s*:[^{}]*\}', text, re.DOTALL)
    if json_match:
        text = json_match.group(0)
    
    # Step 3: Parse JSON
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        instance.logger.warning(f"parse_llm_response JSON decode error: {e}. response: {response[:200]}")
        return []
    
    # Step 4: Extract and validate synonyms
    synonyms = data.get("synonyms")
    if not isinstance(synonyms, list):
        instance.logger.warning(f"parse_llm_response: 'synonyms' is not a list. response: {response[:200]}")
        return []
    
    # Filter: keep only non-empty strings, strip whitespace, deduplicate preserving order
    result = []
    seen = set()
    for s in synonyms:
        if isinstance(s, str):
            cleaned = s.strip().rstrip('.')
            if cleaned and cleaned.lower() not in seen:
                result.append(cleaned)
                seen.add(cleaned.lower())
    
    return result


async def send_llm_request(question: str) -> List[str]:
    """Generate synonyms using internal LLM (stub implementation)."""
    try:
        # Create a fresh AsyncClient for the current event loop.
        # instance.llm was created in the main loop and cannot be reused
        # from a different loop (e.g. inside run_in_executor threads).
        # The client is short-lived and will be GC'd after this function returns.
        from ollama import AsyncClient
        llm_client = AsyncClient(host=config.llm_url, headers={
            'X-Gateway-Api-Key': config.llm_api_key,
            'Authorization': f"Bearer {config.llm_auth_token}",
        })
        response = await llm_client.chat(
            model=config.llm_model,
            stream=False,
            messages=[
                {
                    "role": "system",
                    "content": """
Ты — помощник для генерации синонимичных формулировок.
Отвечай ТОЛЬКО валидным JSON без дополнительного текста.
Формат: {"synonyms": ["текст1", "текст2", ...]}
Не используй markdown-разметку, не добавляй объяснений.
                    """.strip()
                },
                {
                    "role": "user",
                    "content": config.llm_prompt.format(question=question)
                }
            ],
            options={
                'temperature': config.llm_temperature,
                'top_p': config.llm_top_p,
                'frequency_penalty': config.llm_frequency_penalty,
                'repeat_penalty': config.llm_repeat_penalty,
                'presence_penalty': config.llm_presence_penalty,
            },
            format='json'
        )
        data = parse_llm_response(response.message.content)
        return data
    except Exception as e:
        error = traceback.format_exc(3)
        instance.logger.info(f"process_index_task generate_synonyms send_llm_request: {error}")
        return []


@singledispatch
async def generate_synonyms(sample: str) -> List[str]:
    if not sample:
        return []

    synonyms = await send_llm_request(sample)
    model = get_embedding_model()
    threshold = config.synonym_validation_threshold

    valid_synonyms = [
        instance.preprocess_text(syn) for syn in synonyms 
        if validate_synonym(model, sample, syn, threshold)
    ]

    return valid_synonyms


@generate_synonyms.register(list)
async def _(samples: List[str], task_id: str) -> List[Tuple[str, List[str]]]:
    instance.logger.info(f"process_index_task generate_synonyms.register: samples - {bool(samples)}")
    if not samples:
        return []

    all_synonyms = []
    for sample in samples:
        synonyms = await send_llm_request(sample)
        model = get_embedding_model()
        threshold = config.synonym_validation_threshold

        valid_synonyms = [
            instance.preprocess_text(syn) for syn in synonyms 
            if validate_synonym(model, sample, syn, threshold)
        ]
        all_synonyms.append([sample, valid_synonyms])
        
        instance.tasks_db[task_id]["progress"]["current"] += 1
        save_tasks_db()

    return all_synonyms


def validate_synonym(model: SentenceTransformer, original: str, synonym: str, threshold: float = 0.75) -> bool:
    """Validate synonym using cosine similarity."""
    try:
        orig_vec = model.encode([instance.preprocess_text(original)], show_progress_bar=False)[0]
        syn_vec = model.encode([instance.preprocess_text(synonym)], show_progress_bar=False)[0]
        
        similarity = np.dot(orig_vec, syn_vec) / (np.linalg.norm(orig_vec) * np.linalg.norm(syn_vec) + 1e-9)
        return similarity >= threshold
    except Exception as e:
        instance.logger.warning(f"Synonym validation failed: {e}")
        return False


def get_version_metadata(version_id: str) -> Dict:
    """Load metadata for a specific version."""
    version_path = get_version_path(version_id)
    
    if not version_path.exists():
        raise HTTPException(status_code=404, detail="Version not found")
    
    metadata_file = version_path / "metadata.json"
    if not metadata_file.exists():
        raise HTTPException(status_code=400, detail="Version metadata not found")
    
    with open(metadata_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def build_article_data(metadata: Dict) -> Dict[str, Dict]:
    """
    Build article data structure from metadata.
    Returns dict: article_id -> {article_title, samples: {id: text}, synonyms: {id: text}}
    
    Sample and synonym IDs are generated as:
    - samples: "smp_{article_id}_{index}"
    - synonyms: "syn_{article_id}_{index}"
    
    Note: article_title is optional in metadata (kept for backward compatibility with old versions).
    """
    articles = {}
    
    for entry in metadata.get("data", []):
        article_id = entry["article_id"]
        article_title = entry.get("article_title", "")
        text = entry["text"]
        source_type = entry.get("source_type", "original")
        parent_sample_id = entry.get("parent_sample_id")
        
        if article_id not in articles:
            articles[article_id] = {
                "article_title": article_title,
                "samples": {},
                "synonyms": {}
            }
        
        if source_type == "original":
            # Generate sample ID based on article_id and text hash for consistency
            sample_id = f"smp_{article_id}_{hashlib.blake2b(text.encode(), digest_size=8).hexdigest()[:8]}"
            articles[article_id]["samples"][sample_id] = text
        elif source_type == "synonym":
            # Generate synonym ID based on article_id and text hash
            synonym_id = f"syn_{article_id}_{hashlib.blake2b(text.encode(), digest_size=8).hexdigest()[:8]}"
            articles[article_id]["synonyms"][synonym_id] = text
    
    return articles


def save_synonyms_to_index(
    version_id: str,
    article_id: str,
    article_title: str,
    synonyms_to_samples: List[Tuple[str, List[str]]],
    task_id: str,
) -> int:
    """Save generated synonyms to an existing version's FAISS index (mutation).
    
    Args:
        synonyms_to_samples: list of [sample_text, synonyms_list] pairs
    
    CPU-bound function intended to be run in a thread executor.
    Returns the number of synonyms added.
    """
    if not synonyms_to_samples:
        return 0
    
    version_path = get_version_path(version_id)
    index_file = version_path / "index.faiss"
    metadata_file = version_path / "metadata.json"
    
    if not index_file.exists() or not metadata_file.exists():
        instance.logger.error(f"save_synonyms_to_index: version files not found for {version_id}")
        return 0
    
    # Load index and metadata
    index = faiss.read_index(str(index_file))
    
    with open(metadata_file, 'r', encoding='utf-8') as f:
        metadata = json.load(f)
    
    model = get_embedding_model()
    
    # Collect all synonyms and their metadata across all sample/synonym pairs
    all_vectors = []
    all_entries = []
    start_index = len(metadata.get("data", []))
    
    for sample_text, synonyms in synonyms_to_samples:
        if not synonyms:
            continue
        
        preprocessed_synonyms = [instance.preprocess_text(syn) for syn in synonyms]
        vectors = model.encode(preprocessed_synonyms, show_progress_bar=False)
        sample_preprocessed = instance.preprocess_text(sample_text)
        
        for i, syn_text in enumerate(preprocessed_synonyms):
            vector_id = start_index + len(all_vectors)
            entry = {
                "vector_index": vector_id,
                "article_id": article_id,
                "text": syn_text,
                "source_type": "synonym",
                "parent_sample_text": sample_preprocessed,
            }
            if article_title:
                entry["article_title"] = article_title
            all_entries.append(entry)
            all_vectors.append(vectors[i])
        
        instance.tasks_db[task_id]["progress"]["current"] += 1
        save_tasks_db()
    
    if not all_vectors:
        return 0
    
    # Normalize and add to index
    vectors_array = np.array(all_vectors, dtype=np.float32)
    faiss.normalize_L2(vectors_array)
    
    new_ids = np.array([entry["vector_index"] for entry in all_entries], dtype=np.int64)
    index.add_with_ids(vectors_array, new_ids)
    
    # Append metadata entries
    metadata["data"].extend(all_entries)
    metadata["vectors_count"] = len(metadata["data"])
    
    # Save index
    faiss.write_index(index, str(index_file))
    
    # Save metadata
    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    # Update active index in memory if this is the active version
    if instance.active_version_id == version_id:
        instance.active_index = index
        instance.active_metadata = metadata
    
    total_added = len(all_vectors)
    instance.logger.info(
        f"save_synonyms_to_index: added {total_added} synonyms "
        f"for article {article_id} to version {version_id}"
    )
    
    return total_added


def delete_from_index(
    version_id: str,
    article_id: str,
    sample_or_synonym_ids: List[str],
    task_id: str,
) -> tuple:
    """Delete an sample or synonym from a version's FAISS index and metadata.
    
    Uses IndexIDMap2.remove_ids() for efficient deletion.
    
    CPU-bound function intended to be run in a thread executor.
    
    Returns:
        Tuple of (article_title, deleted_text, deleted_count)
    """
    version_path = get_version_path(version_id)
    index_file = version_path / "index.faiss"
    metadata_file = version_path / "metadata.json"
    
    if not index_file.exists() or not metadata_file.exists():
        instance.logger.error(f"delete_from_index: version files not found for {version_id}")
        return ("", "", 0)
    
    # Load index and metadata
    index = faiss.read_index(str(index_file))
    
    with open(metadata_file, 'r', encoding='utf-8') as f:
        metadata = json.load(f)
    
    data = metadata.get("data", [])
    
    # Determine if targeting an sample or synonym
    ids_to_remove = set()
    for sample_or_synonym_id in sample_or_synonym_ids:
        is_sample = sample_or_synonym_id.startswith("smp_")
        is_synonym = sample_or_synonym_id.startswith("syn_")
        target_source_type = "original" if is_sample else "synonym"
        
        # Find the target entry(ies) by computing IDs
        entries_to_remove = []  # list of (index_in_data, entry)
        
        for i, entry in enumerate(data):
            if entry.get("article_id") != article_id:
                continue
            if entry.get("source_type") != target_source_type:
                continue
            
            text = entry.get("text", "")
            computed_id = f"{'ex' if is_sample else 'syn'}_{article_id}_{hashlib.blake2b(text.encode(), digest_size=8).hexdigest()[:8]}"
            
            if computed_id == sample_or_synonym_id:
                entries_to_remove.append((i, entry))
        
        if not entries_to_remove:
            instance.logger.warning(f"delete_from_index: entry {sample_or_synonym_id} not found")
            raise Exception(f"Entry {sample_or_synonym_id} not found")
        
        # Get the primary target
        target_entry = entries_to_remove[0][1]
        article_title = target_entry.get("article_title", "")
        target_text = target_entry.get("text", "")
        
        # If deleting an sample, also find and mark its synonyms for removal        
        for idx, entry in entries_to_remove:
            ids_to_remove.add(entry.get("vector_index"))
        
        if is_sample:
            # Find all synonyms of this sample
            parent_text = target_text
            for i, entry in enumerate(data):
                if entry.get("source_type") == "synonym" and entry.get("parent_sample_text") == parent_text:
                    ids_to_remove.add(entry.get("vector_index"))
        
        if not ids_to_remove:
            instance.logger.warning(f"delete_from_index: no vector IDs found for removal")
            raise Exception(f"No vector IDs found for removal")

        instance.tasks_db[task_id]["progress"]["current"] += 1
        save_tasks_db()
    
    # Remove from FAISS index using IndexIDMap2.remove_ids()
    ids_array = np.array(sorted(ids_to_remove), dtype=np.int64)
    index.remove_ids(ids_array)
    
    # Remove from metadata data list
    removed_count = len(ids_to_remove)
    metadata["data"] = [
        entry for entry in data if entry.get("vector_index") not in ids_to_remove
    ]
    
    # Update vectors_count
    metadata["vectors_count"] = len(metadata["data"])
    
    # Save index
    faiss.write_index(index, str(index_file))
    
    # Save metadata
    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    # Update active index in memory if this is the active version
    if instance.active_version_id == version_id:
        instance.active_index = index
        instance.active_metadata = metadata
    
    instance.logger.info(
        f"delete_from_index: removed {removed_count} entry(ies) from article {article_id} in version {version_id}"
    )
    
    return (article_title, removed_count)


def convert_synonym_to_sample(
    version_id: str,
    article_id: str,
    synonym_ids: List[str],
    task_id: str,
) -> tuple:
    """Convert one or more synonyms to samples in a version's FAISS index and metadata.

    The synonym entries are kept in the index but their source_type is changed
    from "synonym" to "original" and parent_sample_text is cleared.
    No new embeddings are generated — the existing vector is reused.

    CPU-bound function intended to be run in a thread executor.

    Returns:
        Tuple of (article_title, converted_count)
    """
    version_path = get_version_path(version_id)
    index_file = version_path / "index.faiss"
    metadata_file = version_path / "metadata.json"

    if not index_file.exists() or not metadata_file.exists():
        instance.logger.error(f"convert_synonym_to_sample: version files not found for {version_id}")
        return ("", 0)

    # Load metadata
    with open(metadata_file, 'r', encoding='utf-8') as f:
        metadata = json.load(f)

    data = metadata.get("data", [])
    article_title = ""
    converted_count = 0

    # Collect all synonym texts for validation
    synonym_texts = []
    for synonym_id in synonym_ids:
        if not synonym_id.startswith("syn_"):
            continue

        # Find the target entry by computing ID
        for entry in data:
            if entry.get("article_id") != article_id:
                continue
            if entry.get("source_type") != "synonym":
                continue

            text = entry.get("text", "")
            computed_id = f"syn_{article_id}_{hashlib.blake2b(text.encode(), digest_size=8).hexdigest()[:8]}"

            if computed_id == synonym_id:
                synonym_texts.append(text)
                if not article_title:
                    article_title = entry.get("article_title", "")
                break

    # Convert synonyms to samples in metadata
    for entry in data:
        if entry.get("article_id") != article_id:
            continue
        if entry.get("source_type") != "synonym":
            continue

        text = entry.get("text", "")
        computed_id = f"syn_{article_id}_{hashlib.blake2b(text.encode(), digest_size=8).hexdigest()[:8]}"

        if computed_id in synonym_ids and text in synonym_texts:
            entry["source_type"] = "original"
            entry.pop("parent_sample_text", None)
            converted_count += 1

            instance.tasks_db[task_id]["progress"]["current"] += 1
            save_tasks_db()

    # Update vectors_count (it stays the same since we only change metadata)
    metadata["vectors_count"] = len(metadata["data"])

    # Save metadata
    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    # Update active metadata in memory if this is the active version
    if instance.active_version_id == version_id:
        instance.active_metadata = metadata

    instance.logger.info(
        f"convert_synonym_to_sample: converted {converted_count} synonym(s) "
        f"to sample(s) for article {article_id} in version {version_id}"
    )

    return (article_title, converted_count)


def update_stop_words(stop_words: List[str]) -> tuple:
    """Update stop-words list"""
    is_data_valid = isinstance(stop_words, list) and all(isinstance(s, str) for s in stop_words)
    if not is_data_valid:
        raise TypeError("Невалидный список стоп-слов, Ожидался список строк list(str)")

    # Find the differences between the current and new stopword lists
    current_stop_words = set(instance.preprocess_text(s, False) for s in instance.stop_words)
    new_stop_words = set(instance.preprocess_text(s, False) for s in stop_words)

    # Count resulting data
    added = list(new_stop_words - current_stop_words)
    deleted = list(current_stop_words - new_stop_words)

    # Update instance stop-words list
    if added or deleted:
        instance.update_stop_words(sorted(new_stop_words))

    return len(new_stop_words), added, deleted


def get_all_tasks() -> QueueStatusResponse:
    """Get all tasks from tasks and done tasks databases"""
    active_tasks = []
    queued_tasks = []
    failed_tasks = []
    for task_info in instance.tasks_db.values():
        if task_info.get("status") == "processing":
            active_tasks.append(task_info)
        elif task_info.get("status") == "pending":
            queued_tasks.append(task_info)
        elif task_info.get("status") == "failed":
            failed_tasks.append(task_info)
    
    # Done tasks are stored separately
    done_tasks = []
    for task_info in instance.done_tasks_db.values():
        done_tasks.append(task_info)
    
    return QueueStatusResponse(
        active_tasks=active_tasks,
        queued_tasks=queued_tasks,
        failed_tasks=failed_tasks,
        done_tasks=done_tasks,
    )
