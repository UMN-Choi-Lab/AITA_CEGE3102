"""
Document ingestion pipeline for AITA 3102.
Course-specific collection functions + shared pipeline from aita_core.

Usage:
    python add_document.py
"""

import os

from aita_core.ingest import (
    get_week_for_filename, load_pdf, load_tex,
    chunk_documents, get_embeddings, build_faiss_index, save_index,
    collect_syllabus,
)
from config import CONFIG


def _week_for(filename):
    return get_week_for_filename(
        filename, CONFIG.topic_num_to_week, CONFIG.hw_num_to_week,
        CONFIG.lab_num_to_week, CONFIG.study_guide_to_week,
    )


def collect_handouts():
    docs = []
    handouts_dir = os.path.join(CONFIG.course_materials_dir, "Handouts", "Handouts")
    if not os.path.isdir(handouts_dir):
        print(f"  Warning: {handouts_dir} not found")
        return docs
    for filename in sorted(os.listdir(handouts_dir)):
        if not filename.endswith(".pdf"):
            continue
        file_path = os.path.join(handouts_dir, filename)
        label = f"Handout: {filename}"
        week = _week_for(filename)
        print(f"  Loading {label} (week {week})")
        docs.extend(load_pdf(file_path, label, max_week=week))
    return docs


def collect_homework_questions():
    docs = []
    hw_dir = os.path.join(CONFIG.course_materials_dir, "Homework handouts", "Homework handouts")
    if not os.path.isdir(hw_dir):
        print(f"  Warning: {hw_dir} not found")
        return docs
    for filename in sorted(os.listdir(hw_dir)):
        if not filename.endswith(".pdf"):
            continue
        if "solution" in filename.lower():
            print(f"  Skipping (solution): {filename}")
            continue
        file_path = os.path.join(hw_dir, filename)
        label = f"Homework: {filename}"
        week = _week_for(filename)
        print(f"  Loading {label} (week {week})")
        docs.extend(load_pdf(file_path, label, max_week=week))
    return docs


def collect_slide_content():
    docs = []
    slides_dir = os.path.join(CONFIG.course_materials_dir, "Slides", "Slides")
    if not os.path.isdir(slides_dir):
        print(f"  Warning: {slides_dir} not found")
        return docs
    for topic_name in sorted(os.listdir(slides_dir)):
        topic_path = os.path.join(slides_dir, topic_name)
        if not os.path.isdir(topic_path):
            continue
        label = f"Slides: {topic_name}"
        week = _week_for(topic_name)
        content_tex = os.path.join(topic_path, "content.tex")
        if os.path.exists(content_tex):
            print(f"  Loading {label} (LaTeX, week {week})")
            docs.extend(load_tex(content_tex, label, max_week=week))
        else:
            notes_pdf = os.path.join(topic_path, "Notes.pdf")
            if os.path.exists(notes_pdf):
                print(f"  Loading {label} (PDF, week {week})")
                docs.extend(load_pdf(notes_pdf, label, max_week=week))
    return docs


def main():
    print("=" * 60)
    print("AITA 3102 Document Ingestion Pipeline")
    print("=" * 60)

    print("\n[1/4] Collecting lecture handouts...")
    all_docs = collect_handouts()

    print("\n[2/4] Collecting homework questions & labs...")
    all_docs += collect_homework_questions()

    print("\n[3/4] Collecting slide content...")
    all_docs += collect_slide_content()

    print("\n[4/4] Collecting syllabus...")
    all_docs += collect_syllabus(CONFIG.course_materials_dir)

    if not all_docs:
        print("\nNo documents found. Check course_materials directory.")
        return

    print(f"\nTotal documents loaded: {len(all_docs)}")

    chunks = chunk_documents(all_docs, CONFIG.chunk_size, CONFIG.chunk_overlap)
    print(f"Total chunks after splitting: {len(chunks)}")

    print(f"\nGenerating embeddings with {CONFIG.embedding_model}...")
    texts = [c["text"] for c in chunks]
    embeddings = get_embeddings(texts, CONFIG.embedding_model)

    print("\nBuilding FAISS index...")
    index = build_faiss_index(embeddings)
    save_index(index, chunks, CONFIG.faiss_db_dir, CONFIG.docs_dir, CONFIG.backup_dir)

    print("\nDone! Vector store is ready.")


if __name__ == "__main__":
    main()
