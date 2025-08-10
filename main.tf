resource "random_id" "bucket_suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "reports_generated" {
  bucket = "${var.report_bucket_name}-${random_id.bucket_suffix.hex}"
}

resource "aws_sns_topic" "findings" {
  name = "public-exposure-findings"
}

resource "aws_sns_topic_subscription" "email_sub" {
  topic_arn = aws_sns_topic.findings.arn
  protocol  = "email"
  endpoint  = var.sns_email
}

resource "aws_iam_role" "lambda_exec_role" {
  name = "lambda-public-exposure-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic_exec" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "lambda_vpc_access" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonVPCReadOnlyAccess"
}

resource "aws_iam_policy" "lambda_network_scan_policy" {
  name        = "lambda-network-scan-policy"
  description = "Custom policy for Lambda to scan VPCs, subnets, ENIs, and security groups"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = [
          "ec2:DescribeVpcs",
          "ec2:DescribeSubnets",
          "ec2:DescribeAddresses",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DescribeSecurityGroups",
          "ec2:DescribeInternetGateways",
          "ec2:DescribeNatGateways",
          "ec2:DescribeRouteTables"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_network_scan_permissions" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = aws_iam_policy.lambda_network_scan_policy.arn
}

resource "aws_lambda_function" "public_exposure_check" {
  filename         = "lambda.zip"
  function_name    = var.lambda_function_name
  role             = aws_iam_role.lambda_exec_role.arn
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.9"
  source_code_hash = filebase64sha256("lambda.zip")
  timeout          = 300

  environment {
    variables = {
      BUCKET_NAME = aws_s3_bucket.reports_generated.bucket
      SNS_TOPIC   = aws_sns_topic.findings.arn
    }
  }
}

resource "aws_cloudwatch_event_rule" "schedule_rule" {
  name                = "public-exposure-scan-schedule"
  schedule_expression = "rate(1 day)"
}

resource "aws_cloudwatch_event_target" "lambda_target" {
  rule      = aws_cloudwatch_event_rule.schedule_rule.name
  target_id = "public-exposure-lambda"
  arn       = aws_lambda_function.public_exposure_check.arn
}

resource "aws_lambda_permission" "allow_cloudwatch" {
  statement_id  = "AllowExecutionFromCloudWatch"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.public_exposure_check.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.schedule_rule.arn
}