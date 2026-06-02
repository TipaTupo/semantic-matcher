import os

from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings


class Config:

    def __init__(self):
        # Port
        self.port: str = os.getenv("HOST_PORT", "8123")

        # Data directory
        self.data_dir: Path = Path(os.getenv("DATA_DIR", ""))

        # Model loading config
        self.model_name: str = os.getenv("MODEL_NAME", "")
        self.model_path: str = f"/app/models/{self.model_name}"
        
        # Search config
        self.default_limit: int = int(os.getenv("DEFAULT_LIMIT", 10))
        self.similarity_threshold: float = float(os.getenv("SIMILARITY_THRESHOLD", 0.7))
        self.synonym_validation_threshold: float = float(os.getenv("SYNONYM_VALIDATION_THRESHOLD", 0.75))
        
        # Task config
        self.batch_size: int = int(os.getenv("BATCH_SIZE", 32))
        self.max_qsize: int = int(os.getenv("MAX_QUEUE_SIZE", 5))
        self.stale_lock_timeout_mins: int = int(os.getenv("STALE_LOCK_TIMEOUT_MINUTES", 10))
        
        # Retention policy
        self.max_versions: int = int(os.getenv("MAX_VERSIONS", 10))
        
        # LLM config
        self.reset_llm_params()
    

    def reset_llm_params(self) -> None:
        self.llm_url: str = os.getenv("LLM_URL", "")
        self.llm_api_key: str = os.getenv("LLM_API_KEY", "")
        self.llm_auth_token: str = os.getenv("LLM_AUTH_TOKEN", "")
        self.llm_model: str = os.getenv("LLM_MODEL", "")
        self.llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", 0.4))
        self.llm_top_p: float = float(os.getenv("LLM_TOP_P", 0.7))
        self.llm_frequency_penalty: float = float(os.getenv("LLM_FREQUENCY_PENALTY", 0.2))
        self.llm_repeat_penalty: float = float(os.getenv("LLM_REPEAT_PENALTY", 1.1))
        self.llm_presence_penalty: float = float(os.getenv("LLM_PRESENCE_PENALTY", 0.1))
        self.llm_prompt: str = """
Задача: сгенерировать 5 альтернативных формулировок одного и того же вопроса.
Каждая формулировка должна передавать тот же смысл и намерение (интент)
но отличаться словами, порядком слов или грамматической конструкцией.

Правила:
1. Сохраняй ключевые термины и собственные названия без изменений
2. Меняй глаголы на синонимы, переставляй части предложения, меняй активный/пассивный залог
3. Не добавляй новую информацию и не убирай существующую
4. Каждая формулировка — полноценный вопрос или утверждение-запрос
5. Не дублируй исходный вопрос дословно

Исходный вопрос: "{question}"

Верни результат строго в JSON-формате: {{"synonyms": ["вариант1", "вариант2", ...
        """.strip()

    def get_llm_config(self) -> dict:
        return {
            "llm_url": self.llm_url,
            "llm_model": self.llm_model,
            "llm_temperature": self.llm_temperature,
            "llm_top_p": self.llm_top_p,
            "llm_frequency_penalty": self.llm_frequency_penalty,
            "llm_repeat_penalty": self.llm_repeat_penalty,
            "llm_presence_penalty": self.llm_presence_penalty,
            "llm_prompt": self.llm_prompt,
        }
    

    def change_llm_params(self, **kwargs) -> None:
        for key, value in kwargs.items():
            if hasattr(self, key) and value is not None:
                setattr(self, key, value)


config = Config()
