"""
Upload (file) and Paste (JSON) endpoints + read views for batches.

The contract:
  POST /api/ingest/upload  (multipart)  → 202 Accepted + IngestionBatch
  POST /api/ingest/paste   (JSON)       → 202 Accepted + IngestionBatch
  GET  /api/batches/                    → paginated list
  GET  /api/batches/:id/                → detail with errors

Idempotency: a re-upload of the same bytes (same file_sha256, same org)
returns 200 with the existing batch in body + `deduped: true` flag. No new
batch row, no new parse task.

The actual parsing runs in a Celery worker via `parse_batch.delay(batch.id)`.
The upload endpoint returns immediately; the frontend polls /api/batches/:id/.
"""

from __future__ import annotations

import hashlib
import json

from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from core.utils import require_org

from .models import IngestionBatch, SourceType
from .serializers import IngestionBatchDetailSerializer, IngestionBatchSerializer
from .storage import write_bytes
from .tasks import parse_batch


class BatchListView(generics.ListAPIView):
    serializer_class = IngestionBatchSerializer

    def get_queryset(self):
        org = require_org(self.request)
        qs = IngestionBatch.objects.for_org(org)
        source = self.request.query_params.get("source")
        if source in SourceType.values:
            qs = qs.filter(source_type=source)
        return qs


class BatchDetailView(generics.RetrieveAPIView):
    serializer_class = IngestionBatchDetailSerializer

    def get_queryset(self):
        org = require_org(self.request)
        return IngestionBatch.objects.for_org(org).prefetch_related("errors")


class UploadView(APIView):
    parser_classes = [MultiPartParser]

    def post(self, request):
        org = require_org(request)
        source = request.data.get("source_type")
        if source not in SourceType.values:
            raise ValidationError({"source_type": "Must be one of " + ", ".join(SourceType.values)})

        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationError({"file": "Required."})

        # Stream-hash so memory stays flat regardless of file size; we also
        # buffer the full bytes into memory for parsing (acceptable for the
        # prototype's expected file sizes; production would stream to S3).
        hasher = hashlib.sha256()
        chunks: list[bytes] = []
        size = 0
        for chunk in upload.chunks():
            hasher.update(chunk)
            chunks.append(chunk)
            size += len(chunk)
        digest = hasher.hexdigest()
        raw = b"".join(chunks)

        existing = IngestionBatch.objects.for_org(org).filter(file_sha256=digest).first()
        if existing is not None:
            return Response(
                {**IngestionBatchSerializer(existing).data, "deduped": True},
                status=status.HTTP_200_OK,
            )

        batch = IngestionBatch.objects.create(
            organization=org, source_type=source,
            uploaded_by=request.user,
            file_name=upload.name, file_sha256=digest, file_size_bytes=size,
            parser_version="pending",   # task stamps the real version
        )
        write_bytes(batch.id, raw)
        parse_batch.delay(batch.id)

        return Response(IngestionBatchSerializer(batch).data, status=status.HTTP_202_ACCEPTED)


class PasteView(APIView):
    parser_classes = [JSONParser]

    def post(self, request):
        org = require_org(request)
        if request.data.get("source_type") != SourceType.TRAVEL:
            raise ValidationError(
                {"source_type": "Paste is only supported for source_type=travel."}
            )
        payload = request.data.get("payload")
        if not isinstance(payload, (dict, list)):
            raise ValidationError({"payload": "Required JSON object/array."})

        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        digest = hashlib.sha256(canonical).hexdigest()
        size = len(canonical)

        existing = IngestionBatch.objects.for_org(org).filter(file_sha256=digest).first()
        if existing is not None:
            return Response(
                {**IngestionBatchSerializer(existing).data, "deduped": True},
                status=status.HTTP_200_OK,
            )

        batch = IngestionBatch.objects.create(
            organization=org, source_type=SourceType.TRAVEL,
            uploaded_by=request.user,
            file_name=request.data.get("file_name", "pasted.json"),
            file_sha256=digest, file_size_bytes=size,
            parser_version="pending",
        )
        write_bytes(batch.id, canonical)
        parse_batch.delay(batch.id)

        return Response(IngestionBatchSerializer(batch).data, status=status.HTTP_202_ACCEPTED)
