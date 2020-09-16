module "common" {
    source = "git@github.com:deathtumble/terraform_modules.git//modules/common?ref=v0.1.5"
    application_name = "releasable-target"
    project_name     = "urbanfortress"
}

resource "aws_lambda_function" "main" {
    function_name = var.application_name
    runtime = "provided"
    handler = "handler"
    timeout = "30"
    role = aws_iam_role.lambda_service_role.arn
    s3_bucket = module.common.destination_builds_bucket_name
    s3_key = "builds/${var.application_name}/refs/branch/${terraform.workspace}/dist.zip"

}

resource "aws_iam_role" "lambda_service_role" {
    name = "LambdaserviceRole.${var.application_name}"
    assume_role_policy = data.template_file.lambda_service_role.rendered
}

data "template_file" "lambda_service_role" {
    template = file("policies/lambda_service_role.json")
}