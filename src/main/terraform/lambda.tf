resource "aws_iam_role_policy_attachment" "lambda_log_access" {
  role       = aws_iam_role.lambda_service_role.name
  policy_arn = aws_iam_policy.lambda_log_access.arn
}

resource "aws_iam_policy" "lambda_log_access" {
  name   = "AllowLambdaToWriteToLogs.${var.application_name}"
  policy = data.template_file.lambda_service_policy.rendered
}

data "template_file" "lambda_service_policy" {
  template = file("policies/lambda_service_policy.json")
}

#################################################################

resource "aws_lambda_function" "main" {
  function_name = var.application_name
  runtime       = "provided"
  handler       = "handler"
  timeout       = "30"
  role          = aws_iam_role.lambda_service_role.arn
  s3_bucket     = module.common.destination_builds_bucket_name
  s3_key        = "builds/${var.application_name}/refs/branch/${terraform.workspace}/dist.zip"
}

resource "aws_iam_role" "lambda_service_role" {
  name               = "LambdaserviceRole.${var.application_name}"
  assume_role_policy = data.template_file.lambda_service_role.rendered
}

data "template_file" "lambda_service_role" {
  template = file("policies/lambda_service_role.json")
}


