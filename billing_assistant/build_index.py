"""Offline ingestion: split docs into chunks, embed them, save the index."""
import json
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

HERE = Path(__file__).parent
DOCS_DIR = HERE / "docs"
INDEX_FILE = HERE / "index.json"
EMBED_MODEL = "gemini-embedding-001"     # use the name from your model list

load_dotenv(HERE / ".env")               # same API key the agent uses
client = genai.Client()


def chunk_markdown(path: Path) -> list[dict]:
    """One chunk per '## ' section, with the document title and source attached."""
    lines = path.read_text().splitlines()
    doc_title = lines[0].lstrip("# ").strip()
    source = next((l.split("Source:", 1)[1].strip()
                   for l in lines if l.startswith("Source:")), "")

    chunks, section, body = [], None, []

    def flush():
        if section and body:
            text = " ".join(l.strip() for l in body if l.strip())
            chunks.append({
                "id": f"{path.stem}#{len(chunks)}",
                "doc": doc_title,
                "section": section,
                "source": source,
                "text": text,
            })

    for line in lines[1:]:
        if line.startswith("## "):
            flush()
            section, body = line[3:].strip(), []
        elif section:
            body.append(line)
    flush()
    return chunks


def embed_documents(texts: list[str]) -> list[list[float]]:
    result = client.models.embed_content(
        model=EMBED_MODEL,
        contents=texts,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"
                                      #  output_dimensionality=768,        # ← optional; default is 3072
        ),
    )
    return [e.values for e in result.embeddings]


def main():
    chunks = []
    for path in sorted(DOCS_DIR.glob("*.md")):
        chunks += chunk_markdown(path)

    # Embed title + section + text, so the vector knows what the chunk is about
    texts = [f"{c['doc']} - {c['section']}\n{c['text']}" for c in chunks]
    vectors = embed_documents(texts)
    for c, v in zip(chunks, vectors):
        c["embedding"] = v

    INDEX_FILE.write_text(json.dumps(chunks))
    print(f"Indexed {len(chunks)} chunks, vector size {len(vectors[0])}")


if __name__ == "__main__":
    main()