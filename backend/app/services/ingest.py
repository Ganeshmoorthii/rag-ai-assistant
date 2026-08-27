from app.services.chunker import chunk_text
from app.services.pdf_loader import extract_text_by_page
from app.services.vector_store import add_chunks, new_doc_id


def ingest_pdf(file_path: str, filename: str) -> dict:
    doc_id = new_doc_id()
    pages = extract_text_by_page(file_path)

    chunks = []
    for page in pages:
        for chunk in chunk_text(page["text"]):
            chunks.append({"text": chunk, "page": page["page"]})

    count = add_chunks(doc_id, filename, chunks)
    return {"doc_id": doc_id, "filename": filename, "chunks": count}
