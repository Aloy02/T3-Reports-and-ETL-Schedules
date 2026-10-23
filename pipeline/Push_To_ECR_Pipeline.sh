REPO_NAME="c26-aloysius-t3-pipeline-image"
REGION="eu-west-2"

echo "Starting the pipeline for repository '$REPO_NAME' in region '$REGION'..."

echo "Logging in to AWS ECR..."

aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin 129033205317.dkr.ecr."$REGION".amazonaws.com

echo "Creating repository '$REPO_NAME' if it does not already exist..."
if aws ecr describe-repositories --repository-names "$REPO_NAME" --region "$REGION" 2>/dev/null; then
    echo "Repository already exists: $REPO_NAME"
else
    echo "Creating repository: $REPO_NAME"
    aws ecr create-repository --repository-name "$REPO_NAME" --region "$REGION"
fi

echo "Building the Docker image for repository '$REPO_NAME'..."

docker buildx build -t "$REPO_NAME" . --platform "linux/amd64"

echo "Tagging the Docker image for repository '$REPO_NAME'..."

docker tag "$REPO_NAME:latest" 129033205317.dkr.ecr."$REGION".amazonaws.com/"$REPO_NAME:latest"

echo "Pushing the Docker image for repository '$REPO_NAME'..."

docker push 129033205317.dkr.ecr."$REGION".amazonaws.com/"$REPO_NAME:latest"

echo "Pipeline for repository '$REPO_NAME' completed successfully."