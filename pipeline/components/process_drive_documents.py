# Copyright 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Process incident response documents from Google Drive."""

import hashlib
import json
from datetime import datetime
from typing import Any

import pandas as pd
from google.api_core import retry
from google.cloud import bigquery
from google.oauth2 import service_account
from googleapiclient.discovery import build
from kfp import dsl
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .parsers import get_file_type_config


@dsl.component(
    base_image="python:3.11-slim",
    packages_to_install=[
        "google-cloud-aiplatform>=1.116.0",
        "google-cloud-bigquery>=3.0",
        "google-auth>=2.0.0",
        "google-api-python-client>=2.0.0",
        "pymupdf>=1.23.0",
        "python-docx>=1.1.0",
        "openpyxl>=3.1.0",
        "Pillow>=10.0.0",
        "pytesseract>=0.3.10",
        "langchain-text-splitters>=1.0.0",
        "pandas>=2.0.0",
    ],
)
def process_drive_documents(
    project_id: str,
    schedule_time: str,
    drive_folder_id: str,
    impersonation_user: str,
    chunk_size: int,
    chunk_overlap: int,
    destination_dataset: str,
    destination_table: str,
    location: str,
    embedding_column: str,
) -> str:
    """Process incident response documents from Google Drive.

    Args:
        project_id: GCP project ID
        schedule_time: Pipeline schedule time
        drive_folder_id: Google Drive folder ID to process
        impersonation_user: Email of user to impersonate for Drive access
        chunk_size: Size of text chunks in characters
        chunk_overlap: Overlap between chunks in characters
        destination_dataset: BigQuery dataset name
        destination_table: BigQuery table name
        location: GCP location
        embedding_column: Name of the embedding column

    Returns:
        GCS path to JSONL file with processed documents
    """
    import os

    from google.auth import default
    from google.cloud import aiplatform, storage

    # Initialize Google Drive service with domain-wide delegation
    # Credentials are loaded from environment variable or default application credentials
    # No secrets are hardcoded - they're provided at runtime via:
    # 1. GOOGLE_APPLICATION_CREDENTIALS environment variable (local dev)
    # 2. Service account attached to Vertex AI Pipeline (production)
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

    if creds_path and os.path.exists(creds_path):
        # Local development: use credentials from file
        credentials = service_account.Credentials.from_service_account_file(
            creds_path,
            scopes=["https://www.googleapis.com/auth/drive.readonly"],
            subject=impersonation_user,
        )
    else:
        # Production: use default application credentials with domain-wide delegation
        base_credentials, _ = default(scopes=["https://www.googleapis.com/auth/drive.readonly"])
        # Create service account credentials with delegation
        if hasattr(base_credentials, "with_subject"):
            credentials = base_credentials.with_subject(impersonation_user)
        else:
            # Fallback: assume credentials already support delegation
            credentials = base_credentials

    drive_service = build("drive", "v3", credentials=credentials)

    # List files from Drive
    print(f"Listing files from Drive folder: {drive_folder_id}")
    files = list_drive_files(drive_service, drive_folder_id)
    print(f"Found {len(files)} files")

    # Get existing hashes from BigQuery for deduplication
    bq_client = bigquery.Client(project=project_id)
    existing_hashes = get_existing_hashes(bq_client, project_id, destination_dataset, destination_table)
    print(f"Found {len(existing_hashes)} existing documents in BigQuery")

    # Filter files by timestamp (fast check)
    files_to_download, stats = filter_by_timestamp(files, existing_hashes)
    print(f"Filtered to {len(files_to_download)} files after timestamp check")
    print(f"Stats: {stats}")

    # Verify by hash (download and check content)
    files_to_process = verify_by_hash(files_to_download, existing_hashes, drive_service, stats)
    print(f"Final files to process: {len(files_to_process)}")

    if not files_to_process:
        print("No new or modified files to process")
        # Return empty JSONL file
        output_path = f"gs://{project_id}-incident-response-rag/processed/empty.jsonl"
        return output_path

    # Process files
    all_chunks = []
    for file_info in files_to_process:
        print(f"Processing: {file_info['name']}")
        text = process_file_by_type(
            file_info["mimeType"], file_info["id"], file_info["name"], drive_service
        )

        if text:
            chunks = create_chunks_with_metadata(
                text,
                file_info["id"],
                file_info["name"],
                file_info["mimeType"],
                file_info["modifiedTime"],
                file_info["webViewLink"],
                file_info.get("path", ""),
                chunk_size,
                chunk_overlap,
            )
            all_chunks.extend(chunks)

    print(f"Created {len(all_chunks)} chunks from {len(files_to_process)} files")

    # Convert to DataFrame
    df = pd.DataFrame(all_chunks)

    # Generate embeddings
    print("Generating embeddings...")
    df = generate_embeddings(df, project_id, location)

    # Store to BigQuery
    print("Storing to BigQuery...")
    store_to_bigquery(df, project_id, destination_dataset, destination_table)

    # Export to JSONL for Discovery Engine
    print("Exporting to JSONL...")
    output_path = export_to_jsonl(
        project_id, destination_dataset, destination_table, embedding_column, schedule_time
    )

    print(f"Processing complete. Output: {output_path}")
    return output_path


