import os
import sys

# Force global UTF-8 mode on Windows
if sys.platform == "win32" and os.environ.get("PYTHONUTF8") != "1":
    import subprocess

    os.environ["PYTHONUTF8"] = "1"
    result = subprocess.run([sys.executable] + sys.argv, env=os.environ)
    sys.exit(result.returncode)

import csv
import hashlib
import io
import math
import re
import shutil
import time
import uuid
import yaml
import logging
import threading
import asyncio
from pathlib import Path
from collections import defaultdict, Counter

# Fix for Windows: avoid "Event loop is closed" with ProactorEventLoop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import nest_asyncio

# Apply nest_asyncio only when needed (conflicts with uvicorn)
_NEST_ASYNCIO_APPLIED = False


def _ensure_nest_asyncio():
    global _NEST_ASYNCIO_APPLIED
    if not _NEST_ASYNCIO_APPLIED:
        nest_asyncio.apply()
        _NEST_ASYNCIO_APPLIED = True

# Force UTF-8 on stdout/stderr
try:
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )
except Exception:
    pass

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from llama_index.core import (
    PropertyGraphIndex,
    StorageContext,
    SimpleDirectoryReader,
    Settings,
    PromptTemplate,
    load_index_from_storage,
)
from llama_index.core.indices.property_graph.transformations import (
    SimpleLLMPathExtractor,
    ImplicitPathExtractor,
)
from llama_index.core.indices.property_graph import (
    LLMSynonymRetriever,
    VectorContextRetriever,
    CustomPGRetriever,
)
from llama_index.core.schema import NodeWithScore, TextNode, Document
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.ollama import OllamaEmbedding

from kwipu_config import (
    EMBED_MODEL,
    HASH_CACHE_FILE,
    KNOWLEDGE_DIR,
    MODEL_NAME,
    OLLAMA_BASE_URL,
    OLLAMA_TIMEOUT,
    QUERY_MAX_LENGTH,
    STORAGE_DIR,
    STORAGE_LOCK_FILE,
    STORAGE_LOCK_TIMEOUT,
    STORAGE_MANIFEST_FILE,
    validate_storage_layout,
)
from kwipu_storage import (
    InterProcessFileLock,
    _fsync_directory,
    atomic_write_json,
    atomic_write_json_locked,
    read_json,
    read_json_locked,
)

# Multilingual module
from lang_config import (
    tokenize,
    detect_language,
    extract_date_tokens,
    infer_relation,
    ALL_TEMPORAL_KEYWORDS,
    FALLBACK_RELATION,
)

# ==========================================
# CONFIGURATION
# ==========================================
WATCHER_DEBOUNCE_SECONDS = 5
WATCHER_VALID_EXTENSIONS = {".md", ".txt", ".pdf", ".docx"}
_WATCHER_EVENT_PRIORITY = {"created": 1, "modified": 2, "deleted": 3}

logging.basicConfig(level=logging.ERROR)


class EmbeddingModelMismatchError(RuntimeError):
    """Stored vectors were created with a different embedding model."""


class QueryValidationError(ValueError):
    """A knowledge-graph query is empty or exceeds the configured limit."""


class PersistedIndexUnavailableError(RuntimeError):
    """A read-only consumer could not load a complete persisted index."""


class StoragePublishError(RuntimeError):
    """A prepared storage generation could not be published safely."""


def validate_question(question: str) -> str:
    """Validate and normalize a query before any model or index initialization."""
    if not isinstance(question, str):
        raise QueryValidationError("Question must be a string.")
    normalized = question.strip()
    if not normalized:
        raise QueryValidationError("Question must not be empty.")
    if len(normalized) > QUERY_MAX_LENGTH:
        raise QueryValidationError(
            f"Question is too long: maximum length is {QUERY_MAX_LENGTH} characters."
        )
    return normalized


_TRIPLET_BULLET_RE = re.compile(r"^(?:(?:[-*+])|(?:\d+[.)]))\s*")
_TRIPLET_LABEL_RE = re.compile(r"^triplet\s*:\s*", re.IGNORECASE)
_TRIPLET_WRAPPERS = {"(": ")", "[": "]", "{": "}"}


def parse_llm_triplets(
    response_str: str, max_length: int = 128
) -> list[tuple[str, str, str]]:
    """Parse CSV triplets emitted by the LLM without changing their casing.

    Each non-empty line may have a Markdown bullet, a ``Triplet:`` label, and
    one outer pair of brackets. Quoted CSV fields may contain commas. Malformed
    rows, empty fields, and fields over the UTF-8 byte limit are discarded.
    Exact duplicate triplets are returned only once.
    """
    if not isinstance(response_str, str) or max_length <= 0:
        return []

    results: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for raw_line in response_str.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("```"):
            continue
        line = _TRIPLET_BULLET_RE.sub("", line, count=1).strip()
        line = _TRIPLET_LABEL_RE.sub("", line, count=1).strip()
        if len(line) >= 2 and line[0] == "`" and line[-1] == "`":
            line = line[1:-1].strip()
        if len(line) >= 2 and _TRIPLET_WRAPPERS.get(line[0]) == line[-1]:
            line = line[1:-1].strip()
        if not line:
            continue

        try:
            rows = list(csv.reader([line], skipinitialspace=True, strict=True))
        except csv.Error:
            continue
        if len(rows) != 1 or len(rows[0]) != 3:
            continue

        triplet = tuple(field.strip() for field in rows[0])
        if any(
            not field or len(field.encode("utf-8")) > max_length
            for field in triplet
        ):
            continue
        typed_triplet = (triplet[0], triplet[1], triplet[2])
        if typed_triplet in seen:
            continue
        seen.add(typed_triplet)
        results.append(typed_triplet)
    return results


def _init_llm(
    model_name: str = MODEL_NAME,
    embed_model: str = EMBED_MODEL,
    base_url: str = OLLAMA_BASE_URL,
    request_timeout: float = OLLAMA_TIMEOUT,
):
    """Initialize LLM and embedding model without doing network I/O."""
    Settings.llm = Ollama(
        model=model_name,
        request_timeout=request_timeout,
        base_url=base_url,
    )
    Settings.embed_model = OllamaEmbedding(
        model_name=embed_model,
        base_url=base_url,
        client_kwargs={"timeout": request_timeout},
    )

    # Chunking: large chunks to avoid splitting small notes
    Settings.chunk_size = 2048
    Settings.chunk_overlap = 256

