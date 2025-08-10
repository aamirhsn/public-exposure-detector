output "report_bucket" {
  value = aws_s3_bucket.reports.bucket
}

output "lambda_function_name" {
  value = aws_lambda_function.public_exposure_check.function_name
}

output "sns_topic_arn" {
  value = aws_sns_topic.findings.arn
}