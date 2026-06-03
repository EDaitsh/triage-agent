"""
RAG – Retrieval-Augmented Generation module
============================================
Functions
---------
chunk_text   – split text into overlapping character chunks
embed        – convert text to an embedding vector (OpenAI)
ingest_data  – chunk + embed + store in ChromaDB
retrieve     – cosine-similarity search against the vector store
answer_question – full RAG pipeline: retrieve → prompt → LLM → answer
"""

import asyncio
import logging
import os
import uuid
from typing import List

import chromadb

from .llm import MODEL, client

logger = logging.getLogger("rag")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    datefmt="%H:%M:%S",
)

# ── Configuration ────────────────────────────────────────────────────────────
CHROMA_PATH: str = os.environ.get("CHROMA_PATH", "./chromadb")
COLLECTION_NAME: str = "org_knowledge"
EMBED_MODEL: str = "text-embedding-3-small"

CHUNK_SIZE: int = 600       # characters per chunk
CHUNK_OVERLAP: int = 80     # character overlap between consecutive chunks
TOP_K: int = 8              # number of documents returned by retrieve()


# ── 1. chunk_text ────────────────────────────────────────────────────────────
def chunk_text(
    text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP
) -> List[str]:
    """
    Section-aware chunking strategy:
    1. Split the document on Markdown headings (## / ###).
    2. Each section is prefixed with its heading so every chunk is
       self-contained — a retrieved chunk always includes its topic.
    3. Sections longer than *size* are sub-divided by paragraphs while
       keeping the section heading on every sub-chunk.
    4. Very long paragraphs fall back to a sliding character window.
    """
    import re

    # Split on lines that start with one or more # characters
    parts = re.split(r"(?=^#{1,3} )", text, flags=re.MULTILINE)
    chunks: List[str] = []

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Extract the heading (first line) to repeat on sub-chunks
        first_line = part.split("\n", 1)[0].strip()
        heading = first_line if first_line.startswith("#") else ""

        if len(part) <= size:
            chunks.append(part)
            continue

        # Section is too long → split by paragraphs, keep heading on each
        paragraphs = [p.strip() for p in part.split("\n\n") if p.strip()]
        current = ""

        for para in paragraphs:
            # If a single paragraph exceeds size, slide over it
            if len(para) > size:
                if current:
                    chunks.append(current)
                    current = ""
                start = 0
                while start < len(para):
                    window = para[start: start + size].strip()
                    if window:
                        prefix = (
                            f"{heading}\n"
                            if heading and not window.startswith("#")
                            else ""
                        )
                        chunks.append((prefix + window).strip())
                    start += size - overlap
                continue

            candidate = (current + "\n\n" + para).strip() if current else para
            if len(candidate) <= size:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                # New sub-chunk: re-attach section heading for context
                prefix = (
                    f"{heading}\n[המשך]\n"
                    if heading and not para.startswith("#")
                    else ""
                )
                current = (prefix + para).strip()

        if current:
            chunks.append(current)

    return chunks


# ── 2. embed ─────────────────────────────────────────────────────────────────
async def embed(text: str) -> List[float]:
    """Return embedding vector for *text* using OpenAI's embedding model."""
    response = await client.embeddings.create(
        model=EMBED_MODEL,
        input=text,
    )
    return response.data[0].embedding


# ── 3. ingest_data ───────────────────────────────────────────────────────────
async def ingest_data(text: str, source: str = "unknown") -> int:
    """
    Chunk *text*, embed every chunk and persist them in ChromaDB.

    Parameters
    ----------
    text   : raw document text
    source : human-readable label stored as metadata (e.g. filename)

    Returns
    -------
    Number of chunks added to the collection.
    """
    chunks = chunk_text(text)
    if not chunks:
        logger.warning("ingest_data: הטקסט ריק לאחר חיתוך – לא נוסף דבר")
        return 0

    logger.info(
        "ingest_data: מקור='%s' | %d תווים → %d chunks (size=%d, overlap=%d)",
        source, len(text), len(chunks), CHUNK_SIZE, CHUNK_OVERLAP,
    )
    for i, ch in enumerate(chunks):
        suffix = "…" if len(ch) > 80 else ""
        logger.debug("  chunk[%d]: %r", i, ch[:80] + suffix)

    # Embed all chunks (sequential to respect rate limits)
    embeddings: List[List[float]] = []
    for i, chunk in enumerate(chunks):
        emb = await embed(chunk)
        embeddings.append(emb)
        logger.debug(
            "  embed chunk[%d]: וקטור באורך %d, ערכים ראשונים: %s",
            i, len(emb), [round(v, 4) for v in emb[:5]],
        )

    ids = [str(uuid.uuid4()) for _ in chunks]
    metadatas = [
        {"source": source, "chunk_index": i} for i, _ in enumerate(chunks)
    ]

    def _add_to_chroma() -> int:
        col = _get_collection()
        col.add(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas,
        )
        total = col.count()
        logger.info(
            "ingest_data: נשמרו %d chunks → סה\"כ %d במאגר",
            len(chunks), total,
        )
        return len(chunks)

    return await asyncio.to_thread(_add_to_chroma)