def list_drive_files(drive_service: Any, folder_id: str) -> list[dict[str, Any]]:
    """List all files from Google Drive folder recursively.

    Args:
        drive_service: Google Drive API service
        folder_id: Folder ID to list files from

    Returns:
        List of file metadata dictionaries
    """
    files = []
    page_token = None

    query = f"'{folder_id}' in parents and trashed=false"

    while True:
        results = (
            drive_service.files()
            .list(
                q=query,
                pageSize=1000,
                fields="nextPageToken, files(id, name, mimeType, modifiedTime, webViewLink, parents)",
                pageToken=page_token,
            )
            .execute()
        )

        items = results.get("files", [])
        files.extend(items)

        page_token = results.get("nextPageToken")
        if not page_token:
            break

    # Recursively process folders
    all_files = []
    for item in files:
        if item["mimeType"] == "application/vnd.google-apps.folder":
            # Recursively list files in subfolder
            subfolder_files = list_drive_files(drive_service, item["id"])
            all_files.extend(subfolder_files)
        else:
            all_files.append(item)

    return all_files


def get_existing_hashes(
    bq_client: bigquery.Client, project_id: str, dataset: str, table: str
) -> dict[str, dict[str, Any]]:
    """Query BigQuery for existing file hashes.

    Args:
        bq_client: BigQuery client
        project_id: GCP project ID
        dataset: Dataset name
        table: Table name

    Returns:
        Dictionary mapping file_id to hash and modified time
    """
    query = f"""
    SELECT DISTINCT document_id, content_hash, file_mtime
    FROM `{project_id}.{dataset}.{table}`
    """

    try:
        results = bq_client.query(query).result()
        hashes = {}
        for row in results:
            hashes[row.document_id] = {
                "hash": row.content_hash,
                "mtime": row.file_mtime,
            }
        return hashes
    except Exception as e:
        print(f"Error querying BigQuery (table may not exist): {e}")
        return {}


