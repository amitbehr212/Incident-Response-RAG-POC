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

"""Ingest processed documents into Discovery Engine."""

import time
from typing import Any

from kfp import dsl


@dsl.component(
    base_image="python:3.11-slim",
    packages_to_install=[
        "google-cloud-discoveryengine>=0.11.0",
        "google-cloud-storage>=2.10.0",
    ],
)
def ingest_data(
    project_id: str,
    data_store_region: str,
    input_files: str,
    data_store_id: str,
    embedding_column: str,
) -> None:
    """Ingest processed documents into Discovery Engine.

    Args:
        project_id: GCP project ID
        data_store_region: Discovery Engine data store region
        input_files: GCS path to JSONL file
        data_store_id: Discovery Engine data store ID
        embedding_column: Name of the embedding column
    """
    from google.api_core import exceptions
    from google.cloud import discoveryengine_v1 as discoveryengine

    # Initialize Discovery Engine client
    client = discoveryengine.DocumentServiceClient()

    # Data store parent path
    parent = client.branch_path(
        project=project_id,
        location=data_store_region,
        data_store=data_store_id,
        branch="default_branch",
    )

    print(f"Ingesting data into: {parent}")
    print(f"Input files: {input_files}")

    # Check if schema needs updating
    schema_service = discoveryengine.SchemaServiceClient()
    schema_parent = f"projects/{project_id}/locations/{data_store_region}/dataStores/{data_store_id}"

    try:
        # Get current schema
        schemas = schema_service.list_schemas(parent=schema_parent)
        current_schema = None
        for schema in schemas:
            current_schema = schema
            break

        needs_schema_update = False
        if current_schema:
            # Check if embedding field exists
            if embedding_column not in [field.field_path for field in current_schema.struct_schema.get("properties", {})]:
                needs_schema_update = True
        else:
            needs_schema_update = True

        if needs_schema_update:
            print("Updating schema to include embedding field...")
            update_schema(schema_service, schema_parent, embedding_column)
            # Wait for schema to be ready
            time.sleep(30)

    except Exception as e:
        print(f"Schema check/update failed (may be first run): {e}")

    # Import documents
    request = discoveryengine.ImportDocumentsRequest(
        parent=parent,
        gcs_source=discoveryengine.GcsSource(
            input_uris=[input_files],
            data_schema="content",
        ),
        reconciliation_mode=discoveryengine.ImportDocumentsRequest.ReconciliationMode.INCREMENTAL,
        auto_generate_ids=False,
        id_field="id",
    )

    try:
        # Start import operation (non-blocking for large datasets)
        operation = client.import_documents(request=request)
        print(f"Import operation started: {operation.operation.name}")
        print("Import will continue in background. Check Discovery Engine console for status.")

    except exceptions.AlreadyExists:
        print("Documents already exist, skipping import")
    except Exception as e:
        print(f"Import failed: {e}")
        raise


def update_schema(
    schema_service: Any, schema_parent: str, embedding_column: str
) -> None:
    """Update Discovery Engine schema to include embedding field.

    Args:
        schema_service: Schema service client
        schema_parent: Parent path for schema
        embedding_column: Name of embedding column to add
    """
    from google.cloud import discoveryengine_v1 as discoveryengine

    schema = discoveryengine.Schema(
        struct_schema={
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "document_id": {"type": "string"},
                "chunk_index": {"type": "integer"},
                "content": {"type": "string"},
                "document_name": {"type": "string"},
                "document_type": {"type": "string"},
                "file_mtime": {"type": "string"},
                "web_link": {"type": "string"},
                "document_path": {"type": "string"},
                "content_hash": {"type": "string"},
                "chunk_size": {"type": "integer"},
                embedding_column: {
                    "type": "array",
                    "items": {"type": "number"},
                },
            },
        }
    )

    request = discoveryengine.CreateSchemaRequest(
        parent=schema_parent,
        schema=schema,
        schema_id="default_schema",
    )

    try:
        operation = schema_service.create_schema(request=request)
        print("Schema creation started, waiting for completion...")
        # Wait for schema operation to complete (blocking)
        result = operation.result(timeout=300)
        print(f"Schema updated successfully: {result.name}")
    except Exception as e:
        print(f"Schema update failed: {e}")
        # If schema already exists, that's okay
        if "already exists" in str(e).lower():
            print("Schema already exists, continuing...")
        else:
            raise
