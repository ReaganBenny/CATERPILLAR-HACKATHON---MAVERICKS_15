variable "aws_region" {
  description = "Region to deploy into. Cat dealers operate per-region, so this is the only value that changes between deployments."
  type        = string
  default     = "ap-south-1"
}

variable "project_name" {
  description = "Name prefix for all resources."
  type        = string
  default     = "smart-rental-tracking"
}

variable "environment" {
  description = "Deployment environment."
  type        = string
  default     = "dev"
}

variable "alert_email" {
  description = "Email subscribed to overdue/anomaly alerts. AWS sends a confirmation link that must be clicked before delivery starts."
  type        = string
  default     = ""
}

variable "sweep_schedule" {
  description = "EventBridge schedule for the fleet sweep. Default is 08:00 UTC daily."
  type        = string
  default     = "cron(0 8 * * ? *)"
}

variable "pandas_layer_arn" {
  description = <<-EOT
    ARN of the AWS-managed SDK-for-pandas layer. The loader depends on pandas,
    which exceeds the inline Lambda package limit, so it must come from a layer.
    Region- and version-specific; find yours with:
      aws lambda list-layer-versions --layer-name AWSSDKPandas-Python311 --region <region>
    Leave empty to deploy without it (the Lambda will fail on import until set).
  EOT
  type        = string
  default     = ""
}

variable "monthly_budget_usd" {
  description = "Monthly spend cap that triggers a budget alert. Guardrail against a hackathon surprise bill."
  type        = number
  default     = 5
}

variable "log_retention_days" {
  description = "CloudWatch log retention. Short by default to stay inside free tier."
  type        = number
  default     = 7
}
