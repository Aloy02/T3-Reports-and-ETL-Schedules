provider "aws" {
  region = var.AWS_REGION
}

# ------------------------------------------------------------------------------
# AWS S3 Bucket
# ------------------------------------------------------------------------------

resource "aws_s3_bucket" "main" {
  bucket        = var.S3_TARGET_BUCKET
  force_destroy = false

  tags = merge(
    var.S3_TAGS,
    {
      Name = var.S3_TARGET_BUCKET
    }
  )
}

# ------------------------------------------------------------------------------
# AWS Glue Database and Crawler
# ------------------------------------------------------------------------------

# 1. Glue Database
resource "aws_glue_catalog_database" "glue_db" {
  name = "${var.ENVIRONMENT_PREFIX}-glue-db"
}

# 2. IAM Role for Glue
resource "aws_iam_role" "glue_role" {
  name = "AWSGlueServiceRole-${var.ENVIRONMENT_PREFIX}-crawler"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "glue.amazonaws.com"
        }
      }
    ]
  })

  tags = var.S3_TAGS
}

# AWS Managed Policy Attachment
resource "aws_iam_role_policy_attachment" "glue_service_attachment" {
  role       = aws_iam_role.glue_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

# Custom S3 Access Policy
resource "aws_iam_policy" "glue_s3_policy" {
  name        = "AWSGlueServiceRole-${var.ENVIRONMENT_PREFIX}-s3-access"
  description = "Grant AWS Glue access to s3://${var.S3_TARGET_BUCKET}/${var.S3_TARGET_PATH}"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject"
        ]
        Resource = "arn:aws:s3:::${var.S3_TARGET_BUCKET}/${var.S3_TARGET_PATH}*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = "arn:aws:s3:::${var.S3_TARGET_BUCKET}"
      }
    ]
  })

  tags = var.S3_TAGS
}

resource "aws_s3_object" "target_folder" {
  bucket = aws_s3_bucket.main.id
  key    = "${var.S3_TARGET_PATH}/" # Ensures trailing slash for folder prefix
}

resource "aws_iam_role_policy_attachment" "glue_s3_attachment" {
  role       = aws_iam_role.glue_role.name
  policy_arn = aws_iam_policy.glue_s3_policy.arn
}

# 3. Glue Crawler
resource "aws_glue_crawler" "crawler" {
  database_name = aws_glue_catalog_database.glue_db.name
  name          = "${var.ENVIRONMENT_PREFIX}-crawler"
  role          = aws_iam_role.glue_role.arn
  schedule      = ""

  s3_target {
    path = "s3://${var.S3_TARGET_BUCKET}/${var.S3_TARGET_PATH}"
  }

  tags = var.S3_TAGS

  # Force Terraform to wait until the S3 bucket and folder prefix exist
  depends_on = [
    aws_s3_bucket.main,
    aws_s3_object.target_folder
  ]
}

# ------------------------------------------------------------------------------
# Networking Datasources & ECR
# ------------------------------------------------------------------------------

data "aws_vpc" "c26-vpc" {
  filter {
    name   = "tag:Name"
    values = [var.VPC_NAME]
  }
}

data "aws_subnet" "subnet_1" {
  filter {
    name   = "tag:Name"
    values = [var.SUBNET_1_NAME]
  }
}

# Create ECR Repository
resource "aws_ecr_repository" "pipeline_repo" {
  name                 = "c26-aloysius-t3-pipeline-image"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = var.S3_TAGS
}

# ------------------------------------------------------------------------------
# ECS Resources
# ------------------------------------------------------------------------------

# Reference existing ECS Cluster
data "aws_ecs_cluster" "main" {
  cluster_name = "c26-ecs-cluster"
}

# IAM Role for ECS Task Execution (for pulling images and CloudWatch logs)
resource "aws_iam_role" "ecs_task_execution_role" {
  name = "${var.ENVIRONMENT_PREFIX}-ecs-pipeline-task-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })

  tags = var.S3_TAGS
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution_role_policy" {
  role       = aws_iam_role.ecs_task_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# IAM Role for ECS Task (Trust Policy ONLY)
resource "aws_iam_role" "ecs_task_role" {
  name = "${var.ENVIRONMENT_PREFIX}-ecs-pipeline-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })

  tags = var.S3_TAGS
}

# Policy for task to access S3 and Glue
resource "aws_iam_policy" "ecs_task_s3_glue_policy" {
  name        = "${var.ENVIRONMENT_PREFIX}-ecs-task-s3-glue-policy"
  description = "Grant ECS task full access to S3 bucket and Glue Crawler/Catalog"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3ObjectAccess"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject"
        ]
        Resource = [
          "arn:aws:s3:::${var.S3_TARGET_BUCKET}",
          "arn:aws:s3:::${var.S3_TARGET_BUCKET}/*"
        ]
      },
      {
        Sid    = "S3ListBucket"
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = "arn:aws:s3:::${var.S3_TARGET_BUCKET}"
      },
      {
        Sid    = "GlueCrawlerAccess"
        Effect = "Allow"
        Action = [
          "glue:GetCrawler",
          "glue:StartCrawler"
        ]
        Resource = aws_glue_crawler.crawler.arn
      },
      {
        Sid    = "GlueCatalogAccess"
        Effect = "Allow"
        Action = [
          "glue:GetDatabase",
          "glue:GetTable",
          "glue:GetPartitions",
          "glue:CreatePartition",
          "glue:BatchCreatePartition"
        ]
        Resource = "*"
      }
    ]
  })

  tags = var.S3_TAGS
}

