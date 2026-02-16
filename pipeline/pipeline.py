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

"""Incident Response RAG Pipeline - Kubeflow Pipeline Definition."""

from components.ingest_data import ingest_data
from components.process_drive_documents import process_drive_documents
from kfp import dsl


@dsl.pipeline(
    description="A pipeline to process incident response documents from Google Drive and ingest them into Discovery Engine for RAG"
)
def incident_response_pipeline(
    project_id: str,
    location: str,
    drive_folder_id: str,
    impersonation_user: str,
    chunk_size: int = 1500,
    chunk_overlap: int = 200,
    destination_table: str = "incident_response_embeddings",
    destination_dataset: str = "incident_response_rag",
    data_store_region: str = "global",
    data_store_id: str = "incident-response-datastore",
) -> None:
    """Process incident response documents from Google Drive and ingest into Discovery Engine.

    This pipeline:
    1. Lists documents from Google Drive (runbooks, playbooks, post-mortems)
    2. Extracts text from various formats (PDF, Word, Excel, Google Docs/Sheets)
    3. Performs intelligent deduplication (timestamp + hash-based)
    4. Chunks text for optimal retrieval
    5. Generates embeddings using Vertex AI text-embedding-005
    6. Stores in BigQuery for analytics
    7. Exports to Discovery Engine for RAG-powered search

    Args:
        project_id: GCP project ID
        location: BigQuery and Vertex AI location (e.g., us-central1)
        drive_folder_id: Google Drive folder ID containing incident response docs
        impersonation_user: User email to impersonate for Drive access
        chunk_size: Size of text chunks in characters (default: 1500)
        chunk_overlap: Overlap between chunks in characters (default: 200)
        destination_table: BigQuery table name (default: incident_response_embeddings)
        destination_dataset: BigQuery dataset name (default: incident_response_rag)
        data_store_region: Discovery Engine region (default: global)
        data_store_id: Discovery Engine data store ID (default: incident-response-datastore)
    """

    # Step 1: Process incident response documents from Google Drive
    # - Fetch from Google Drive (using service account with domain-wide delegation)
    # - Extract text from various formats (Google Docs, PDFs, Sheets, etc.)
    # - Intelligent deduplication (timestamp + hash-based)
    # - Chunk text for optimal retrieval
    # - Generate embeddings with text-embedding-005
    # - Store in BigQuery with incremental processing
    # - Export to JSONL for Discovery Engine
    processed_data = (
        process_drive_documents(
            project_id=project_id,
            schedule_time=dsl.PIPELINE_JOB_SCHEDULE_TIME_UTC_PLACEHOLDER,
            drive_folder_id=drive_folder_id,
            impersonation_user=impersonation_user,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            destination_dataset=destination_dataset,
            destination_table=destination_table,
            location=location,
            embedding_column="embedding",
        )
        .set_caching_options(enable_caching=False)  # Always run fresh for data pipeline
        .set_retry(num_retries=2)
        .set_memory_limit("32G")  # 32GB RAM for processing
        .set_cpu_limit("8")  # 8 vCPUs for faster processing
    )

    # Step 2: Ingest processed data into Discovery Engine for RAG
    # - Updates schema if needed (idempotent)
    # - Imports documents from JSONL
    # - Builds search index
    (
        ingest_data(
            project_id=project_id,
            data_store_region=data_store_region,
            input_files=processed_data.output,
            data_store_id=data_store_id,
            embedding_column="embedding",
        )
        .set_caching_options(enable_caching=False)  # Must run after processing
        .set_retry(num_retries=2)
    )
