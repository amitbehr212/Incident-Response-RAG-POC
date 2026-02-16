# Incident Response RAG Pipeline

> **Production-ready RAG pipeline** for incident response agents that processes security documents from Google Drive into Discovery Engine for retrieval-augmented generation.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Key Features](#key-features)
- [Document Types Supported](#document-types-supported)
- [Prerequisites](#prerequisites)
- [Local Development](#local-development)
- [Deployment](#deployment)
- [Usage](#usage)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)

---

## Overview

The Incident Response RAG Pipeline is a **Vertex AI Pipeline (Kubeflow)** that:

1. ✅ Reads incident response documents from Google Drive (via domain-wide delegation)
2. ✅ Extracts text from multiple formats (PDF, Word, Excel, Google Docs/Sheets)
3. ✅ Intelligently deduplicates files using timestamp + hash-based checks
4. ✅ Chunks text for optimal retrieval (1500 chars, 200 overlap)
5. ✅ Generates embeddings using Vertex AI `text-embedding-005`
6. ✅ Stores in BigQuery for analytics
7. ✅ Exports to Discovery Engine for RAG-powered search

**Result:** Up-to-date, searchable knowledge base for incident response! 🚀

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│              Google Drive Shared Folder                          │
│     (Runbooks, Playbooks, Post-Mortems, SOPs)                   │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│         Vertex AI Pipeline (Kubeflow) - 2 Components            │
├─────────────────────────────────────────────────────────────────┤
│  1️⃣  process_drive_documents                                    │
│      • Lists files from Google Drive                             │
│      • Deduplication (timestamp + hash)                          │
│      • Text extraction (PDF, Word, Excel, Google Docs/Sheets)   │
│      • Text chunking (RecursiveCharacterTextSplitter)           │
│      • Embedding generation (Vertex AI text-embedding-005)      │
│      • Storage to BigQuery                                       │
│      • Export to JSONL                                           │
│                                                                   │
│  2️⃣  ingest_data                                                │
│      • Updates Discovery Engine schema (idempotent)              │
│      • Imports documents from JSONL                              │
│      • Builds search index                                       │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│              Discovery Engine Data Store                         │
│  • Indexed documents ready for RAG retrieval                     │
│  • Hybrid search: Semantic (embeddings) + Keyword                │
│  • Used by incident response agent for context retrieval         │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Features

### 🎯 Incident Response Focused
- **Runbooks & Playbooks**: Step-by-step incident response procedures
- **Post-Mortems**: Historical incident reports and lessons learned
- **SOPs & Policies**: Security policies and standard operating procedures
- **Technical Docs**: Architecture diagrams, system documentation

### 🚀 Performance
- **Incremental processing**: Only processes new/changed files
- **Two-stage deduplication**:
  1. Timestamp check (fast, no download)
  2. Content hash verification (only for changed files)
- **Parallel processing**: Kubeflow pipeline components run efficiently

### 📊 Supported File Types
| Format | Parser | Status |
|--------|--------|--------|
| PDF | PyMuPDF (fitz) | ✅ |
| Word (.docx) | python-docx | ✅ |
| Excel (.xlsx) | openpyxl | ✅ |
| Plain Text | UTF-8 decode | ✅ |
| Markdown | UTF-8 decode | ✅ |
| Images (PNG/JPEG) | Pillow + pytesseract OCR | ✅ |
| Google Docs | Export as text | ✅ |
| Google Sheets | Export as Excel → parse | ✅ |

### 🔐 Security
- **Domain-wide delegation**: Service account impersonates users
- **Least privilege**: `drive.readonly` scope only
- **Secure secrets**: Service account keys in Secret Manager
- **Audit logging**: All operations logged in Cloud Logging

---

## Document Types Supported

This RAG is optimized for incident response documents:

1. **Runbooks & Playbooks**
   - Step-by-step incident response procedures
   - Troubleshooting guides
   - Recovery procedures

2. **Post-Mortems & Incident Reports**
   - Root cause analyses (RCAs)
   - Timeline of events
   - Lessons learned
   - Action items

3. **Security Policies**
   - Security policies and standards
   - Compliance documentation
   - Access control policies

4. **Technical Documentation**
   - System architecture diagrams
   - API documentation
   - Configuration guides

---

## Prerequisites

### GCP Resources Required

1. **GCP Project** with the following APIs enabled:
   - Vertex AI API
   - Cloud Storage API
   - BigQuery API
   - Discovery Engine API
   - Drive API

2. **Service Account** with:
   - Domain-wide delegation enabled
   - Scopes: `https://www.googleapis.com/auth/drive.readonly`
   - IAM roles:
     - `roles/bigquery.admin`
     - `roles/storage.admin`
     - `roles/aiplatform.user`
     - `roles/discoveryengine.admin`

3. **Storage Resources**:
   - GCS bucket: `{project-id}-incident-response-rag`
   - BigQuery dataset: `incident_response_rag`
   - Discovery Engine data store: `incident-response-datastore`

4. **Google Drive**:
   - Shared Drive or folder with incident response documents
   - Service account has access via domain-wide delegation

---

## Local Development

### 1. Install uv (Python package manager)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Install dependencies

```bash
cd /Users/aidan.behrens/incident-response-agent
uv sync
```

### 3. Set up credentials

```bash
# Download service account key from GCP Console or Secret Manager
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account-key.json"
```

### 4. Compile pipeline locally

```bash
uv run python pipeline/submit_pipeline.py \
  --project-id YOUR_PROJECT_ID \
  --location us-central1 \
  --drive-folder-id YOUR_FOLDER_ID \
  --impersonation-user user@yourdomain.com
```

---

## Deployment

### Option 1: Submit Pipeline Manually

```bash
# Set environment variables
export PROJECT_ID="your-project-id"
export LOCATION="us-central1"
export DRIVE_FOLDER_ID="your-drive-folder-id"
export IMPERSONATION_USER="user@yourdomain.com"

# Submit pipeline
uv run python pipeline/submit_pipeline.py \
  --project-id $PROJECT_ID \
  --location $LOCATION \
  --drive-folder-id $DRIVE_FOLDER_ID \
  --impersonation-user $IMPERSONATION_USER
```

### Option 2: Schedule with Cloud Scheduler

Create a Cloud Run Job that submits the pipeline on a schedule:

```bash
# Create Cloud Run Job
gcloud run jobs create incident-response-rag-trigger \
  --image gcr.io/YOUR_PROJECT/incident-response-rag:latest \
  --region us-central1 \
  --set-env-vars PROJECT_ID=$PROJECT_ID,DRIVE_FOLDER_ID=$DRIVE_FOLDER_ID \
  --service-account pipeline-sa@$PROJECT_ID.iam.gserviceaccount.com

# Create Cloud Scheduler job (daily at 3 AM UTC)
gcloud scheduler jobs create http incident-response-rag-daily \
  --location us-central1 \
  --schedule "0 3 * * *" \
  --uri "https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$PROJECT_ID/jobs/incident-response-rag-trigger:run" \
  --http-method POST \
  --oauth-service-account-email pipeline-sa@$PROJECT_ID.iam.gserviceaccount.com
```

---

## Usage

### Query the RAG

Once documents are ingested into Discovery Engine, you can query using the Discovery Engine API:

```python
from google.cloud import discoveryengine_v1 as discoveryengine

client = discoveryengine.SearchServiceClient()

request = discoveryengine.SearchRequest(
    serving_config=f"projects/{project_id}/locations/global/dataStores/incident-response-datastore/servingConfigs/default_serving_config",
    query="How do I respond to a DDoS attack?",
    page_size=10,
)

response = client.search(request)

for result in response.results:
    print(f"Title: {result.document.derived_struct_data['document_name']}")
    print(f"Content: {result.document.derived_struct_data['content']}")
    print(f"Link: {result.document.derived_struct_data['web_link']}")
    print("---")
```

### Integrate with Agent

Use the RAG in your incident response agent:

```python
from google.cloud import discoveryengine_v1 as discoveryengine

def retrieve_context(query: str, top_k: int = 5) -> list[str]:
    """Retrieve relevant context from RAG."""
    client = discoveryengine.SearchServiceClient()

    request = discoveryengine.SearchRequest(
        serving_config=f"projects/{PROJECT_ID}/locations/global/dataStores/incident-response-datastore/servingConfigs/default_serving_config",
        query=query,
        page_size=top_k,
    )

    response = client.search(request)
    contexts = []

    for result in response.results:
        contexts.append({
            "content": result.document.derived_struct_data["content"],
            "source": result.document.derived_struct_data["document_name"],
            "link": result.document.derived_struct_data["web_link"],
        })

    return contexts

# Use in agent
user_query = "How do I investigate a potential data breach?"
contexts = retrieve_context(user_query)

# Pass contexts to LLM for response generation
```

---

## Monitoring

### Vertex AI Pipelines Console

Monitor pipeline execution:
- https://console.cloud.google.com/vertex-ai/pipelines?project=YOUR_PROJECT_ID

### BigQuery

Check ingested data:

```sql
-- Check latest ingestion
SELECT
  COUNT(*) as total_chunks,
  COUNT(DISTINCT document_id) as total_documents,
  MAX(file_mtime) as latest_modified_date
FROM `YOUR_PROJECT_ID.incident_response_rag.incident_response_embeddings`;

-- Check documents by type
SELECT
  document_type,
  COUNT(DISTINCT document_id) as doc_count
FROM `YOUR_PROJECT_ID.incident_response_rag.incident_response_embeddings`
GROUP BY document_type
ORDER BY doc_count DESC;
```

### Discovery Engine Console

Check indexed documents:
- https://console.cloud.google.com/gen-app-builder?project=YOUR_PROJECT_ID

---

## Troubleshooting

### Common Issues

#### ❌ "Permission denied" accessing Drive
**Cause**: Service account lacks domain-wide delegation
**Fix**: Ensure service account has `drive.readonly` scope and domain-wide delegation enabled in Google Workspace Admin

#### ❌ Pipeline timeout
**Cause**: Processing too many files
**Fix**: Deduplication is implemented - check if it's working correctly. Increase memory/CPU limits if needed.

#### ❌ Embedding generation fails
**Cause**: Vertex AI quota exceeded
**Fix**: Check quotas in GCP Console, implement additional retry logic or request quota increase

#### ❌ "Existing schema update processing is ongoing"
**Cause**: Concurrent schema updates
**Fix**: Code handles this with idempotent checks and blocking updates

### Debug Mode

Enable verbose logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

---

## File Structure

```
incident-response-agent/
├── pipeline/
│   ├── components/
│   │   ├── __init__.py
│   │   ├── parsers.py                    # File parsers (PDF, Word, Excel, etc.)
│   │   ├── process_drive_documents.py    # Main document processing component
│   │   └── ingest_data.py                # Discovery Engine ingestion component
│   ├── pipeline.py                        # Kubeflow pipeline definition
│   └── submit_pipeline.py                 # Pipeline submission script
├── tests/
│   └── ...                                # Unit tests
├── pyproject.toml                         # Python dependencies (uv)
├── Makefile                               # Common commands
└── README.md                              # This file
```

---

## Contributing

When adding new features:

1. **Add new file parser**: Update `parsers.py` and `get_file_type_config()`
2. **Test locally**: Run pipeline with small dataset
3. **Run linting**: `ruff check pipeline/`
4. **Update README**: Document new features

---

## License

Copyright 2025. All rights reserved.

---

## Related Resources

- [Vertex AI Pipelines Documentation](https://cloud.google.com/vertex-ai/docs/pipelines)
- [Discovery Engine Documentation](https://cloud.google.com/generative-ai-app-builder/docs/introduction)
- [Kubeflow Pipelines](https://www.kubeflow.org/docs/components/pipelines/)
- [ROKT Security RAG Reference](https://github.com/ROKT/security)
