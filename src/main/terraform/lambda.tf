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
          "Resource": "arn:aws:logs:${module.common.aws_region}:${module.common.aws_account_id}:log-group:/aws/lambda/${aws_lambda_function.main.function_name}:*",
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
  name               = "${var.application_name}-lambda-executeRole"
  assume_role_policy = data.template_file.lambda_service_role.rendered
}

data "template_file" "lambda_service_role" {
  template = file("policies/lambda_service_role.json")
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${aws_lambda_function.main.function_name}"
  retention_in_days = 14
}

#######################################################################

resource "aws_api_gateway_deployment" "main" {
  rest_api_id = data.aws_api_gateway_rest_api.external_api.id

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_integration" "releasable" {
  rest_api_id = data.aws_api_gateway_rest_api.external_api.id
  resource_id = aws_api_gateway_resource.releasable.id

  http_method = aws_api_gateway_method.releasable.http_method

  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.main.invoke_arn
  content_handling        = null

  depends_on = [
      data.aws_api_gateway_rest_api.external_api
  ]
}

resource "aws_api_gateway_resource" "releasable" {
  rest_api_id = data.aws_api_gateway_rest_api.external_api.id
  parent_id   = data.aws_api_gateway_rest_api.external_api.root_resource_id
  path_part   = "releaseable"
}

resource "aws_api_gateway_method" "releasable" {
  rest_api_id      = data.aws_api_gateway_rest_api.external_api.id
  resource_id      = aws_api_gateway_resource.releasable.id
  http_method      = "ANY"
  authorization    = "NONE"
  api_key_required = false
}

resource "aws_lambda_permission" "lambda_permission" {
  statement_id  = "AllowAPIGatewayToInvokeLambda"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.main.function_name
  principal     = "apigateway.amazonaws.com"

  # The /*/*/* part allows invocation from any stage, method and resource path
  # within API Gateway REST API.
  source_arn = "${data.aws_api_gateway_rest_api.external_api.execution_arn}/*/*/*"
}

