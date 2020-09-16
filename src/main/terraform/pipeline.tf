data "archive_file" "updater_source" {
    type = "zip"
    source_file = "lambda_updater.py"
    output_path = "lambda_updater.zip"
}

data "aws_s3_bucket" "build_bucket" {
    bucket = module.common.destination_builds_bucket_name
}

locals {
    lambdas = [ aws_lambda_function.main ] 
}

locals {
    lambda_arns  = tolist([for lambda in local.lambdas : lambda.arn])
    lambda_names = tolist([for lambda in local.lambdas : lambda.function_name])
}

resource "aws_lambda_function" "updater" {
    function_name = "${var.application_name}-lambda-updater"
    handler = "lambda_updater.updater"
    runtime = "python3.7"
    role = aws_iam_role.lambda_updater_service_role.arn
    timeout = 30
    filename = data.archive_file.updater_source.output_path
    source_code_hash = filebase64sha256(data.archive_file.updater_source.output_path)

    environment {
        variables = {
            FUNCTION_NAMES = join(",", [for l in local.lambdas: l.function_name])
            BRANCH_NAME = terraform.workspace
            APPLICATION_NAME = var.application_name
        }
    }
}

resource "aws_iam_role" "lambda_updater_service_role" {
    name = "AllowLambdaToUpdateLambda.${var.application_name}"
    assume_role_policy = data.template_file.lambda_updater_service_role.rendered
}

data "template_file" "lambda_updater_service_role" {
    template = file("policies/lambda_updater_service_role.json")
}

##############################################################################

resource "aws_iam_policy" "lambda_updater_service_role_lambda" {
    name = "AllowLambdaToUpdateLambda.${var.application_name}"
    policy = data.template_file.lambda_updater_service_role_lambda.rendered
}

resource "aws_iam_role_policy_attachment" "lambda_updater_service_role_lambda" {
    role = aws_iam_role.lambda_updater_service_role.name
    policy_arn = aws_iam_policy.lambda_updater_service_role_lambda.arn
}

data "template_file" "lambda_updater_service_role_lambda" {
    template = file("policies/lambda_updater_service_role_lambda.json")
    vars = {
        lambda_arns = jsonencode(local.lambda_arns)
        build_bucket_arn = data.aws_s3_bucket.build_bucket.arn
    }
}

data "aws_sns_topic" "api_upload_subscription" {
    name = "uk-co-urbanfortress-endtoend-api-upload-notifications"
}

resource "aws_sns_topic_subscription" "api_upload_subscription" {
    topic_arn = data.aws_sns_topic.api_upload_subscription.arn
    protocol = "lambda"
    endpoint = aws_lambda_function.updater.arn
}

resource "aws_lambda_permission" "with_sns" {
    statement_id = "AllowExecutionFromSns"
    action = "lambda:InvokeFunction"
    function_name = aws_lambda_function.updater.function_name
    principal = "sns.amazonaws.com"
    source_arn = data.aws_sns_topic.api_upload_subscription.arn
}