# ==========================================
# SYSTEM PROMPT (multilingual)
# ==========================================
SYSTEM_PROMPT = (
    "You are the research assistant of Geode Graph. Your task is to answer questions "
    "based exclusively on the provided context from the user's knowledge base.\n\n"
    "RULES:\n"
    "1. Use ONLY information explicitly stated in the context below. Never invent or assume facts.\n"
    "2. Be concise but complete: include every relevant fact found in the context. "
    "Do not omit cited information that answers the question.\n"
    "3. If the answer involves multiple files, state which files are involved and "
    "quote the connecting fact from each.\n"
    "4. Always cite source file names in square brackets (e.g. [document.md]).\n"
    "5. When quoting actions or facts, preserve the original meaning. "
    "If a document says someone WILL do something, report it as a future action.\n"
    "6. When the user asks what to do BEFORE an event, include ALL tasks, preparations, "
    "and actions related to that event.\n"
    "7. If you cannot find the answer, say: 'I don't have enough information in your local files.'\n"
    "8. If unsure about a detail, omit it rather than guessing.\n"
    "9. ALWAYS respond in the same language as the user's question.\n\n"
    "CONTEXT:\n"
    "{context_str}\n\n"
    "QUESTION: {query_str}"
)

qa_template = PromptTemplate(SYSTEM_PROMPT)


# ==========================================
# SAFE PRINT (Rich-powered)
# ==========================================
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.status import Status

console = Console()


def safe_print(*args, **kwargs):
    try:
        console.print(*args, **kwargs)
    except Exception:
        try:
            print(*[str(a) for a in args])
        except Exception:
            pass


# ==========================================
# BM25 CHUNK RETRIEVER
# ==========================================
class BM25ChunkRetriever(CustomPGRetriever):
    """Multilingual BM25-like retriever that searches text chunks in the graph."""

    K1 = 1.5
    B = 0.75
    TOP_K = 8

    def init(self, **kwargs):
        self._idf_cache = {}
        self._avg_dl = 0
        self._doc_count = 0
        self._corpus_built = False

    def _build_corpus_stats(self, chunks: list[tuple[str, str]]):
        """Compute IDF and average document length."""
        if self._corpus_built:
            return

        self._doc_count = len(chunks)
        if self._doc_count == 0:
            return

        total_len = 0
        df = Counter()

        for _, text in chunks:
            tokens = tokenize(text)  # Usa tokenizer multilingue
            total_len += len(tokens)
            unique_tokens = set(tokens)
            for t in unique_tokens:
                df[t] += 1

        self._avg_dl = total_len / self._doc_count if self._doc_count > 0 else 1

        for token, freq in df.items():
            self._idf_cache[token] = math.log(
                1 + (self._doc_count - freq + 0.5) / (freq + 0.5)
            )

        self._corpus_built = True

    def _bm25_score(self, query_tokens: list[str], doc_text: str) -> float:
        """Compute BM25 score for a document."""
        doc_tokens = tokenize(doc_text)
        doc_len = len(doc_tokens)
        if doc_len == 0:
            return 0.0

        tf = Counter(doc_tokens)
        score = 0.0

        for qt in query_tokens:
            if qt not in self._idf_cache:
                continue
            term_freq = tf.get(qt, 0)
            if term_freq == 0:
                continue
            idf = self._idf_cache[qt]
            numerator = term_freq * (self.K1 + 1)
            denominator = term_freq + self.K1 * (
                1 - self.B + self.B * doc_len / self._avg_dl
            )
            score += idf * numerator / denominator

        return score

    def custom_retrieve(self, query_str: str) -> list[NodeWithScore]:
        """Search text chunks in the graph using BM25 scoring."""
        results = []
        chunks = []
        try:
            all_nodes = self.graph_store.graph.nodes
            for nid, data in all_nodes.items():
                text = getattr(data, "text", None)
                if text and len(text.strip()) > 20:
                    chunks.append((str(nid), text))
        except Exception:
            return results

        if not chunks:
            return results

        self._build_corpus_stats(chunks)

        query_tokens = tokenize(query_str)
        if not query_tokens:
            return results

        scored = []
        for nid, text in chunks:
            score = self._bm25_score(query_tokens, text)
            if score > 0:
                scored.append((nid, text, score))

        scored.sort(key=lambda x: x[2], reverse=True)
        for nid, text, score in scored[: self.TOP_K]:
            results.append(
                NodeWithScore(node=TextNode(text=text, id_=nid), score=score)
            )

        return results


# ==========================================
# TEMPORAL METADATA RETRIEVER
# ==========================================
class TemporalMetadataRetriever(CustomPGRetriever):
    """Multilingual retriever for temporal queries and events."""

    TOP_K = 8

    def init(self, **kwargs):
        pass

    def custom_retrieve(self, query_str: str) -> list[NodeWithScore]:
        """Search for relevant documents based on dates, tags and metadata in any language."""
        results = []

        query_date_tokens = extract_date_tokens(query_str)
        query_tokens = tokenize(query_str)

        is_temporal_query = bool(query_date_tokens) or bool(
            ALL_TEMPORAL_KEYWORDS.intersection(set(query_tokens))
        )

        if not is_temporal_query and not query_tokens:
            return results

        try:
            all_nodes = self.graph_store.graph.nodes
        except Exception:
            return results

        for nid, data in all_nodes.items():
            text = getattr(data, "text", None)
            if not text or len(text.strip()) < 20:
                continue

            score = 0.0
            text_lower = text.lower()

            # 1. Date matching
            for dt in query_date_tokens:
                if dt in text_lower:
                    score += 3.0

            # 2. Temporal keyword matching (all languages)
            for kw in ALL_TEMPORAL_KEYWORDS:
                if kw in query_tokens and kw in tokenize(text):
                    score += 2.0

            # 3. Tag/metadata matching
            if "tags:" in text_lower or "data:" in text_lower or "date:" in text_lower:
                for qt in query_tokens:
                    if qt in text_lower:
                        score += 1.0

            # 4. Proper name matching
            for qt in query_tokens:
                if len(qt) > 4 and qt in text_lower:
                    if qt[0:1].upper() + qt[1:] in text:
                        score += 1.5

            if score > 0:
                results.append(
                    NodeWithScore(node=TextNode(text=text, id_=str(nid)), score=score)
                )

        results.sort(key=lambda x: x.score, reverse=True)
        return results[: self.TOP_K]


# ==========================================
# READ-WRITE LOCK
# ==========================================
class ReadWriteLock:
    """Writer-preference lock with concurrent readers and exclusive writers."""

    def __init__(self):
        self._condition = threading.Condition()
        self._readers = 0
        self._writer_active = False
        self._waiting_writers = 0

    def acquire_read(self):
        with self._condition:
            while self._writer_active or self._waiting_writers > 0:
                self._condition.wait()
            self._readers += 1

    def release_read(self):
        with self._condition:
            if self._readers <= 0:
                raise RuntimeError("Cannot release an unacquired read lock.")
            self._readers -= 1
            if self._readers == 0:
                self._condition.notify_all()

    def acquire_write(self):
        with self._condition:
            self._waiting_writers += 1
            try:
                while self._writer_active or self._readers > 0:
                    self._condition.wait()
                self._writer_active = True
            finally:
                self._waiting_writers -= 1

    def release_write(self):
        with self._condition:
            if not self._writer_active:
                raise RuntimeError("Cannot release an unacquired write lock.")
            self._writer_active = False
            self._condition.notify_all()


