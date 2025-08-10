variable "aws_region" {
  default = "us-east-1"
}

variable "report_bucket_name" {
  default = "public-exposure-reports-demo"
}

variable "sns_email" {
  description = "Email address to receive alerts"
}

variable "lambda_function_name" {
  default = "public_exposure_checker"
}