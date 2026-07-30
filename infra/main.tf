locals {
  name = "${var.project_name}-${var.environment}"
}

data "aws_caller_identity" "current" {}

# ---------------------------------------------------------------------------
# Asset state store
# ---------------------------------------------------------------------------
# On-demand billing: no idle cost, and the free tier covers a fleet this size.
resource "aws_dynamodb_table" "assets" {
  name         = "${local.name}-assets"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "equipment_id"

  attribute {
    name = "equipment_id"
    type = "S"
  }

  # Lets the dashboard query "everything currently at site S002" without a scan.
  attribute {
    name = "site_id"
    type = "S"
  }

  global_secondary_index {
    name            = "site-index"
    hash_key        = "site_id"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = false # dev only; enable for anything holding real rental records
  }
}

# ---------------------------------------------------------------------------
# Alerting
# ---------------------------------------------------------------------------
resource "aws_sns_topic" "alerts" {
  name = "${local.name}-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.alert_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# ---------------------------------------------------------------------------
# Lambda: scheduled overdue / anomaly sweep
# ---------------------------------------------------------------------------
data "archive_file" "lambda" {
  type        = "zip"
  output_path = "${path.module}/build/lambda.zip"

  source {
    content  = file("${path.module}/../src/lambda_handler.py")
    filename = "lambda_handler.py"
  }
  source {
    content  = file("${path.module}/../src/analytics.py")
    filename = "analytics.py"
  }
  source {
    content  = file("${path.module}/../src/loader.py")
    filename = "loader.py"
  }
  source {
    content  = file("${path.module}/../src/models.py")
    filename = "models.py"
  }
  source {
    content  = file("${path.module}/../data/equipment.csv")
    filename = "data/equipment.csv"
  }
}

resource "aws_iam_role" "lambda" {
  name = "${local.name}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

# Least privilege: publish to exactly one topic, read/write exactly one table.
resource "aws_iam_role_policy" "lambda" {
  name = "${local.name}-lambda-policy"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.lambda.arn}:*"
      },
      {
        Effect   = "Allow"
        Action   = "sns:Publish"
        Resource = aws_sns_topic.alerts.arn
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:Scan",
        ]
        Resource = [
          aws_dynamodb_table.assets.arn,
          "${aws_dynamodb_table.assets.arn}/index/*",
        ]
      },
    ]
  })
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.name}-sweep"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "sweep" {
  function_name    = "${local.name}-sweep"
  role             = aws_iam_role.lambda.arn
  handler          = "lambda_handler.handler"
  runtime          = "python3.11"
  timeout          = 30
  memory_size      = 256
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256

  layers = var.pandas_layer_arn == "" ? [] : [var.pandas_layer_arn]

  environment {
    variables = {
      SNS_TOPIC_ARN = aws_sns_topic.alerts.arn
      ASSETS_TABLE  = aws_dynamodb_table.assets.name
      LOG_LEVEL     = "INFO"
    }
  }

  depends_on = [
    aws_iam_role_policy.lambda,
    aws_cloudwatch_log_group.lambda,
  ]
}

# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_event_rule" "sweep" {
  name                = "${local.name}-sweep-schedule"
  description         = "Daily fleet sweep for overdue rentals and anomalies"
  schedule_expression = var.sweep_schedule
}

resource "aws_cloudwatch_event_target" "sweep" {
  rule      = aws_cloudwatch_event_rule.sweep.name
  target_id = "lambda"
  arn       = aws_lambda_function.sweep.arn
}

resource "aws_lambda_permission" "events" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.sweep.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.sweep.arn
}

# ---------------------------------------------------------------------------
# Monitoring: we monitor the monitor
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name          = "${local.name}-sweep-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_description   = "The fleet sweep failed — overdue alerts are not being delivered."
  alarm_actions       = [aws_sns_topic.alerts.arn]

  dimensions = {
    FunctionName = aws_lambda_function.sweep.function_name
  }
}

# Cost guardrail. A runaway bill is the most likely way this project hurts anyone.
resource "aws_budgets_budget" "monthly" {
  name         = "${local.name}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  dynamic "notification" {
    for_each = var.alert_email == "" ? [] : [1]
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = 80
      threshold_type             = "PERCENTAGE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = [var.alert_email]
    }
  }
}