resource "aws_iam_role_policy_attachment" "ecs_task_s3_glue_attachment" {
  role       = aws_iam_role.ecs_task_role.name
  policy_arn = aws_iam_policy.ecs_task_s3_glue_policy.arn
}

# CloudWatch Log Group for ECS
resource "aws_cloudwatch_log_group" "ecs_log_group" {
  name              = "/ecs/${var.ENVIRONMENT_PREFIX}-pipeline"
  retention_in_days = 7

  tags = merge(
    var.S3_TAGS,
    {
      Name = "${var.ENVIRONMENT_PREFIX}-ecs-logs"
    }
  )
}

# Security Group for ECS tasks
resource "aws_security_group" "ecs_tasks" {
  name        = "${var.ENVIRONMENT_PREFIX}-ecs-tasks-sg"
  description = "Security group for ECS tasks"
  vpc_id      = data.aws_vpc.c26-vpc.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    var.S3_TAGS,
    {
      Name = "${var.ENVIRONMENT_PREFIX}-ecs-tasks-sg"
    }
  )
}

# ECS Task Definition (Fargate)
resource "aws_ecs_task_definition" "pipeline_task" {
  family                   = "${var.ENVIRONMENT_PREFIX}-pipeline-task"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([
    {
      name      = "${var.ENVIRONMENT_PREFIX}-pipeline-container"
      image     = "${aws_ecr_repository.pipeline_repo.repository_url}:latest"
      essential = true
      environment = [
        {
          name  = "DB_HOST"
          value = var.DB_HOST
        },
        {
          name  = "DB_NAME"
          value = var.DB_NAME
        },
        {
          name  = "DB_USER"
          value = var.DB_USER
        },
        {
          name  = "DB_PORT"
          value = var.DB_PORT
        },
        {
          name  = "DB_PASSWORD"
          value = var.DB_PASSWORD
        },
        {
          name  = "AWS_DEFAULT_REGION"
          value = var.AWS_REGION
        },
        {
          name  = "S3_TARGET_BUCKET"
          value = var.S3_TARGET_BUCKET
        },
        {
          name  = "S3_TARGET_PATH"
          value = var.S3_TARGET_PATH
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs_log_group.name
          "awslogs-region"        = var.AWS_REGION
          "awslogs-stream-prefix" = "ecs"
        }
      }
    }
  ])

  tags = merge(
    var.S3_TAGS,
    {
      Name = "${var.ENVIRONMENT_PREFIX}-pipeline-task"
    }
  )
}

# ------------------------------------------------------------------------------
# EventBridge Scheduler to trigger ECS Task
# ------------------------------------------------------------------------------

# EventBridge Schedule (Replaces both event_rule and event_target)
resource "aws_scheduler_schedule" "trigger_ecs" {
  name       = "${var.ENVIRONMENT_PREFIX}-trigger-pipeline"
  group_name = "default"

  # schedule_expression          = "cron(*/5 * * * ? *)"
  schedule_expression          = "cron(0 */3 * * ? *)"
  schedule_expression_timezone = "UTC"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = data.aws_ecs_cluster.main.arn
    role_arn = aws_iam_role.eventbridge_ecs_role.arn

    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.pipeline_task.arn
      launch_type         = "FARGATE"

      network_configuration {
        subnets          = [data.aws_subnet.subnet_1.id]
        security_groups  = [aws_security_group.ecs_tasks.id]
        assign_public_ip = true
      }
    }
  }
}

# IAM Role for EventBridge Scheduler to invoke ECS
resource "aws_iam_role" "eventbridge_ecs_role" {
  name = "${var.ENVIRONMENT_PREFIX}-eventbridge-ecs-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "scheduler.amazonaws.com"
        }
      }
    ]
  })

  tags = var.S3_TAGS
}

# IAM Policy for EventBridge Scheduler to run ECS tasks
resource "aws_iam_role_policy" "eventbridge_ecs_policy" {
  name   = "${var.ENVIRONMENT_PREFIX}-eventbridge-ecs-policy"
  role   = aws_iam_role.eventbridge_ecs_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecs:RunTask"
        ]
        Resource = [
          aws_ecs_task_definition.pipeline_task.arn,
          "${aws_ecs_task_definition.pipeline_task.arn}:*" # Allows execution of task revision wildcards
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "iam:PassRole"
        ]
        Resource = [
          aws_iam_role.ecs_task_execution_role.arn,
          aws_iam_role.ecs_task_role.arn
        ]
      }
    ]
  })
}