def filter_by_timestamp(
    files: list[dict[str, Any]], existing_hashes: dict[str, dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Filter files by modification timestamp.

    Args:
        files: List of file metadata
        existing_hashes: Dictionary of existing file hashes

    Returns:
        Tuple of (files to download, statistics)
    """
    files_to_download = []
    stats = {"new": 0, "modified": 0, "unchanged": 0}

    for file in files:
        file_id = file["id"]
        file_mtime = file["modifiedTime"]

        if file_id not in existing_hashes:
            files_to_download.append(file)
            stats["new"] += 1
        elif existing_hashes[file_id]["mtime"] < file_mtime:
            files_to_download.append(file)
            stats["modified"] += 1
        else:
            stats["unchanged"] += 1

    return files_to_download, stats


def verify_by_hash(
    files: list[dict[str, Any]],
    existing_hashes: dict[str, dict[str, Any]],
    drive_service: Any,
    stats: dict[str, int],
) -> list[dict[str, Any]]:
    """Verify files by content hash.

    Args:
        files: List of files to verify
        existing_hashes: Dictionary of existing file hashes
        drive_service: Google Drive API service
        stats: Statistics dictionary to update

    Returns:
        List of files that need processing
    """
    files_to_process = []

    for file in files:
        file_id = file["id"]

        # For new files, no need to verify hash
        if file_id not in existing_hashes:
            files_to_process.append(file)
            continue

        # For potentially modified files, download and verify hash
        try:
            file_content = download_file_from_drive(drive_service, file_id, file["mimeType"])
            content_hash = hashlib.sha256(file_content).hexdigest()

            if content_hash != existing_hashes[file_id]["hash"]:
                files_to_process.append(file)
            else:
                # File was modified but content is the same (e.g., permissions change)
                stats["unchanged"] += 1
                stats["modified"] -= 1
        except Exception as e:
            print(f"Error verifying hash for {file['name']}: {e}")
            # If error, process the file to be safe
            files_to_process.append(file)

    return files_to_process


def download_file_from_drive(drive_service: Any, file_id: str, mime_type: str) -> bytes:
    """Download file from Google Drive.

    Args:
        drive_service: Google Drive API service
        file_id: File ID
        mime_type: MIME type of the file

    Returns:
        File content as bytes
    """
    if mime_type.startswith("application/vnd.google-apps"):
        # Google Workspace file - needs export
        # Will be handled by specific parser
        return b""
    else:
        request = drive_service.files().get_media(fileId=file_id)
        return request.execute()


def process_file_by_type(mime_type: str, file_id: str, file_name: str, drive_service: Any) -> str:
    """Route file to appropriate parser based on MIME type.

    Args:
        mime_type: MIME type of the file
        file_id: File ID
        file_name: File name
        drive_service: Google Drive API service

    Returns:
        Extracted text from the file
    """
    from .parsers import get_file_type_config

    config = get_file_type_config()

    if mime_type not in config:
        print(f"Unsupported file type: {mime_type} for file {file_name}")
        return ""

    parser_config = config[mime_type]
    parser = parser_config["parser"]
    needs_drive = parser_config["needs_drive"]

    try:
        if needs_drive:
            # Parser needs Drive service (Google Workspace files)
            return parser(drive_service, file_id, file_name)
        else:
            # Download file and parse
            file_content = download_file_from_drive(drive_service, file_id, mime_type)
            return parser(file_content, file_name)
    except Exception as e:
        print(f"Error processing file {file_name}: {e}")
        return ""


def create_chunks_with_metadata(
    text: str,
    file_id: str,
    file_name: str,
    mime_type: str,
    modified_time: str,
    web_link: str,
    file_path: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[dict[str, Any]]:
    """Create text chunks with metadata.

    Args:
        text: Text to chunk
        file_id: File ID
        file_name: File name
        mime_type: MIME type
        modified_time: Last modified time
        web_link: Web view link
        file_path: File path in Drive
        chunk_size: Chunk size in characters
        chunk_overlap: Chunk overlap in characters

    Returns:
        List of chunk dictionaries with metadata
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
    )

    chunks = splitter.split_text(text)
    content_hash = hashlib.sha256(text.encode()).hexdigest()

    chunk_list = []
    for i, chunk in enumerate(chunks):
        chunk_dict = {
            "id": f"{file_id}_chunk_{i}",
            "document_id": file_id,
            "chunk_index": i,
            "content": chunk,
            "document_name": file_name,
            "document_type": mime_type,
            "file_mtime": modified_time,
            "web_link": web_link,
            "document_path": file_path,
            "content_hash": content_hash,
            "chunk_size": len(chunk),
        }
        chunk_list.append(chunk_dict)

    return chunk_list


@retry.Retry(deadline=300)
def generate_embeddings(df: pd.DataFrame, project_id: str, location: str) -> pd.DataFrame:
    """Generate embeddings using Vertex AI.

    Args:
        df: DataFrame with content column
        project_id: GCP project ID
        location: GCP location

    Returns:
        DataFrame with embeddings column added
    """
    from google.cloud import aiplatform
    from vertexai.language_models import TextEmbeddingInput, TextEmbeddingModel

    aiplatform.init(project=project_id, location=location)

    model = TextEmbeddingModel.from_pretrained("text-embedding-005")

    # Process in batches
    batch_size = 250
    embeddings = []

    for i in range(0, len(df), batch_size):
        batch = df.iloc[i : i + batch_size]
        inputs = [
            TextEmbeddingInput(text=text, task_type="RETRIEVAL_DOCUMENT")
            for text in batch["content"]
        ]
        batch_embeddings = model.get_embeddings(inputs)
        embeddings.extend([emb.values for emb in batch_embeddings])

    df["embedding"] = embeddings
    return df


def store_to_bigquery(df: pd.DataFrame, project_id: str, dataset: str, table: str) -> None:
    """Store DataFrame to BigQuery.

    Args:
        df: DataFrame to store
        project_id: GCP project ID
        dataset: Dataset name
        table: Table name
    """
    from google.cloud import bigquery

    client = bigquery.Client(project=project_id)
    table_id = f"{project_id}.{dataset}.{table}"

    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        schema=[
            bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("document_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("chunk_index", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("content", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("document_name", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("document_type", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("file_mtime", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("web_link", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("document_path", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("content_hash", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("chunk_size", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("embedding", "FLOAT64", mode="REPEATED"),
        ],
    )

    job = client.load_table_from_dataframe(df, table_id, job_config=job_config)
    job.result()
    print(f"Loaded {len(df)} rows into {table_id}")


def export_to_jsonl(
    project_id: str, dataset: str, table: str, embedding_column: str, schedule_time: str
) -> str:
    """Export from BigQuery to JSONL for Discovery Engine.

    Args:
        project_id: GCP project ID
        dataset: Dataset name
        table: Table name
        embedding_column: Name of embedding column
        schedule_time: Schedule time for unique filename

    Returns:
        GCS path to JSONL file
    """
    from google.cloud import bigquery, storage

    client = bigquery.Client(project=project_id)

    # Generate unique filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = f"gs://{project_id}-incident-response-rag/processed/documents_{timestamp}.jsonl"

    query = f"""
    SELECT
        id,
        document_id,
        chunk_index,
        content,
        document_name,
        document_type,
        file_mtime,
        web_link,
        document_path,
        content_hash,
        chunk_size,
        {embedding_column}
    FROM `{project_id}.{dataset}.{table}`
    """

    # Extract to GCS
    extract_job = client.extract_table(
        query,
        output_path,
        job_config=bigquery.ExtractJobConfig(destination_format=bigquery.DestinationFormat.NEWLINE_DELIMITED_JSON),
    )
    extract_job.result()

    print(f"Exported to {output_path}")
    return output_path
