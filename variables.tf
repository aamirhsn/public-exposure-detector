variable "aws_region" {
  description = "AWS region to deploy resources"
  default     = "us-east-1"
}

variable "lambda_s3_bucket" {
  description = "S3 bucket name where reports will be stored"
  default     = "public-exposure-reports-demo"
}

variable "sns_email" {
  description = "Email address for receiving alerts"
}