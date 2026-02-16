#!/usr/bin/env python3
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

"""Submit the incident response RAG pipeline to Vertex AI Pipelines."""

import argparse
import os

from google.cloud import aiplatform
from kfp import compiler

from pipeline import incident_response_pipeline


def submit_pipeline(
    project_id: str,
    location: str,
    drive_folder_id: str,
    impersonation_user: str,
    pipeline_root: str,
    service_account: str,
    enable_caching: bool = False,
) -> None:
    """Submit the pipeline to Vertex AI Pipelines.

    Args:
        project_id: GCP project ID
        location: GCP location for Vertex AI
        drive_folder_id: Google Drive folder ID
        impersonation_user: User email to impersonate
        pipeline_root: GCS path for pipeline artifacts
        service_account: Service account for pipeline execution
        enable_caching: Enable pipeline caching (default: False)
    """
    # Compile pipeline
    compiler.Compiler().compile(
        pipeline_func=incident_response_pipeline,
        package_path="incident_response_pipeline.json",
    )

    print(f"Pipeline compiled to: incident_response_pipeline.json")

    # Initialize Vertex AI
    aiplatform.init(
        project=project_id,
        location=location,
    )

    # Create pipeline job
    job = aiplatform.PipelineJob(
        display_name="incident-response-rag-pipeline",
        template_path="incident_response_pipeline.json",
        pipeline_root=pipeline_root,
        parameter_values={
            "project_id": project_id,
            "location": location,
            "drive_folder_id": drive_folder_id,
            "impersonation_user": impersonation_user,
        },
        enable_caching=enable_caching,
    )

    # Submit pipeline
    print(f"Submitting pipeline to Vertex AI Pipelines...")
    print(f"  Project: {project_id}")
    print(f"  Location: {location}")
    print(f"  Drive Folder: {drive_folder_id}")
    print(f"  Service Account: {service_account}")

    job.submit(service_account=service_account)

    print(f"Pipeline submitted successfully!")
    print(f"Pipeline URL: {job._dashboard_uri()}")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Submit incident response RAG pipeline")
    parser.add_argument("--project-id", required=True, help="GCP project ID")
    parser.add_argument("--location", default="us-central1", help="GCP location")
    parser.add_argument("--drive-folder-id", required=True, help="Google Drive folder ID")
    parser.add_argument("--impersonation-user", required=True, help="User email to impersonate")
    parser.add_argument(
        "--pipeline-root",
        help="GCS path for pipeline artifacts (default: gs://{project-id}-incident-response-rag/pipeline)",
    )
    parser.add_argument(
        "--service-account",
        help="Service account email (default: pipeline-sa@{project-id}.iam.gserviceaccount.com)",
    )
    parser.add_argument("--enable-caching", action="store_true", help="Enable pipeline caching")

    args = parser.parse_args()

    # Set defaults
    pipeline_root = args.pipeline_root or f"gs://{args.project_id}-incident-response-rag/pipeline"
    service_account = (
        args.service_account or f"pipeline-sa@{args.project_id}.iam.gserviceaccount.com"
    )

    submit_pipeline(
        project_id=args.project_id,
        location=args.location,
        drive_folder_id=args.drive_folder_id,
        impersonation_user=args.impersonation_user,
        pipeline_root=pipeline_root,
        service_account=service_account,
        enable_caching=args.enable_caching,
    )


if __name__ == "__main__":
    main()
