from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class SearchRequest(BaseModel):
    query: str


class SearchResponse(BaseModel):
    articles: List[str]
    scores: List[float]
    version_used: str
    processing_time_ms: float


class ArticleData(BaseModel):
    id: str
    title: Optional[str] = None
    samples: List[str]


class IndexRequest(BaseModel):
    data: List[ArticleData]


class QueueStatusResponse(BaseModel):
    active_tasks: List[Dict[str, Any]] = []
    queued_tasks: List[Dict[str, Any]] = []
    failed_tasks: List[Dict[str, Any]] = []
    done_tasks: List[Dict[str, Any]] = []


class QueueDeleteResponse(BaseModel):
    status: str
    task_ids: List[str]
    data: QueueStatusResponse


class QueueRestartResponse(BaseModel):
    task_ids: List[str]
    data: QueueStatusResponse


class TaskStatusResponse(BaseModel):
    task_id: str
    parameters: Optional[Dict[str, Any]] = None
    status: Optional[str] = None
    progress: Optional[Dict[str, Any]] = None
    queued_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None


class TaskDeleteResponse(BaseModel):
    status: str
    task_id: str
    data: QueueStatusResponse


class VersionInfo(BaseModel):
    version_id: str
    version_name: str
    created_at: str
    is_active: bool
    is_pin: bool
    vectors_count: int
    articles_count: int


class VersionsResponse(BaseModel):
    versions: List[VersionInfo]
    total_versions: int
    pin_versions: int


class VersionActionRequest(BaseModel):
    action: str  # activate, rename, pin, unpin, delete
    name: Optional[str]


class HealthResponse(BaseModel):
    status: str


class ArticleSummary(BaseModel):
    article_id: str
    article_title: str
    samples_count: int
    synonyms_count: int


class ArticlesListResponse(BaseModel):
    version_id: str
    articles_count: int
    articles: List[ArticleSummary]


class ArticleDetailResponse(BaseModel):
    version_id: str
    article_id: str
    article_title: str
    samples_count: int
    samples: Dict[str, str]  # sample_id: text
    synonyms_count: int
    synonyms: Dict[str, str]  # synonym_id: text


class SampleDeleteRequest(BaseModel):
    ids: List[str]


class SampleDeleteResponse(BaseModel):
    status: str
    task_id: str
    version_id: str
    article_id: str
    article_title: str
    samples_number: int


class SamplesSynonymizeRequest(BaseModel):
    ids: List[str]


class SamplesSynonymizeResponse(BaseModel):
    status: str
    task_id: str
    version_id: str
    article_id: str
    article_title: str
    samples_number: int


class SynonymToSampleRequest(BaseModel):
    ids: List[str]


class SynonymToSampleResponse(BaseModel):
    status: str
    task_id: str
    version_id: str
    article_id: str
    article_title: str
    count: int


class GetStopWordsResponse(BaseModel):
    count: int
    stop_words: List[str]


class UpdateStopWordsRequest(BaseModel):
    stop_words: List[str]


class UpdateStopWordsResponse(BaseModel):
    status: str
    total_count: int
    added: list
    deleted: list


class LLMConfigRequest(BaseModel):
    llm_url: Optional[str] = None
    llm_model: Optional[str] = None
    llm_temperature: Optional[float] = None
    llm_top_p: Optional[float] = None
    llm_frequency_penalty: Optional[float] = None
    llm_repeat_penalty: Optional[float] = None
    llm_presence_penalty: Optional[float] = None
    llm_prompt: Optional[str] = None


class LLMConfigResponse(BaseModel):
    llm_url: str
    llm_model: str
    llm_temperature: float
    llm_top_p: float
    llm_frequency_penalty: float
    llm_repeat_penalty: float
    llm_presence_penalty: float
    llm_prompt: str


class ArticleDeleteResponse(BaseModel):
    status: str
    task_id: str
    version_id: str
    article_id: str
    article_title: str
    deleted_count: int
