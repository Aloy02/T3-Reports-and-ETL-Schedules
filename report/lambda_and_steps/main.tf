# -----------------------------------------------------------------------------
# 1. Data Sources
# -----------------------------------------------------------------------------
data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

data "aws_ecr_repository" "report_generator_repo" {
  name = "${var.ENVIRONMENT_PREFIX}-report-generator"
}

# -----------------------------------------------------------------------------
# 2. IAM Role & Policies for Lambda Execution
# -----------------------------------------------------------------------------
resource "aws_iam_role" "lambda_exec_role" {
  name = "${var.ENVIRONMENT_PREFIX}-report-generator-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

# Attach AWS Basic Lambda Execution policy (CloudWatch logs)
resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Inline Policy for S3, Athena, AWS Glue, and Amazon SES permissions
resource "aws_iam_role_policy" "lambda_permissions" {
  name = "${var.ENVIRONMENT_PREFIX}-report-generator-policy"
  role = aws_iam_role.lambda_exec_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3BucketAccess"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket",
          "s3:GetBucketLocation",
          "s3:ListMultipartUploadParts",
          "s3:AbortMultipartUpload",
          "s3:DeleteObject",
        ]
        Resource = [
          "arn:aws:s3:::c26-aloysius-t3-s3",
          "arn:aws:s3:::c26-aloysius-t3-s3/*"
        ]
      },
      {
        Sid    = "AthenaQueryAccess"
        Effect = "Allow"
        Action = [
          "athena:StartQueryExecution",
          "athena:GetQueryExecution",
          "athena:GetQueryResults",
          "athena:StopQueryExecution",
          "athena:GetWorkGroup",
          "athena:GetDataCatalog",
          "glue:GetDatabase",
          "glue:GetTable",
          "glue:GetTables",
          "glue:GetPartitions",
          "glue:CreateTable",
          "glue:BatchCreatePartition",
          "glue:DeleteTable"
        ]
        Resource = "*"
      },
      {
        Sid    = "SESEmailAccess"
        Effect = "Allow"
        Action = [
          "ses:SendEmail",
          "ses:SendRawEmail"
        ]
        Resource = "*"
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# 3. AWS Lambda Function (Container Image)
# -----------------------------------------------------------------------------
resource "aws_lambda_function" "report_generator" {
  function_name                  = "${var.ENVIRONMENT_PREFIX}-report-generator"
  role                           = aws_iam_role.lambda_exec_role.arn
  package_type                   = "Image"
  image_uri                      = "${data.aws_ecr_repository.report_generator_repo.repository_url}:latest"
  memory_size                    = 512
  timeout                        = 120
  reserved_concurrent_executions = -1

  environment {
    variables = {
      S3_BUCKET_NAME     = "c26-aloysius-t3-s3"
      DATABASE_NAME      = "c26-aloysius-t3-glue-db"
      S3_OUTPUT_LOCATION = "s3://c26-aloysius-t3-s3/t3-output/"
      SES_SENDER_EMAIL   = var.SENDER_EMAIL
      RECIPIENT_EMAIL    = var.RECIPIENT_EMAIL
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.lambda_logs,
    aws_iam_role_policy.lambda_permissions,
    data.aws_ecr_repository.report_generator_repo
  ]
}

# -----------------------------------------------------------------------------
# 4. SES Email Identity (Verification)
# -----------------------------------------------------------------------------
resource "aws_ses_email_identity" "sender_email" {
  email = var.SENDER_EMAIL
}

resource "aws_ses_email_identity" "receiver_email" {
  email = var.RECIPIENT_EMAIL
}

# -----------------------------------------------------------------------------
# 5. EventBridge Scheduler (Triggers State Machine Daily at 09:30 UTC)
# -----------------------------------------------------------------------------

# IAM Role so EventBridge can execute your Step Functions State Machine
resource "aws_iam_role" "eventbridge_scheduler_role" {
  name = "${var.ENVIRONMENT_PREFIX}-eventbridge-schedule-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "scheduler.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })
}

