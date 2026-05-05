"""
Prompt builder for the doctor-facing RAG layer.

All prompts must:
- Be addressed to doctors only.
- Cite approved retrieved knowledge base chunks.
- Include a safety disclaimer.
- Never generate a final diagnosis.
- Never generate prescriptions.
- Never address the patient directly.
"""

from __future__ import annotations

SAFETY_DISCLAIMER = (
    "AI-assisted medical support. This is not a final diagnosis or treatment decision. "
    "The licensed doctor remains responsible for clinical judgment."
)

SYSTEM_PROMPT = (
    """\
You are a doctor-facing medical support assistant for Al-Rafidain Medical Platform.

Your role is to assist licensed doctors by summarising relevant approved medical knowledge.

STRICT RULES:
- Answer ONLY using the approved retrieved context provided below.
- Do NOT provide a final diagnosis.
- Do NOT prescribe medications.
- Do NOT address the patient directly.
- Do NOT make claims beyond what is in the approved sources.
- If the retrieved context is insufficient to answer the question, say so clearly.
- Always include source references from the retrieved context.
- Always end your response with the safety disclaimer.

REQUIRED RESPONSE FORMAT:
1. Brief answer grounded in approved sources
2. Relevant points from approved sources
3. Suggested follow-up questions or clinical considerations
4. Red flags (if applicable)
5. Sources (Document title, Chunk ID, Page if available)
6. Safety note: \""""
    + SAFETY_DISCLAIMER
    + """\"""
"""
)


def _format_chunks(retrieved_chunks: list[dict]) -> str:
    """Format retrieved chunks into numbered source blocks."""
    if not retrieved_chunks:
        return "No approved context was retrieved."

    lines = []
    for i, hit in enumerate(retrieved_chunks, start=1):
        chunk = hit["chunk"]
        doc = chunk.document
        lines.append(f"[Source {i}]")
        lines.append(f"Document: {doc.title}")
        lines.append(f"Document Type: {doc.document_type}")
        lines.append(f"Chunk ID: {chunk.pk}")
        if chunk.page_number:
            lines.append(f"Page: {chunk.page_number}")
        if chunk.section_title:
            lines.append(f"Section: {chunk.section_title}")
        lines.append(f"Relevance Score: {hit['score']:.4f}")
        lines.append(f"Text:\n{chunk.text}")
        lines.append("")
    return "\n".join(lines)


def build_doctor_rag_prompt(
    query_text: str,
    retrieved_chunks: list[dict],
    service_context: str,
    object_summary: str | None = None,
) -> list[dict[str, str]]:
    """
    Build the message list for the DeepSeek Chat Completions API.

    Args:
        query_text: The doctor's question.
        retrieved_chunks: List of {chunk, score, distance, rank} dicts from semantic search.
        service_context: e.g. 'consultation', 'lab_result', 'general_doctor_query'
        object_summary: Optional summary of the clinical object (consultation, lab result, etc.)

    Returns:
        List of {role, content} dicts ready for the LLM.
    """
    context_label = service_context.replace("_", " ").title()

    user_parts = [
        f"Service context: {context_label}",
        "",
        f"Doctor question:\n{query_text}",
    ]

    if object_summary:
        user_parts += [
            "",
            f"Clinical object summary:\n{object_summary}",
        ]

    user_parts += [
        "",
        "Approved retrieved context:",
        _format_chunks(retrieved_chunks),
    ]

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(user_parts)},
    ]
