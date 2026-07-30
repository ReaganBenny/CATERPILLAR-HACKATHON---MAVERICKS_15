output "account_id" {
  description = "Account this stack targets — check it before applying."
  value       = data.aws_caller_identity.current.account_id
}

output "dynamodb_table" {
  description = "Asset state table name."
  value       = aws_dynamodb_table.assets.name
}

output "sns_topic_arn" {
  description = "Set this as SNS_TOPIC_ARN when running the sweep locally."
  value       = aws_sns_topic.alerts.arn
}

output "lambda_function_name" {
  description = "Invoke manually with: aws lambda invoke --function-name <this> --payload '{\"today\":\"2025-06-01\"}' out.json"
  value       = aws_lambda_function.sweep.function_name
}

output "log_group" {
  description = "CloudWatch log group for the sweep."
  value       = aws_cloudwatch_log_group.lambda.name
}

output "email_confirmation_required" {
  description = "Whether an SNS subscription is pending email confirmation."
  value       = var.alert_email == "" ? "no email configured" : "check ${var.alert_email} and click the confirmation link"
}