# Policy granting EventBridge permissions to start Step Functions execution
resource "aws_iam_role_policy" "eventbridge_scheduler_policy" {
  name = "${var.ENVIRONMENT_PREFIX}-eventbridge-schedule-policy"
  role = aws_iam_role.eventbridge_scheduler_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "states:StartExecution"
        Resource = aws_sfn_state_machine.morning_report_state_machine.arn
      }
    ]
  })
}

# EventBridge Schedule set for 9:30 AM UTC daily
resource "aws_scheduler_schedule" "daily_report_schedule" {
  name       = "${var.ENVIRONMENT_PREFIX}-daily-report-schedule"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = "cron(30 9 * * ? *)"
  schedule_expression_timezone = "UTC"

  target {
    # Changed target to Step Functions State Machine ARN
    arn      = aws_sfn_state_machine.morning_report_state_machine.arn
    role_arn = aws_iam_role.eventbridge_scheduler_role.arn
  }
}

# -----------------------------------------------------------------------------
# 6. Step Functions State Machine & IAM Role
# -----------------------------------------------------------------------------

# IAM Role for Step Functions State Machine
resource "aws_iam_role" "sfn_exec_role" {
  name = "${var.ENVIRONMENT_PREFIX}-sfn-exec-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "states.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

# Policy allowing State Machine to invoke Lambda and send emails via SES
resource "aws_iam_role_policy" "sfn_permissions" {
  name = "${var.ENVIRONMENT_PREFIX}-sfn-permissions-policy"
  role = aws_iam_role.sfn_exec_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "LambdaInvokeAccess"
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = [
          aws_lambda_function.report_generator.arn,
          "${aws_lambda_function.report_generator.arn}:*"
        ]
      },
      {
        Sid    = "SESSendEmailAccess"
        Effect = "Allow"
        Action = [
          "ses:SendEmail",
          "ses:SendRawEmail"
        ]
        Resource = "*"
      }
    ]
  })
}

# Step Functions State Machine
resource "aws_sfn_state_machine" "morning_report_state_machine" {
  name     = "c26-aloysius-state-morning-report"
  role_arn = aws_iam_role.sfn_exec_role.arn

  definition = jsonencode({
    Comment = "A description of my state machine"
    StartAt = "Lambda Invoke"
    States = {
      "Lambda Invoke" = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Output   = "{% $states.result.Payload %}"
        Arguments = {
          Payload = {
            test = ""
          }
          # Dynamically references the Lambda function created in your Terraform file
          FunctionName = "${aws_lambda_function.report_generator.arn}:$LATEST"
        }
        Retry = [
          {
            ErrorEquals = [
              "Lambda.ServiceException",
              "Lambda.AWSLambdaException",
              "Lambda.SdkClientException",
              "Lambda.TooManyRequestsException"
            ]
            IntervalSeconds = 1
            MaxAttempts     = 3
            BackoffRate     = 2
            JitterStrategy  = "FULL"
          }
        ]
        Next = "SendEmail"
      }
      "SendEmail" = {
        Type = "Task"
        Arguments = {
          Source = var.SENDER_EMAIL
          Destination = {
            ToAddresses = [
              var.RECIPIENT_EMAIL
            ]
          }
          Message = {
            Subject = {
              Data = "{% $states.input.email_subject %}"
            }
            Body = {
              Html = {
                Data = "{% $states.input.email_body_html %}"
              }
              Text = {
                Data = "{% $states.input.email_body_text %}"
              }
            }
          }
        }
        Resource = "arn:aws:states:::aws-sdk:ses:sendEmail"
        End      = true
      }
    }
    QueryLanguage = "JSONata"
  })

  depends_on = [
    aws_iam_role_policy.sfn_permissions
  ]
}