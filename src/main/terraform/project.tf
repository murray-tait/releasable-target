locals {
  application_name = "releasable-target"
}

module "common" {
  # source = "git@github.com:deathtumble/terraform_modules.git//modules/common?ref=v0.3.0"
  source                       = "../../../../terraform/modules/common"
  application_name             = "build"
  project_name                 = "experiment"
  domain                       = local.domain
  aws_account_id               = local.aws_account_id
  dns_account_id               = local.dns_account_id
  build_account_id             = local.build_account_id
  build_account_name           = local.build_account_name
  terraform_state_account_name = local.terraform_state_account_name
  terraform_state_account_id   = local.terraform_state_account_id
}

module "lambda_pipeline" {
  source = "git@github.com:deathtumble/terraform_modules.git//modules/lambda_pipeline?ref=v0.1.43"
  #  source                         = "../../../../../infra2/terraform/modules/lambda_pipeline"
  application_name                          = local.application_name
  destination_builds_bucket_name            = module.common.destination_builds_bucket_name
  lambdas                                   = [aws_lambda_function.main]
  aws_sns_topic_env_build_notification_name = module.common.aws_sns_topic_env_build_notification_name
  aws_account_id                            = local.aws_account_id
}

data "aws_wafregional_web_acl" "main" {
  name = module.common.web_acl_name
}

data "aws_route53_zone" "environment" {
  name = module.common.fqdn_no_app
}

data "aws_acm_certificate" "main" {
  domain   = "*.${module.common.fqdn_no_app}"
  types    = ["AMAZON_ISSUED"]
  statuses = ["ISSUED"]
  provider = aws.global

  most_recent = true
}

# module "api_gateway" {
#   source = "git@github.com:deathtumble/terraform_modules.git//modules/api_gateway?ref=v0.1.42"
#   #  source                         = "../../../../../infra2/terraform/modules/api_gateway"
#   aws_region   = module.common.aws_region
#   aws_profile  = module.common.aws_profile
#   fqdn         = module.common.fqdn
#   fqdn_no_app  = module.common.fqdn_no_app
#   zone_id      = data.aws_route53_zone.environment.zone_id
#   lambda       = aws_lambda_function.main
#   web_acl_name = module.common.web_acl_name
#   providers = {
#     aws.global = aws.global
#   }
# }
