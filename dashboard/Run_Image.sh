docker run --rm \
    -p 8501:8501 \
    --env-file .env \
    -v ~/.aws:/root/.aws:ro \
    t3-dashboard