# ── 4. retrieve ──────────────────────────────────────────────────────────────
async def retrieve(query: str, top_k: int = TOP_K) -> List[dict]:
    """
    Embed *query* and return the *top_k* most similar chunks from ChromaDB.

    Each result dict contains:
      - ``text``     : the original chunk text
      - ``source``   : metadata source label
      - ``distance`` : cosine distance (lower = more similar)
    """
    logger.info("retrieve: שאילתה='%s' | top_k=%d", query, top_k)

    query_embedding = await embed(query)
    logger.debug(
        "retrieve: וקטור השאילתה – אורך %d, ערכים ראשונים: %s",
        len(query_embedding), [round(v, 4) for v in query_embedding[:5]],
    )

    def _query_chroma() -> dict:
        col = _get_collection()
        count = col.count()
        logger.debug("retrieve: %d מסמכים במאגר", count)
        if count == 0:
            return {"documents": [[]], "metadatas": [[]], "distances": [[]]}
        n = min(top_k, count)
        return col.query(
            query_embeddings=[query_embedding],
            n_results=n,
        )

    results = await asyncio.to_thread(_query_chroma)

    docs: List[dict] = []
    for i, doc in enumerate(results["documents"][0]):
        distance = (
            results["distances"][0][i]
            if results.get("distances") and results["distances"][0]
            else None
        )
        similarity = round(1 - distance, 4) if distance is not None else None
        source = results["metadatas"][0][i].get("source", "unknown")
        chunk_index = results["metadatas"][0][i].get("chunk_index", "?")
        logger.info(
            "  תוצאה[%d]: מקור='%s' chunk=%s"
            " | dist=%.4f sim=%.4f | טקסט: %r",
            i, source, chunk_index,
            distance if distance is not None else -1,
            similarity if similarity is not None else -1,
            doc[:100] + ("…" if len(doc) > 100 else ""),
        )
        docs.append(
            {
                "text": doc,
                "source": source,
                "distance": distance,
                "similarity": similarity,
            }
        )

    logger.info("retrieve: הוחזרו %d תוצאות", len(docs))
    return docs


# ── 5. answer_question ───────────────────────────────────────────────────────
async def answer_question(question: str) -> dict:
    """
    Full RAG pipeline:
    1. Retrieve relevant chunks for *question*
    2. Build a context-enriched prompt
    3. Call the LLM
    4. Return answer + source references

    Returns
    -------
    dict with keys: ``question``, ``answer``, ``sources``
    """
    logger.info("answer_question: שאלה='%s'", question)

    docs = await retrieve(question)

    if docs:
        context = "\n\n---\n\n".join(
            f"[מקור: {d['source']}]\n{d['text']}" for d in docs
        )
        logger.info(
            "answer_question: נבנה הקשר מ-%d chunks, %d תווים סה\"כ",
            len(docs), len(context),
        )
    else:
        context = "אין מידע זמין במאגר הידע."
        logger.warning("answer_question: לא נמצאו chunks – תשובה ללא הקשר")

    system_prompt = (
        "אתה עוזר ידע ארגוני. ענה על שאלת המשתמש"
        " אך ורק בהתבסס על המידע המצורף.\n"
        "אם המידע אינו מספיק לתשובה מלאה, ציין זאת בבירור ואל תמציא פרטים.\n\n"
        f"מידע מהמאגר:\n{context}"
    )

    response = await client.responses.create(
        model=MODEL,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
    )

    return {
        "question": question,
        "answer": response.output_text,
        "sources": [
            {"text": d["text"][:300], "source": d["source"]}
            for d in docs
        ],
    }


# ── helpers ──────────────────────────────────────────────────────────────────
def _get_collection() -> chromadb.Collection:
    """Return (or create) the ChromaDB collection using cosine similarity."""
    chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
    return chroma_client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def get_collection_stats() -> dict:
    """Return basic stats about the knowledge collection (sync)."""
    col = _get_collection()
    return {"count": col.count(), "name": COLLECTION_NAME}
