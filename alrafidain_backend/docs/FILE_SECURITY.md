# File Upload and Document Security

This document describes file upload validation, storage configuration, and the
malware-scan boundary for clinical document uploads.

---

## Allowed File Types by Upload Category

| Category | Allowed Extensions | Allowed MIME Types |
|---|---|---|
| Knowledge Base documents | `.pdf`, `.docx`, `.txt` | `application/pdf`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, `text/plain` |
| Clinical attachments (messaging, lab results) | `.pdf`, `.docx`, `.txt`, `.jpg`, `.jpeg`, `.png`, `.webp` | same as above + `image/jpeg`, `image/png`, `image/webp` |
| Profile / license images | `.jpg`, `.jpeg`, `.png`, `.webp` | `image/jpeg`, `image/png`, `image/webp` |

Validation is enforced server-side in `apps/common/file_validation.py` using both
extension and `Content-Type` header checks. Client-supplied MIME types are treated
as hints only; if empty the server falls back to `mimetypes.guess_type`.

---

## Upload Size Limits

| Setting | Default | Env variable |
|---|---|---|
| `MAX_KNOWLEDGE_DOCUMENT_UPLOAD_MB` | 20 MB | `MAX_KNOWLEDGE_DOCUMENT_UPLOAD_MB` |
| `MAX_CLINICAL_ATTACHMENT_UPLOAD_MB` | 15 MB | `MAX_CLINICAL_ATTACHMENT_UPLOAD_MB` |
| `MAX_PROFILE_IMAGE_UPLOAD_MB` | 5 MB | `MAX_PROFILE_IMAGE_UPLOAD_MB` |

Requests exceeding these limits are rejected with HTTP 400 before any file data is
written to disk.

---

## Malware Scanning

File scanning is **disabled by default** (development-safe default).

| Setting | Default | Description |
|---|---|---|
| `FILE_SCANNING_ENABLED` | `False` | Enable/disable the scan gate |
| `FILE_SCANNER_BACKEND` | `""` | Backend identifier (future: `clamav`, `safefiles`, etc.) |

### Scan result states

| State | Meaning | Effect on processing |
|---|---|---|
| `scan_clean` | File passed the scanner | Processing continues normally |
| `scan_skipped` | Scanning disabled (`FILE_SCANNING_ENABLED=False`) | Processing continues; `security_status` set to `scan_skipped` |
| `scan_failed` | Scanner found a threat or backend error | Processing blocked; `security_status` set to `scan_failed`; document `processing_status` set to `FAILED` |

The scan boundary is implemented in `apps/common/file_scanner.py`. The
`process_knowledge_document_task` Celery task (in `apps/knowledge_base/tasks.py`)
calls `scan_uploaded_file()` before delegating to the processing service. Scan result
is recorded on `KnowledgeDocument.security_status`.

---

## File Storage

### Development (current)

Files are stored locally in the `media/` directory. `MEDIA_ROOT` and `MEDIA_URL` are
set in `config/settings/base.py`.

**WARNING**: Local file storage is not safe for production clinical deployments.
File paths are predictable and there are no access controls on individual files once
the URL is known.

### Production recommendation

Set `PRIVATE_MEDIA_STORAGE=True` in the production environment. When this flag is
`True`, the application should be configured to use a private object-storage bucket
(e.g., AWS S3 with `private` ACL, Azure Blob with private containers, or GCS with
uniform bucket-level access).

A Django system check (`common.W001`) will emit a **warning** if the application
starts with `ENVIRONMENT=production` and `PRIVATE_MEDIA_STORAGE=False`.

### File URL exposure policy

- `MessageAttachmentSerializer` and `LabResultPatientSerializer` serialise file fields
  with `use_url=False` — raw file paths are never included in API responses.
- Knowledge base documents do not include the `file` field in any read serializer.
- Profile image fields currently render DRF's default relative URL. **Do not serve
  profile image URLs directly to unauthenticated users** via the API.

---

## Secure Download Endpoints (Future)

Signed, time-limited download URLs are **not yet implemented**.

Planned approach:
1. Generate a signed URL (Django's `generate_filename` + cloud storage signing, or a
   custom HMAC token) valid for a short duration (e.g., 60 seconds).
2. Add a `GET /api/files/<token>/` endpoint that validates the token, checks that the
   requesting user has permission to access the referenced object, and either streams
   the file or issues an HTTP 302 redirect to the cloud-signed URL.
3. Log every download in the audit log (`action="file_downloaded"`).

This will be implemented in a future phase once private object storage is wired up.

---

## Limitations (Current Phase)

- No signed URLs.
- No per-file download audit logging (upload is logged; download is not yet).
- `FILE_SCANNER_BACKEND` integration is a placeholder — actual ClamAV/SaaS wiring is
  a future deliverable.
- Profile/license image uploads are validated by extension and MIME type but are not
  scanned for malicious content.
