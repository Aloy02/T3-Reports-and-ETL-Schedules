docker buildx build -t t3-report-generator . --platform "linux/amd64"

docker run \
  -p 9000:8080 \
  --env-file .env \
  t3-report-generator