module "common" {
    source = "git@github.com:deathtumble/terraform_modules.git//modules/common?ref=v0.1.15"
    application_name = "releasable-target"
    project_name     = "urbanfortress"
    application_tld  = ["uk"]
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

#######################################

resource "aws_iam_policy" "lambda_log_access" {
  name   = "AllowLambdaToWriteToLogs.${var.application_name}"
  policy = data.template_file.lambda_service_policy.rendered
}

# Attach the policy that allows lambda to access cloudwatch logs
resource "aws_iam_role_policy_attachment" "lambda_log_access" {
  role       = aws_iam_role.lambda_service_role.name
  policy_arn = aws_iam_policy.lambda_log_access.arn
}

# Define a policy that allows lambda to every it needs
data "template_file" "lambda_service_policy" {
  template = file("policies/lambda_service_policy.json")
}

##########################################

data "template_file" "lambda_service_role" {
    template = file("policies/lambda_service_role.json")
}

data "aws_route53_zone" "parent" {
  name     = "${module.common.fqdn_no_env}."
  provider = aws.dns_account
}

module "pipeline" {
    source = "git@github.com:deathtumble/terraform_modules.git//modules/lambda_pipeline?ref=v0.1.7"
    application_name = "releasable_target"
    destination_builds_bucket_name = module.common.destination_builds_bucket_name
    lambdas = [ aws_lambda_function.main ]
    aws_sns_topic_api_upload_subscription_name = module.common.aws_sns_topic_env_build_notification_name
}

module "api_gateway" {
    source = "../../../../../infra2/terraform/modules/api_gateway"
    aws_region = module.common.aws_region
    aws_profile = module.common.aws_profile
    fqdn = module.common.fqdn
    fqdn_no_app = module.common.fqdn_no_app
    zone_id = data.aws_route53_zone.parent.zone_id
    lambda = aws_lambda_function.main
    web_acl_name = "IPWhiteListWebACL"
    providers = {
        aws.global = aws.global
        aws.dns_account = aws.dns_account
    }
}