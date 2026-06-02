import os
import re
import json
import shutil
import string
import asyncio
import logging
import numpy as np
import concurrent.futures

from pathlib import Path
from ollama import AsyncClient
from typing import List, Dict, Optional
from sentence_transformers import SentenceTransformer

from config import config


class Instance:

    def __init__(self):
        # Service var
        self._BLANK_LIST = []
        self._BLANK_DICT = {}

        # Logger
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger(__name__)
        self.logger = logger

        # Stop-words
        self.stop_words_path: Path = config.data_dir / "stop-words.json"
        self.stop_words: List[str] = self._load_stop_words()
        self.stop_words_pattern: re.Pattern = self._update_stop_words_pattern()

        # Database config (LLM description + topic)
        self.database_config_path: Path = config.data_dir / "database-config.json"
        self.database_config: Dict[str, str] = self._load_database_config()

        # Delete punctuation
        self.translator: Dict[int, int | None] = str.maketrans('', '', string.punctuation)

        # In-memory index
        self.active_index: Optional[np.ndarray] = None
        self.active_metadata: Optional[Dict] = None
        self.active_version_id: Optional[str] = None

        # Task queues with priorities (lower number = higher priority)
        # Priority 1: health, search (always immediate)
        # Priority 2: queue, versions (medium priority)
        # Priority 3: reindex tasks (low priority, background)
        self.HIGH_PRIORITY_QUEUE: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self.MEDIUM_PRIORITY_TASKS = set()  # Track medium priority task IDs
        self.task_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()  # Priority 3 for reindex
        self.tasks_db: Dict[str, dict] = {}  # active, pending, failed tasks
        self.done_tasks_db: Dict[str, dict] = {}  # done tasks (separate storage)

        # Lock management
        self.lock_file_path: Path = config.data_dir / ".reindex.lock"

        # Executor for CPU-bound tasks
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="index_worker")

        # Model
        self.model: SentenceTransformer | None = None

        # LLM
        self.llm: AsyncClient = AsyncClient(host=config.llm_url, headers={
            'X-Gateway-Api-Key': config.llm_api_key,
            'Authorization': f"Bearer {config.llm_auth_token}",
        })

        # Frontend
        self.front_path: Path = Path(__file__).parent / "front"


    def _load_stop_words(self) -> List[str]:
        data_path = self.stop_words_path
        default_path = "/app/stop-words.json"

        if os.path.exists(data_path):
            with open(data_path, 'r', encoding="utf-8") as f:
                stop_words = json.load(f)
            return stop_words
        
        elif os.path.exists(default_path):
            shutil.copy(default_path, data_path)
            with open(data_path, 'r', encoding="utf-8") as f:
                stop_words = json.load(f)
            return stop_words
        
        else:
            with open(data_path, 'w', encoding="utf-8") as f:
                json.dump(self._BLANK_LIST, f)
            return self._BLANK_LIST
    
    
    def _update_stop_words_pattern(self) -> re.Pattern:
        return re.compile(r'\b(' + '|'.join(map(re.escape, self.stop_words)) + r')\b', re.UNICODE)

    
    def update_stop_words(self, stop_words: List[str]):
        with open(self.stop_words_path, 'w', encoding="utf-8") as f:
            json.dump(stop_words, f, indent=2, ensure_ascii=False)
        self.stop_words = stop_words
        self.stop_words_pattern = self._update_stop_words_pattern()

    def _load_database_config(self) -> Dict[str, str]:
        if self.database_config_path.exists():
            with open(self.database_config_path, 'r', encoding="utf-8") as f:
                return json.load(f)
        else:
            default_config = {"llm_description": "", "llm_topic": ""}
            with open(self.database_config_path, 'w', encoding="utf-8") as f:
                json.dump(default_config, f, indent=2, ensure_ascii=False)
            return default_config

    def update_database_config(self, config: Dict[str, str]):
        with open(self.database_config_path, 'w', encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        self.database_config = config


    def preprocess_text(self, text: str, delete_stop_words: bool = True) -> str:
        # Convert to lowercase and remove punctuation
        text = text.lower().translate(self.translator)
        
        # Filter stop words
        if delete_stop_words:
            pattern = self.stop_words_pattern
            for stop_word in self.stop_words:
                text = pattern.sub('', text)

        # Trim extra spaces
        text = ' '.join(text.split())

        return text

instance = Instance()
