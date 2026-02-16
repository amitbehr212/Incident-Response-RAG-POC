.PHONY: help install lint test compile submit clean

help:
	@echo "Incident Response RAG Pipeline - Make Commands"
	@echo ""
	@echo "Available commands:"
	@echo "  make install       Install dependencies using uv"
	@echo "  make lint          Run linting (ruff + mypy)"
	@echo "  make test          Run tests"
	@echo "  make compile       Compile pipeline to JSON"
	@echo "  make submit        Submit pipeline to Vertex AI"
	@echo "  make clean         Clean generated files"

install:
	@echo "Installing dependencies with uv..."
	uv sync

lint:
	@echo "Running linters..."
	uv run ruff check pipeline/
	uv run ruff format pipeline/ --check
	uv run mypy pipeline/

lint-fix:
	@echo "Fixing linting issues..."
	uv run ruff check pipeline/ --fix
	uv run ruff format pipeline/

test:
	@echo "Running tests..."
	uv run pytest tests/ -v

compile:
	@echo "Compiling pipeline..."
	uv run python -c "from kfp import compiler; from pipeline.pipeline import incident_response_pipeline; compiler.Compiler().compile(pipeline_func=incident_response_pipeline, package_path='incident_response_pipeline.json')"
	@echo "Pipeline compiled to: incident_response_pipeline.json"

submit:
	@echo "Submitting pipeline to Vertex AI..."
	@test -n "$(PROJECT_ID)" || (echo "ERROR: PROJECT_ID not set. Usage: make submit PROJECT_ID=your-project-id DRIVE_FOLDER_ID=folder-id IMPERSONATION_USER=user@domain.com" && exit 1)
	@test -n "$(DRIVE_FOLDER_ID)" || (echo "ERROR: DRIVE_FOLDER_ID not set" && exit 1)
	@test -n "$(IMPERSONATION_USER)" || (echo "ERROR: IMPERSONATION_USER not set" && exit 1)
	uv run python pipeline/submit_pipeline.py \
		--project-id $(PROJECT_ID) \
		--location $(LOCATION) \
		--drive-folder-id $(DRIVE_FOLDER_ID) \
		--impersonation-user $(IMPERSONATION_USER)

clean:
	@echo "Cleaning generated files..."
	rm -f incident_response_pipeline.json
	rm -rf .pytest_cache
	rm -rf **/__pycache__
	rm -rf .mypy_cache
	rm -rf .ruff_cache

# Default location
LOCATION ?= us-central1
