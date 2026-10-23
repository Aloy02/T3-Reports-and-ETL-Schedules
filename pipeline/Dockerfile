FROM python:3.14.7

WORKDIR /workspace

# Copy application files
COPY src ./src
RUN pip install --no-cache-dir -r ./src/requirements.txt

# Scripts use ../priv_* paths, so run from src/
WORKDIR /workspace/src
CMD ["python", "pipeline.py"]