# ==========================================
# OBSIDIAN PRE-PROCESSING (multilingual)
# ==========================================
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Extract YAML frontmatter and return (metadata_dict, body_text).

    Handles BOM and leading whitespace that some editors add on Windows.
    """
    # Strip BOM and leading whitespace before matching
    text_clean = text.lstrip("\ufeff").lstrip()
    match = _FRONTMATTER_RE.match(text_clean)
    if not match:
        return {}, text
    try:
        meta = yaml.safe_load(match.group(1))
        if not isinstance(meta, dict):
            meta = {}
    except yaml.YAMLError:
        meta = {}
    # Calculate body offset relative to original text
    offset_in_clean = match.end()
    # Find where text_clean starts in original text
    prefix_len = len(text) - len(text.lstrip("\ufeff").lstrip())
    body = text[prefix_len + offset_in_clean:]
    return meta, body


def extract_wikilink_triples(file_path: str, text: str) -> list[tuple[str, str, str]]:
    """Extract structured triples from Obsidian [[wikilinks]] with multilingual inference."""
    filename = Path(file_path).stem
    triples = []
    seen = set()

    for match in _WIKILINK_RE.finditer(text):
        target = match.group(1).strip()
        if not target:
            continue

        pair_key = (filename.lower(), target.lower())
        if pair_key in seen:
            continue
        seen.add(pair_key)

        line_start = text.rfind("\n", 0, match.start()) + 1
        line_end = text.find("\n", match.end())
        if line_end == -1:
            line_end = len(text)
        line = text[line_start:line_end].strip()

        # Use multilingual inference
        relation = infer_relation(line, filename, target)
        triples.append((filename, relation, target))

    return triples


def extract_frontmatter_triples(
    file_path: str, metadata: dict
) -> list[tuple[str, str, str]]:
    """Generate structured triples from YAML frontmatter.

    Frontmatter keys are mapped to relations across supported languages.
    """
    filename = Path(file_path).stem
    triples = []

    # Frontmatter key -> relation mapping (multilingual)
    key_relations = {
        # Italian
        "ruolo": "Has role",
        "organizzazione": "Belongs to",
        "progetto": "Participates in",
        "stato": "Has status",
        "responsabile": "Has responsible",
        "licenza": "Has license",
        "location": "Located at",
        # English
        "role": "Has role",
        "organization": "Belongs to",
        "project": "Participates in",
        "status": "Has status",
        "responsible": "Has responsible",
        "license": "Has license",
        # French
        "organisation": "Belongs to",
        "projet": "Participates in",
        "statut": "Has status",
        "lieu": "Located at",
        # German
        "rolle": "Has role",
        "projekt": "Participates in",
        "standort": "Located at",
        # Spanish
        "rol": "Has role",
        "organizacion": "Belongs to",
        "proyecto": "Participates in",
        "estado": "Has status",
        "ubicacion": "Located at",
        # Portuguese
        "funcao": "Has role",
        "organizacao": "Belongs to",
        "projeto": "Participates in",
        "localizacao": "Located at",
    }

    for key, relation in key_relations.items():
        value = metadata.get(key)
        if value and isinstance(value, str):
            triples.append((filename, relation, value))

    # Tags (universal key)
    tags = metadata.get("tags", [])
    if isinstance(tags, list):
        for tag in tags:
            if isinstance(tag, str):
                triples.append((filename, "Has tag", tag))

    # Participants (multilingual keys)
    for key in ("partecipanti", "participants", "teilnehmer", "participantes"):
        partecipanti = metadata.get(key, [])
        if isinstance(partecipanti, list):
            for p in partecipanti:
                if isinstance(p, str):
                    triples.append((filename, "Has participant", p))

    # Date (multilingual keys)
    for key in ("data", "date", "datum", "fecha"):
        data = metadata.get(key)
        if data:
            triples.append((filename, "Has date", str(data)))
            break

    # Budget (universal)
    budget = metadata.get("budget")
    if budget:
        triples.append((filename, "Has budget", f"{budget}"))

    # Duration (multilingual keys)
    for key in ("durata_mesi", "duration_months", "duree_mois", "dauer_monate",
                "duracion_meses", "duracao_meses"):
        durata = metadata.get(key)
        if durata:
            triples.append((filename, "Has duration", f"{durata} months"))
            break

    return triples


def enrich_documents(
    documents: list[Document],
) -> tuple[list[Document], list[tuple[str, str, str]]]:
    """Pre-process documents: extract frontmatter, wikilinks and generate structured triples."""
    all_triples = []
    enriched_docs = []

    for doc in documents:
        text = doc.text
        file_path = doc.metadata.get("file_path", doc.id_)

        metadata, body = parse_frontmatter(text)

        for key, value in metadata.items():
            if isinstance(value, (str, int, float)):
                doc.metadata[f"fm_{key}"] = str(value)
            elif isinstance(value, list):
                doc.metadata[f"fm_{key}"] = ", ".join(str(v) for v in value)

        wikilink_triples = extract_wikilink_triples(file_path, body)
        all_triples.extend(wikilink_triples)

        fm_triples = extract_frontmatter_triples(file_path, metadata)
        all_triples.extend(fm_triples)

        enriched_docs.append(doc)

    all_triples = _deduplicate_triples(all_triples)
    return enriched_docs, all_triples


def _deduplicate_triples(
    triples: list[tuple[str, str, str]],
) -> list[tuple[str, str, str]]:
    """Remove duplicate triples (case-insensitive)."""
    seen = set()
    unique = []
    for s, r, o in triples:
        key = (s.lower().strip(), r.lower().strip(), o.lower().strip())
        if key not in seen:
            seen.add(key)
            unique.append((s.strip(), r.strip(), o.strip()))
    return unique


# ==========================================
# GRAPH RAG ENGINE
# ==========================================
class WritHerGraphRAG:
    def __init__(
        self,
        fast_mode: bool = False,
        model_name: str = MODEL_NAME,
        embed_model: str = EMBED_MODEL,
        build_if_missing: bool = True,
    ) -> None:
        self.index = None
        self._rw_lock = ReadWriteLock()
        self._async_query_lock = asyncio.Lock()
        self._query_engine = None
        self._retrievers_dirty = True
        self._fast_mode = fast_mode
        self._build_if_missing = build_if_missing
        self._storage_revision: str | None = None
        self.model_name = model_name
        self.embed_model = embed_model
        # Validate every managed generation before the first mkdir. The same
        # helper runs at import time and again here so patched/runtime paths
        # cannot bypass the source-vault safety invariant.
        self._storage_paths()
        os.makedirs(KNOWLEDGE_DIR, exist_ok=True)
        self.load_or_build_index()

    @staticmethod
    def _storage_paths() -> tuple[Path, Path, Path]:
        return validate_storage_layout(KNOWLEDGE_DIR, STORAGE_DIR)

    @staticmethod
    def _storage_lock() -> InterProcessFileLock:
        return InterProcessFileLock(STORAGE_LOCK_FILE, STORAGE_LOCK_TIMEOUT)

    @staticmethod
    def _has_persisted_storage() -> bool:
        if not os.path.isdir(STORAGE_DIR):
            return False
        metadata_only = {
            ".file_hashes.json",
            ".kwipu_meta.json",
            ".kwipu_restore_backup",
        }
        return any(name not in metadata_only for name in os.listdir(STORAGE_DIR))

    @staticmethod
    def _read_storage_manifest_unlocked() -> dict | None:
        manifest_path = Path(STORAGE_MANIFEST_FILE)
        if not manifest_path.exists():
            return None

        invalid = object()
        manifest = read_json(manifest_path, default=invalid)
        if isinstance(manifest, dict):
            return manifest
        # A writer swaps the active directory before a lock-free reader can
        # finish this probe. Treat that brief absence as an in-progress commit
        # instead of interrupting an otherwise usable in-memory index.
        if not manifest_path.exists():
            return None
        manifest = read_json(manifest_path, default=invalid)
        if isinstance(manifest, dict):
            return manifest
        if not manifest_path.exists():
            return None
        raise PersistedIndexUnavailableError(
            "Persisted knowledge-graph manifest is invalid or unreadable."
        )

    @classmethod
    def _read_storage_revision_unlocked(cls) -> str | None:
        manifest = cls._read_storage_manifest_unlocked()
        revision = manifest.get("storage_revision") if manifest else None
        return revision if isinstance(revision, str) and revision else None

    def _load_index_unlocked(self):
        """Load the latest persisted index. Caller owns both write locks."""
        manifest = self._check_storage_compatibility()
        safe_print("Loading knowledge graph from local storage...")
        storage_context = StorageContext.from_defaults(persist_dir=STORAGE_DIR)
        self.index = load_index_from_storage(storage_context)
        revision = manifest.get("storage_revision") if manifest else None
        self._storage_revision = (
            revision if isinstance(revision, str) and revision else None
        )
        safe_print("Graph loaded successfully.")

    def _load_empty_generation_unlocked(self) -> bool:
        """Load the revision of a committed generation that has no index."""
        current, _, _ = self._storage_paths()
        if not self._generation_is_valid(current):
            return False
        manifest = self._read_storage_manifest_unlocked()
        if not isinstance(manifest, dict) or manifest.get("has_index") is not False:
            return False
        self._check_storage_compatibility()
        self.index = None
        revision = manifest.get("storage_revision")
        self._storage_revision = (
            revision if isinstance(revision, str) and revision else None
        )
        return True

    def load_or_build_index(self):
        """Load storage, or build it only when this instance is a writer."""
        self._rw_lock.acquire_write()
        try:
            with self._storage_lock():
                self._recover_storage_unlocked()
                if self._load_empty_generation_unlocked():
                    pass
                elif not self._has_persisted_storage():
                    if not self._build_if_missing:
                        raise PersistedIndexUnavailableError(
                            "Persisted knowledge-graph index is not available."
                        )
                    self._build_index_unlocked()
                else:
                    try:
                        self._load_index_unlocked()
                    except EmbeddingModelMismatchError:
                        raise
                    except Exception as exc:
                        if not self._build_if_missing:
                            raise PersistedIndexUnavailableError(
                                "Persisted knowledge-graph index could not be loaded."
                            ) from exc
                        safe_print(f"Load error: {exc}. Rebuilding index...")
                        self._build_index_unlocked()
                self._query_engine = None
                self._retrievers_dirty = True
        finally:
            self._rw_lock.release_write()

    def _check_storage_compatibility(self) -> dict | None:
        """Raise a dedicated error if stored and configured embeddings differ."""
        meta = self._read_storage_manifest_unlocked()
        if not isinstance(meta, dict):
            return None  # Legacy storage without a readable manifest

        stored_embed = meta.get("embed_model", "")
        if stored_embed and stored_embed != self.embed_model:
            raise EmbeddingModelMismatchError(
                f"Embedding model mismatch: storage was built with '{stored_embed}' "
                f"but current config uses '{self.embed_model}'. "
                f"Delete '{STORAGE_DIR}' to rebuild it, or restore the previous model."
            )

        # An LLM change is safe because it does not alter stored vectors.
        stored_llm = meta.get("llm_model", "")
        if stored_llm and stored_llm != self.model_name:
            safe_print(
                f"[dim]Note: graph was built with '{stored_llm}', "
                f"now using '{self.model_name}' for queries.[/dim]"
            )
        return meta

    @staticmethod
    def _generation_manifest_path(directory: Path) -> Path:
        return directory / Path(STORAGE_MANIFEST_FILE).name

    @staticmethod
    def _generation_hash_path(directory: Path) -> Path:
        return directory / Path(HASH_CACHE_FILE).name

    @classmethod
    def _generation_is_valid(cls, directory: Path) -> bool:
        """Return whether a directory is a complete committed/legacy generation."""
        if not directory.is_dir():
            return False
        metadata_only = {
            Path(HASH_CACHE_FILE).name,
            Path(STORAGE_MANIFEST_FILE).name,
            ".kwipu_restore_backup",
        }
        manifest_path = cls._generation_manifest_path(directory)
        if manifest_path.exists():
            manifest = read_json(manifest_path, default=None)
            if not (
                isinstance(manifest, dict)
                and isinstance(manifest.get("storage_revision"), str)
                and manifest["storage_revision"]
            ):
                return False

            has_index = manifest.get("has_index")
            if has_index is False:
                return isinstance(
                    read_json(cls._generation_hash_path(directory), default=None),
                    dict,
                )
            if has_index not in (True, None):
                return False
            try:
                return any(
                    item.name not in metadata_only for item in directory.iterdir()
                )
            except OSError:
                return False

        # Legacy generations have no manifest but must contain index payload.
        try:
            return any(item.name not in metadata_only for item in directory.iterdir())
        except OSError:
            return False

    @classmethod
    def _remove_generation_unlocked(cls, directory: Path) -> None:
        """Remove only a validated managed generation, never the source vault."""
        current, staging, backup = cls._storage_paths()
        directory = directory.resolve(strict=False)
        if directory not in {current, staging, backup}:
            raise ValueError(f"Refusing to remove unmanaged path '{directory}'")
        if not directory.exists() and not directory.is_symlink():
            return
        is_junction = getattr(directory, "is_junction", lambda: False)()
        if directory.is_symlink() or is_junction or not directory.is_dir():
            if is_junction and directory.is_dir():
                directory.rmdir()
            else:
                directory.unlink(missing_ok=True)
            return
        shutil.rmtree(directory)

    @classmethod
    def _recover_storage_unlocked(cls) -> None:
        """Resolve deterministic crash states while holding the storage lock."""
        current, staging, backup = cls._storage_paths()
        current_valid = cls._generation_is_valid(current)
        backup_valid = cls._generation_is_valid(backup)
        backup_restore_marker = backup / ".kwipu_restore_backup"

        # A marker in backup means publication never cleared its rollback
        # intent. Prefer the last known-good generation even if the candidate
        # currently occupying ``current`` is structurally valid.
        if backup_restore_marker.is_file():
            if not backup_valid:
                raise PersistedIndexUnavailableError(
                    "Persisted rollback backup is invalid or incomplete."
                )
            if current.exists():
                cls._remove_generation_unlocked(current)
            os.replace(backup, current)
            (current / backup_restore_marker.name).unlink(missing_ok=True)
            _fsync_directory(current)
            _fsync_directory(current.parent)
            cls._remove_generation_unlocked(staging)
            return

        if current.exists():
            if current_valid:
                cls._remove_generation_unlocked(backup)
            elif backup_valid:
                cls._remove_generation_unlocked(current)
                os.replace(backup, current)
                _fsync_directory(current.parent)
            elif backup.exists():
                cls._remove_generation_unlocked(backup)
        elif backup.exists():
            if backup_valid:
                os.replace(backup, current)
                _fsync_directory(current.parent)
            else:
                cls._remove_generation_unlocked(backup)

        # A staging directory is never committed: only the staging->current
        # rename commits it. Therefore every surviving staging path is stale.
        cls._remove_generation_unlocked(staging)

    def _write_staging_manifest_unlocked(
        self, staging: Path, *, has_index: bool
    ) -> str:
        """Write the staging commit marker without changing in-memory revision."""
        revision = str(uuid.uuid4())
        atomic_write_json(
            self._generation_manifest_path(staging),
            {
                "embed_model": self.embed_model,
                "llm_model": self.model_name,
                "storage_revision": revision,
                "has_index": has_index,
                "version": "1.0",
            },
        )
        return revision

    @staticmethod
    def _fsync_generation_unlocked(directory: Path) -> None:
        """Flush every prepared regular file before writing the manifest marker."""
        for path in directory.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            with path.open("r+b") as handle:
                os.fsync(handle.fileno())
        _fsync_directory(directory)

    def _commit_staging_unlocked(self, staging: Path, revision: str) -> None:
        """Durably publish staging and roll back if either swap cannot commit."""
        current, expected_staging, backup = self._storage_paths()
        if staging.resolve(strict=False) != expected_staging:
            raise ValueError("Unexpected staging path")
        if not self._generation_is_valid(staging):
            raise StoragePublishError("Staging generation is incomplete")
        if backup.exists():
            raise StoragePublishError(
                "Storage backup must be recovered before publishing a generation"
            )

        moved_current = False
        published_current = False
        backup_restore_marker = backup / ".kwipu_restore_backup"
        try:
            if current.exists():
                os.replace(current, backup)
                moved_current = True
                _fsync_directory(current.parent)
                # Until publication and its directory flush complete, backup
                # remains authoritative. Recovery uses this durable intent if
                # rollback itself is interrupted or fails.
                atomic_write_json(
                    backup_restore_marker,
                    {"restore_backup": True, "version": "1.0"},
                )
            os.replace(staging, current)
            published_current = True
            # The rename is not committed durably until its parent directory is
            # flushed. Keep backup and the old in-memory revision until then.
            _fsync_directory(current.parent)
            if moved_current:
                backup_restore_marker.unlink(missing_ok=True)
                _fsync_directory(backup)
        except BaseException:
            if published_current and current.exists():
                try:
                    os.replace(current, staging)
                    published_current = False
                except OSError:
                    # The durable marker keeps backup authoritative when the
                    # candidate cannot be moved back to staging.
                    pass
            if moved_current and not current.exists() and backup.exists():
                try:
                    os.replace(backup, current)
                    (current / backup_restore_marker.name).unlink(missing_ok=True)
                    _fsync_directory(current)
                    _fsync_directory(current.parent)
                except OSError:
                    # The marked backup remains recoverable on the next lock acquisition.
                    pass
            raise

        # Only the durable staging->current rename and cleared rollback intent
        # advance the in-memory revision.
        self._storage_revision = revision
        try:
            self._remove_generation_unlocked(backup)
        except OSError:
            # A post-commit cleanup failure is recovered on the next transaction.
            pass

    def _publish_generation_unlocked(self, index) -> str:
        """Persist a complete generation in staging, then publish it by swap."""
        current, staging, _ = self._storage_paths()
        try:
            self._remove_generation_unlocked(staging)
            staging.mkdir(parents=False, exist_ok=False)

            if index is not None:
                index.storage_context.persist(persist_dir=str(staging))

            hashes = read_json(
                self._generation_hash_path(current), default={}
            )
            if not isinstance(hashes, dict):
                hashes = {}
            atomic_write_json(self._generation_hash_path(staging), hashes)
            self._fsync_generation_unlocked(staging)
            revision = self._write_staging_manifest_unlocked(
                staging, has_index=index is not None
            )
            self._commit_staging_unlocked(staging, revision)
            return revision
        except BaseException as exc:
            try:
                self._remove_generation_unlocked(staging)
            except OSError:
                pass
            if not isinstance(exc, Exception):
                raise
            if isinstance(exc, StoragePublishError):
                raise
            raise StoragePublishError(
                "Storage generation could not be published; the previous generation "
                "was preserved."
            ) from exc

    def build_index(self):
        """Rebuild the graph under one local and inter-process transaction."""
        self._rw_lock.acquire_write()
        try:
            with self._storage_lock():
                self._recover_storage_unlocked()
                self._build_index_unlocked()
                self._retrievers_dirty = True
        finally:
            self._rw_lock.release_write()

    def insert_document(self, file_path):
        """Insert one new document after reloading the latest persisted index."""
        file_path = str(Path(file_path).resolve())
        self._rw_lock.acquire_write()
        try:
            with self._storage_lock():
                self._recover_storage_unlocked()
                try:
                    # Another process may have persisted changes since this instance loaded.
                    if self._has_persisted_storage():
                        self._load_index_unlocked()
                    elif not self.index:
                        self._build_index_unlocked()
                        self._retrievers_dirty = True
                        return

                    reader = SimpleDirectoryReader(
                        input_files=[file_path], filename_as_id=True
                    )
                    docs = reader.load_data()
                    if docs:
                        enriched_docs, structural_triples = enrich_documents(docs)
                        for doc in enriched_docs:
                            safe_print(
                                f"Incremental insert: {os.path.basename(file_path)}..."
                            )
                            self.index.insert(doc)
                        self._inject_structural_triples(
                            structural_triples, index=self.index
                        )
                        self._publish_generation_unlocked(self.index)
                        safe_print("Document added to graph successfully.")
                        self._retrievers_dirty = True
                except EmbeddingModelMismatchError:
                    raise
                except StoragePublishError as exc:
                    safe_print(f"Incremental insert publish error: {exc}")
                    self._recover_storage_unlocked()
                    if self._has_persisted_storage():
                        self._load_index_unlocked()
                    else:
                        self.index = None
                        self._storage_revision = self._read_storage_revision_unlocked()
                    self._query_engine = None
                    self._retrievers_dirty = True
                    # The caller must not checkpoint this source as indexed when
                    # publication failed. Recovery above restores the active
                    # in-memory generation; propagating preserves watcher state.
                    raise
                except Exception as exc:
                    safe_print(f"Incremental insert error: {exc}. Full rebuild...")
                    self._build_index_unlocked()
                    self._retrievers_dirty = True
        finally:
            self._rw_lock.release_write()

    def update_document(self, file_path):
        """Compatibility API: modifications require a full rebuild for correctness."""
        safe_print(f"Modified file detected: {os.path.basename(file_path)}.")
        self.build_index()

    def _inject_structural_triples(
        self, triples: list[tuple[str, str, str]], *, index=None
    ):
        """Inject pre-extracted triples into the selected property graph."""
        target_index = self.index if index is None else index
        if not target_index or not triples:
            return
        graph_store = target_index.property_graph_store
        for subj, rel, obj in triples:
            try:
                graph_store.upsert_triplet(subj, rel, obj)
            except Exception:
                pass

    def _build_index_unlocked(self):
        """Analyze files and build the graph."""
        safe_print(f"Scanning documents in '{KNOWLEDGE_DIR}'...")

        try:
            reader = SimpleDirectoryReader(
                KNOWLEDGE_DIR, recursive=True, filename_as_id=True
            )
            documents = reader.load_data()
        except ValueError:
            documents = []

        if not documents:
            safe_print("No files found. Waiting for documents...")
            self._publish_generation_unlocked(None)
            self.index = None
            self._query_engine = None
            return

        # Time estimate for user feedback
        n_docs = len(documents)
        safe_print(f"Found {n_docs} documents.")
        if n_docs > 10:
            est_minutes = max(1, n_docs // 3)
            safe_print(
                f"  ⏱  Estimate: {est_minutes}-{est_minutes * 3} minutes "
                f"(depends on model and hardware)."
            )
            safe_print(
                "  💡 Tip: first build is the slowest. "
                "Subsequent runs will be incremental."
            )

        safe_print("Pre-processing: extracting wikilinks and frontmatter...")
        enriched_docs, structural_triples = enrich_documents(documents)
        safe_print(
            f"  -> {len(structural_triples)} structural relations extracted."
        )

        build_start = time.time()
        safe_print(
            f"LLM extraction and graph construction with {self.model_name}..."
        )

        kg_extractors = [
            SimpleLLMPathExtractor(
                llm=Settings.llm,
                extract_prompt=(
                    "From the text below, extract up to {max_paths_per_chunk} knowledge triplets.\n"
                    "Each triplet must be on its own line in the format: entity1, relation, entity2\n"
                    "RULES:\n"
                    "- Each entity must be a single proper noun (person, organization, place, technology, dataset)\n"
                    "- Do NOT combine multiple concepts into one entity\n"
                    "- Extract ALL person names as separate entities\n"
                    "- Relations should be short verb phrases\n\n"
                    "Text: {text}\n"
                    "Triplets:\n"
                ),
                parse_fn=parse_llm_triplets,
                num_workers=1,
                max_paths_per_chunk=20,
            ),
            ImplicitPathExtractor(),
        ]

        new_index = PropertyGraphIndex.from_documents(
            enriched_docs, kg_extractors=kg_extractors, show_progress=False
        )

        safe_print("Injecting structural relations into graph...")
        self._inject_structural_triples(structural_triples, index=new_index)

        # The candidate remains detached from the active in-memory and on-disk
        # generations until the complete staging directory is committed.
        self._publish_generation_unlocked(new_index)
        self.index = new_index
        build_elapsed = time.time() - build_start
        minutes = int(build_elapsed // 60)
        seconds = int(build_elapsed % 60)
        safe_print(
            f"Graph built and saved successfully. "
            f"(Build time: {minutes}m {seconds}s)"
        )

    def _build_retrievers(self):
        """Build retrievers and query engine.

        Fast mode: vector + BM25 + temporal only (no LLM call per query).
        Normal mode: adds LLM synonym retriever.
        """
        if not self.index:
            self._query_engine = None
            return

        sub_retrievers = []

        # Synonym retriever: normal mode only (costs one LLM call per query)
        if not self._fast_mode:
            synonym_retriever = LLMSynonymRetriever(
                self.index.property_graph_store,
                llm=Settings.llm,
                include_text=True,
                synonym_prompt=(
                    "Given the query below, generate synonyms or related keywords up to {max_keywords} in total.\n"
                    "Include: original names, names with titles (Prof., Dott., Dott.ssa, Dr., Ing., Dra.), "
                    "abbreviations, related project names, and multilingual variants.\n"
                    "Provide all synonyms/keywords separated by '^' symbols: 'keyword1^keyword2^...'\n"
                    "Result must be one line, separated by '^' symbols.\n"
                    "----\n"
                    "QUERY: {query_str}\n"
                    "----\n"
                    "KEYWORDS: "
                ),
                max_keywords=15,
                path_depth=3,
            )
            sub_retrievers.append(synonym_retriever)

        # These retrievers don't use the LLM, always active
        vector_retriever = VectorContextRetriever(
            self.index.property_graph_store,
            vector_store=self.index.vector_store,
            include_text=True,
            similarity_top_k=20,
            embed_model=Settings.embed_model,
            path_depth=3,
        )
        sub_retrievers.append(vector_retriever)

        bm25_retriever = BM25ChunkRetriever(self.index.property_graph_store)
        sub_retrievers.append(bm25_retriever)

        temporal_retriever = TemporalMetadataRetriever(self.index.property_graph_store)
        sub_retrievers.append(temporal_retriever)

        self._query_engine = self.index.as_query_engine(
            text_qa_template=qa_template,
            sub_retrievers=sub_retrievers,
        )
        self._retrievers_dirty = False

    def _reload_if_storage_changed(self) -> None:
        """Reload a newly committed storage revision before serving a query.

        The first manifest read is intentionally lock-free and treats a missing
        manifest as an in-progress external build. A changed revision is then
        confirmed while holding the local write lock followed by the canonical
        inter-process lock, matching the writer lock order.
        """
        persisted_revision = self._read_storage_revision_unlocked()
        if (
            persisted_revision is None
            or persisted_revision == self._storage_revision
        ):
            return

        self._rw_lock.acquire_write()
        try:
            with self._storage_lock():
                self._recover_storage_unlocked()
                persisted_revision = self._read_storage_revision_unlocked()
                if (
                    persisted_revision is None
                    or persisted_revision == self._storage_revision
                ):
                    return
                if not self._has_persisted_storage():
                    self.index = None
                    self._storage_revision = persisted_revision
                else:
                    try:
                        self._load_index_unlocked()
                    except EmbeddingModelMismatchError:
                        raise
                    except Exception as exc:
                        raise PersistedIndexUnavailableError(
                            "Updated knowledge-graph index could not be loaded."
                        ) from exc
                self._query_engine = None
                self._retrievers_dirty = True
        finally:
            self._rw_lock.release_write()

    def _no_index_result(self) -> str:
        if not self._build_if_missing:
            raise PersistedIndexUnavailableError(
                "Persisted knowledge-graph index is not available."
            )
        return "No index available. Add files to the knowledge_base folder."

    def ask_with_revision(self, question):
        """Query a stable in-memory generation and return its storage revision."""
        question = validate_question(question)
        self._reload_if_storage_changed()

        while True:
            self._rw_lock.acquire_read()
            try:
                if not self.index:
                    return self._no_index_result(), self._storage_revision
                if not self._retrievers_dirty and self._query_engine is not None:
                    response = self._query_engine.query(question)
                    return response, self._storage_revision
            finally:
                self._rw_lock.release_read()

            # A concurrent revision reload may invalidate retrievers between
            # loop iterations. Recheck under the write lock, rebuild the
            # current generation, then loop until query dispatch owns a read
            # lock on a clean engine.
            self._rw_lock.acquire_write()
            try:
                if not self.index:
                    return self._no_index_result(), self._storage_revision
                if self._retrievers_dirty or self._query_engine is None:
                    self._build_retrievers()
            finally:
                self._rw_lock.release_write()

    def _prepare_async_query_dispatch(self):
        """Prepare one stable async dispatch while running in a worker thread.

        A clean query engine is returned with the local read lock held. The
        async caller owns releasing that lock after model I/O or cancellation.
        """
        self._reload_if_storage_changed()

        while True:
            keep_read_lock = False
            self._rw_lock.acquire_read()
            try:
                if not self.index:
                    return None, self._no_index_result(), self._storage_revision
                if not self._retrievers_dirty and self._query_engine is not None:
                    keep_read_lock = True
                    return self._query_engine, None, self._storage_revision
            finally:
                if not keep_read_lock:
                    self._rw_lock.release_read()

            self._rw_lock.acquire_write()
            try:
                if not self.index:
                    return None, self._no_index_result(), self._storage_revision
                if self._retrievers_dirty or self._query_engine is None:
                    self._build_retrievers()
            finally:
                self._rw_lock.release_write()

    async def ask_with_revision_async(self, question):
        """Asynchronously query one stable generation on the caller's event loop."""
        question = validate_question(question)

        # Cached Ollama clients must remain on Uvicorn's persistent event loop.
        # Blocking storage and threading-lock work runs in a worker, while this
        # lock serializes use of the cached async query engine.
        async with self._async_query_lock:
            prepare_task = asyncio.create_task(
                asyncio.to_thread(self._prepare_async_query_dispatch)
            )
            try:
                query_engine, no_index_result, revision = await asyncio.shield(
                    prepare_task
                )
            except asyncio.CancelledError:
                # asyncio.to_thread cannot stop an in-flight worker. Wait for
                # preparation to finish and release any read lock it returned
                # before propagating cancellation, preventing a leaked lock.
                try:
                    prepared = await prepare_task
                except Exception:
                    pass
                else:
                    if prepared[0] is not None:
                        self._rw_lock.release_read()
                raise

            if query_engine is None:
                return no_index_result, revision

            try:
                response = await query_engine.aquery(question)
                return response, revision
            finally:
                self._rw_lock.release_read()

    def ask(self, question):
        """Validate, refresh persisted storage, and query a stable generation."""
        response, _ = self.ask_with_revision(question)
        return response


