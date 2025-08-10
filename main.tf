resource "random_id" "suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "reports" {
  bucket = "${var.lambda_s3_bucket}-${random_id.suffix.hex}"
}

resource "aws_iam_role" "lambda_exec_role" {
  name = "lambda-public-exposure-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Action = "sts:AssumeRole",
      Effect = "Allow",
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "lambda_vpc_permissions" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonVPCReadOnlyAccess"
}

resource "aws_iam_role_policy_attachment" "lambda_ipam_permissions" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonVPCIPAMFullAccess"
}

resource "aws_sns_topic" "findings" {
  name = "public-exposure-findings"
}

resource "aws_sns_topic_subscription" "email_sub" {
  topic_arn = aws_sns_topic.findings.arn
  protocol  = "email"
  endpoint  = var.sns_email
}

resource "aws_lambda_function" "public_exposure_check" {
  function_name    = "public-exposure-check"
  role             = aws_iam_role.lambda_exec_role.arn
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.11"
  filename         = "lambda.zip"
  source_code_hash = filebase64sha256("lambda.zip")
  timeout          = 300

  environment {
    variables = {
      REPORT_BUCKET = aws_s3_bucket.reports.bucket
      SNS_TOPIC_ARN = aws_sns_topic.findings.arn
    }
  }
}

resource "aws_cloudwatch_event_rule" "schedule" {
  name                = "public-exposure-schedule"
  schedule_expression = "rate(1 day)"
}

resource "aws_cloudwatch_event_target" "lambda_target" {
  rule      = aws_cloudwatch_event_rule.schedule.name
  target_id = "lambda"
  arn       = aws_lambda_function.public_exposure_check.arn
}

resource "aws_lambda_permission" "allow_event" {
  statement_id  = "AllowExecutionFromCloudWatch"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.public_exposure_check.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.schedule.arn
}