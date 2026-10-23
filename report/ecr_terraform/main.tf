resource "aws_ecr_repository" "report_generator_repo" {
  name                 = "${var.ENVIRONMENT_PREFIX}-report-generator"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  # Automatically scan images for vulnerabilities upon push
  image_scanning_configuration {
    scan_on_push = true
  }

  tags = merge(
    var.S3_TAGS,
    {
      Name = "${var.ENVIRONMENT_PREFIX}-report-generator-repo"
    }
  )
}