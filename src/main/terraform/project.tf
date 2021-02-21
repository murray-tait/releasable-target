locals {
  application_name = "releasable-target"
}

module "common" {
  source = "git@github.com:deathtumble/terraform_modules.git//modules/common?ref=v0.2.2"
  # source           = "../../../../../infra2/terraform/modules/common"
  application_name = local.application_name
  project_name     = "urbanfortress"
  tld              = "uk"
}

module "lambda_pipeline" {
  source = "git@github.com:deathtumble/terraform_modules.git//modules/lambda_pipeline?ref=v0.1.43"
  #  source                         = "../../../../../infra2/terraform/modules/lambda_pipeline"
  application_name                          = local.application_name
  destination_builds_bucket_name            = module.common.destination_builds_bucket_name
  lambdas                                   = [aws_lambda_function.main]
  aws_sns_topic_env_build_notification_name = module.common.aws_sns_topic_env_build_notification_name
  aws_account_id                            = module.common.aws_account_id
}

data "aws_wafregional_web_acl" "main" {
  name = module.common.web_acl_name
}

data "aws_route53_zone" "environment" {
  name = module.common.fqdn_no_app
}

data "aws_api_gateway_rest_api" "external_api" {
  name = "api.${module.common.fqdn_no_app}"
}


data "aws_acm_certificate" "main" {
  domain   = "*.${module.common.fqdn_no_app}"
  types    = ["AMAZON_ISSUED"]
  statuses = ["ISSUED"]
  provider = aws.global

  most_recent = true
}