# ==========================================
# REAL-TIME FILE MONITORING (with persistent content-hash)
# ==========================================
_HASH_CACHE_FILE = HASH_CACHE_FILE


def _file_content_hash(path: str) -> str | None:
    """Compute MD5 hash of file contents. Returns None if file doesn't exist."""
    try:
        with open(path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except (OSError, IOError):
        return None


def _load_hash_cache() -> dict[str, str]:
    """Load the hash cache while holding the cross-process storage lock."""
    data = read_json_locked(
        _HASH_CACHE_FILE,
        STORAGE_LOCK_FILE,
        STORAGE_LOCK_TIMEOUT,
        default={},
    )
    return data if isinstance(data, dict) else {}


def _save_hash_cache(hashes: dict[str, str]):
    """Atomically save the hash cache under the cross-process storage lock."""
    atomic_write_json_locked(
        _HASH_CACHE_FILE,
        hashes,
        STORAGE_LOCK_FILE,
        STORAGE_LOCK_TIMEOUT,
    )


class FileWatcher(FileSystemEventHandler):
    def __init__(self, rag_system):
        self.rag_system = rag_system
        self._lock = threading.Lock()
        self._pending_events: dict[str, tuple[str, float]] = {}
        self._timer = None
        self._file_hashes: dict[str, str] = _load_hash_cache()
        self._refresh_hashes()

    def _refresh_hashes(self):
        """Refresh hashes for all current files in the knowledge base."""
        kb_path = Path(KNOWLEDGE_DIR)
        if not kb_path.exists():
            return

        current_files = set()
        for ext in WATCHER_VALID_EXTENSIONS:
            for f in kb_path.rglob(f"*{ext}"):
                if ".obsidian" not in f.parts:
                    fpath = str(f.resolve())
                    current_files.add(fpath)
                    file_hash = _file_content_hash(fpath)
                    if file_hash and fpath not in self._file_hashes:
                        self._file_hashes[fpath] = file_hash

        stale = [key for key in self._file_hashes if key not in current_files]
        for key in stale:
            del self._file_hashes[key]

        _save_hash_cache(self._file_hashes)

    def _is_relevant_file(self, path):
        p = Path(path)
        if ".obsidian" in p.parts:
            return False
        return p.suffix.lower() in WATCHER_VALID_EXTENSIONS

    def _collect_changed_events(
        self, events: dict[str, tuple[str, float]]
    ) -> tuple[dict[str, tuple[str, float]], dict[str, str | None]]:
        """Capture each changed source hash before indexing begins."""
        changed_events: dict[str, tuple[str, float]] = {}
        indexed_hashes: dict[str, str | None] = {}
        for path, (event_type, timestamp) in events.items():
            observed_hash = (
                None if event_type == "deleted" else _file_content_hash(path)
            )
            if event_type == "deleted" or self._file_hashes.get(path) != observed_hash:
                changed_events[path] = (event_type, timestamp)
                indexed_hashes[path] = observed_hash
        return changed_events, indexed_hashes

    def _commit_hashes(
        self,
        events: dict[str, tuple[str, float]],
        indexed_hashes: dict[str, str | None],
    ) -> list[tuple[str, str]]:
        """Checkpoint only stable source versions and return required retries."""
        retry_events: list[tuple[str, str]] = []
        for path in events:
            indexed_hash = indexed_hashes[path]
            current_hash = _file_content_hash(path)
            if current_hash != indexed_hash:
                # A source changed while it was being indexed. Never associate
                # the newly observed bytes with the generation just published:
                # a modification rebuild also removes triples from that stale
                # intermediate version.
                retry_type = "deleted" if current_hash is None else "modified"
                retry_events.append((retry_type, path))
                continue
            if indexed_hash is None:
                self._file_hashes.pop(path, None)
            else:
                self._file_hashes[path] = indexed_hash
        _save_hash_cache(self._file_hashes)
        return retry_events

    def _schedule_processing(self, event_type, path):
        normalized_path = str(Path(path).resolve())
        with self._lock:
            previous = self._pending_events.get(normalized_path)
            if previous is not None:
                previous_type, _ = previous
                # Preserve the strongest event. In particular, delete→create is
                # an atomic replacement and must still force a full rebuild.
                if _WATCHER_EVENT_PRIORITY[previous_type] > _WATCHER_EVENT_PRIORITY[event_type]:
                    event_type = previous_type
            self._pending_events[normalized_path] = (event_type, time.time())
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(
                WATCHER_DEBOUNCE_SECONDS, self._process_pending
            )
            self._timer.daemon = True
            self._timer.start()

    def _process_pending(self):
        with self._lock:
            events = dict(self._pending_events)
            self._pending_events.clear()
            self._timer = None

        if not events:
            return

        real_events, indexed_hashes = self._collect_changed_events(events)
        if not real_events:
            safe_print("\n(Filesystem events ignored: no real content changes)")
            return

        deleted = [p for p, (event_type, _) in real_events.items() if event_type == "deleted"]
        modified = [p for p, (event_type, _) in real_events.items() if event_type == "modified"]
        created = [p for p, (event_type, _) in real_events.items() if event_type == "created"]

        # Any modification/deletion gets one full rebuild so removed structural
        # triples cannot survive. The same rebuild also includes batch creations.
        if deleted or modified:
            safe_print("\nFile modification/deletion detected. Rebuilding graph...")
            self.rag_system.build_index()
        else:
            for path in created:
                if os.path.exists(path):
                    safe_print(f"\nNew file detected: {os.path.basename(path)}.")
                    self.rag_system.insert_document(path)

        retry_events = self._commit_hashes(real_events, indexed_hashes)
        for event_type, path in retry_events:
            self._schedule_processing(event_type, path)

    def on_created(self, event):
        if not event.is_directory and self._is_relevant_file(event.src_path):
            self._schedule_processing("created", event.src_path)

    def on_modified(self, event):
        if not event.is_directory and self._is_relevant_file(event.src_path):
            self._schedule_processing("modified", event.src_path)

    def on_deleted(self, event):
        if not event.is_directory and self._is_relevant_file(event.src_path):
            self._schedule_processing("deleted", event.src_path)


# ==========================================
# TERMINAL INTERFACE (Rich)
# ==========================================
def _check_ollama_available(
    model_name: str,
    embed_model: str,
    base_url: str = OLLAMA_BASE_URL,
    request_timeout: float = OLLAMA_TIMEOUT,
):
    """Verify the configured Ollama endpoint and required models are available.

    Prints clear error messages with suggested commands if something is missing.
    Returns True if everything is ready, False otherwise.
    """
    import urllib.request
    import json as _json

    # Check if Ollama is running
    try:
        req = urllib.request.Request(f"{base_url}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=request_timeout) as resp:
            data = _json.loads(resp.read().decode())
    except Exception:
        console.print(
            Panel(
                "[bold red]Ollama is not running.[/bold red]\n\n"
                "Start Ollama before running Geode Graph:\n"
                "  [dim]ollama serve[/dim]",
                title="[red]Connection Error[/red]",
                border_style="red",
            )
        )
        return False

    # Check available models
    available_models = set()
    for model_info in data.get("models", []):
        name = model_info.get("name", "")
        available_models.add(name)
        # Also add without tag (e.g. "qwen2.5:3b" -> "qwen2.5")
        if ":" in name:
            available_models.add(name.split(":")[0])

    missing = []
    if model_name not in available_models and model_name.split(":")[0] not in available_models:
        missing.append(model_name)
    if embed_model not in available_models and embed_model.split(":")[0] not in available_models:
        missing.append(embed_model)

    if missing:
        cmds = "\n".join(f"  [dim]ollama pull {m}[/dim]" for m in missing)
        console.print(
            Panel(
                f"[bold yellow]Missing model(s):[/bold yellow] {', '.join(missing)}\n\n"
                f"Pull them with:\n{cmds}",
                title="[yellow]Model Not Found[/yellow]",
                border_style="yellow",
            )
        )
        return False

    return True


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Geode Graph - Knowledge Graph Assistant")
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Fast mode: disables LLM synonym retriever for faster queries",
    )
    parser.add_argument(
        "--llm-model",
        type=str,
        default=None,
        help=f"Override LLM model (default: {MODEL_NAME})",
    )
    parser.add_argument(
        "--embed-model",
        type=str,
        default=None,
        help=f"Override embedding model (default: {EMBED_MODEL})",
    )
    args = parser.parse_args()

    # Resolve model names (CLI overrides config)
    llm_model = args.llm_model or MODEL_NAME
    embed_model = args.embed_model or EMBED_MODEL

    _ensure_nest_asyncio()

    # Check Ollama before doing anything expensive
    if not _check_ollama_available(llm_model, embed_model):
        sys.exit(1)

    # Initialize LLM (P0.6: no side effects on import)
    _init_llm(model_name=llm_model, embed_model=embed_model)

    console.print()
    console.print(
        Panel(
            Text.from_markup(
                f"[bold]Geode Graph[/bold]\n"
                f"[dim]LLM:[/dim] {llm_model}  "
                f"[dim]Mode:[/dim] {'FAST' if args.fast else 'FULL'}  "
                f"[dim]Watching:[/dim] {KNOWLEDGE_DIR}"
            ),
            border_style="bright_black",
            padding=(1, 2),
        )
    )

    try:
        with Status("[dim]Loading knowledge graph...[/dim]", console=console, spinner="dots"):
            rag = WritHerGraphRAG(
                fast_mode=args.fast,
                model_name=llm_model,
                embed_model=embed_model,
            )
    except EmbeddingModelMismatchError as exc:
        console.print(
            Panel(
                f"[bold red]{exc}[/bold red]\n\n"
                "Kwipu did not rebuild automatically because mixing embedding "
                "models would invalidate the stored vectors.",
                title="[red]Embedding Configuration Error[/red]",
                border_style="red",
            )
        )
        return 2

    observer = Observer()
    observer.schedule(FileWatcher(rag), KNOWLEDGE_DIR, recursive=True)
    observer.start()

    console.print("[dim]Type your question, or 'exit' to quit.[/dim]\n")

    try:
        while True:
            try:
                query = console.input("[bold bright_white]>[/bold bright_white] ")
            except EOFError:
                break

            if query.lower().strip() in ["exit", "quit", "esci"]:
                break

            try:
                query = validate_question(query)
            except QueryValidationError as exc:
                console.print(f"[yellow]{exc}[/yellow]")
                continue

            with Status("[dim]Querying graph...[/dim]", console=console, spinner="dots"):
                start_t = time.time()
                response = rag.ask(query)
                elapsed = time.time() - start_t

            console.print()
            console.print(
                Panel(
                    Markdown(str(response)),
                    title="[bold]Response[/bold]",
                    subtitle=f"[dim]{elapsed:.1f}s[/dim]",
                    border_style="bright_black",
                    padding=(1, 2),
                )
            )
            console.print()

    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()
        console.print("\n[dim]Goodbye.[/dim]")


if __name__ == "__main__":
    raise SystemExit(main())
