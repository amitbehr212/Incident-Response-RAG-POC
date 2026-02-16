FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy pipeline code
COPY pipeline/ /app/pipeline/
COPY pyproject.toml /app/

# Install Python dependencies
RUN pip install --no-cache-dir \
    kfp>=2.10.0 \
    google-cloud-aiplatform>=1.116.0 \
    google-auth>=2.0.0 \
    google-api-python-client>=2.0.0 \
    pymupdf>=1.23.0 \
    python-docx>=1.1.0 \
    openpyxl>=3.1.0 \
    Pillow>=10.0.0 \
    pytesseract>=0.3.10 \
    langchain-text-splitters>=1.0.0 \
    google-cloud-bigquery>=3.0 \
    google-cloud-discoveryengine>=0.11.0 \
    google-cloud-storage>=2.10.0

# Run pipeline submission script
ENTRYPOINT ["python", "pipeline/submit_pipeline.py"]
