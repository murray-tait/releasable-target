resource "aws_iam_role_policy_attachment" "lambda_log_access" {
  role       = aws_iam_role.lambda_service_role.name
  policy_arn = aws_iam_policy.lambda_log_access.arn
}

resource "aws_iam_policy" "lambda_log_access" {
  name   = "${var.application_name}-lambda-CloudWatchWriteAccess"
  policy = <<-EOT
    {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Action": [
            "logs:PutLogEvents",
            "logs:CreateLogStream"
          ],
          "Resource": "arn:aws:logs:${module.common.aws_region}:${local.aws_account_id}:log-group:/aws/lambda/${aws_lambda_function.lambda.function_name}:*",
          "Effect": "Allow"
        },
        {
          "Action": [
            "xray:PutTraceSegments",
            "xray:PutTelemetryRecords"
          ],
          "Resource": "*",
          "Effect": "Allow"
        }
      ]
    }
EOT
}

#################################################################
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${aws_lambda_function.lambda.function_name}"
  retention_in_days = 14
}

#######################################################################

