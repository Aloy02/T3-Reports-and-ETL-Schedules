FROM python:3.14.7

WORKDIR /workspace

# Copy application files
COPY app ./app

WORKDIR /workspace/app

EXPOSE 8501

RUN pip install --no-cache-dir -r requirements.txt

CMD ["streamlit", "run", "app.py"]