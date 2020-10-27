locals {
  application_name = "releasable-target"
}

module "common" {
  source = "git@github.com:deathtumble/terraform_modules.git//modules/common?ref=v0.1.42"
#  source           = "../../../../../infra2/terraform/modules/common"
  application_name = local.application_name
  project_name     = "urbanfortress"
  tld              = "uk"
}

module "lambda_pipeline" {
  source                                     = "git@github.com:deathtumble/terraform_modules.git//modules/lambda_pipeline?ref=v0.1.42"
#  source                         = "../../../../../infra2/terraform/modules/lambda_pipeline"
  application_name                           = local.application_name
  destination_builds_bucket_name             = module.common.destination_builds_bucket_name
  lambdas                                    = [aws_lambda_function.main]
  aws_sns_topic_env_build_notification_name = module.common.aws_sns_topic_env_build_notification_name
  aws_account_id                            = module.common.aws_account_id  
}

module "api_gateway" {
  source       = "git@github.com:deathtumble/terraform_modules.git//modules/api_gateway?ref=v0.1.42"
#  source                         = "../../../../../infra2/terraform/modules/api_gateway"
  aws_region   = module.common.aws_region
  aws_profile  = module.common.aws_profile
  fqdn         = module.common.fqdn
  fqdn_no_app  = module.common.fqdn_no_app
  zone_id      = data.aws_route53_zone.environment.zone_id
  lambda       = aws_lambda_function.main
  web_acl_name = module.common.web_acl_name
  providers = {
    aws.global = aws.global
  }
}

data "aws_route53_zone" "environment" {
  name = module.common.fqdn_no_app
}
