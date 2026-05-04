"""
Management command to embed knowledge base chunks.

Usage:
    python manage.py embed_knowledge_base
    python manage.py embed_knowledge_base --force
    python manage.py embed_knowledge_base --document-id <uuid>
    python manage.py embed_knowledge_base --limit 100
"""
import uuid

from django.core.management.base import BaseCommand, CommandError

from apps.knowledge_base.services import embed_all_approved_chunks, embed_document_chunks


class Command(BaseCommand):
    help = "Embed knowledge base chunks using the configured embedding model."

    def add_arguments(self, parser):
        parser.add_argument(
            "--document-id",
            type=str,
            dest="document_id",
            default=None,
            help="UUID of a single KnowledgeDocument to embed (defaults to all approved docs).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            default=False,
            help="Re-embed chunks that already have embeddings.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of documents to process (all-approved mode only).",
        )

    def handle(self, *args, **options):
        document_id = options["document_id"]
        force = options["force"]
        limit = options["limit"]

        if document_id:
            from apps.knowledge_base.models import KnowledgeDocument

            try:
                doc_uuid = uuid.UUID(document_id)
            except ValueError:
                raise CommandError(f"Invalid UUID: {document_id}")

            try:
                document = KnowledgeDocument.objects.get(pk=doc_uuid)
            except KnowledgeDocument.DoesNotExist:
                raise CommandError(f"Document not found: {document_id}")

            self.stdout.write(f"Embedding document: {document.title} …")
            try:
                result = embed_document_chunks(document, force=force)
            except ValueError as exc:
                raise CommandError(str(exc))

            self.stdout.write(
                self.style.SUCCESS(
                    f"Done — embedded: {result['embedded']}, "
                    f"skipped: {result['skipped']}, "
                    f"failed: {result['failed']}"
                )
            )
        else:
            self.stdout.write("Embedding all approved document chunks …")
            result = embed_all_approved_chunks(force=force, limit=limit)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Done — embedded: {result['embedded']}, "
                    f"skipped: {result['skipped']}, "
                    f"failed: {result['failed']}"
                )
            )
