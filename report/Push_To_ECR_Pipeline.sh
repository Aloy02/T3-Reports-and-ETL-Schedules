echo "Authenticating..."
aws ecr get-login-password --region eu-west-2 | docker login --username AWS --password-stdin 129033205317.dkr.ecr.eu-west-2.amazonaws.com
echo "Authentication completed."

echo "Building Docker image for t3-report-generator..."
docker buildx build --provenance=false --platform linux/amd64 -t t3-report-generator .
echo "Docker image built successfully."

echo "Tagging Docker image for ECR repository..."
docker tag t3-report-generator:latest 129033205317.dkr.ecr.eu-west-2.amazonaws.com/c26-aloysius-t3-report-generator:latest
echo "Docker image tagged successfully."

echo "Pushing Docker image to ECR repository..."
docker push 129033205317.dkr.ecr.eu-west-2.amazonaws.com/c26-aloysius-t3-report-generator:latest
echo "Docker image pushed successfully."