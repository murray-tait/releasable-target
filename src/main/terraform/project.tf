module "common" {
  source           = "git@github.com:deathtumble/terraform_modules.git//modules/common?ref=v0.1.19"
  application_name = "releasable-target"
  project_name     = "urbanfortress"
  tld              = "uk"
}

module "pipeline" {
  source                                     = "git@github.com:deathtumble/terraform_modules.git//modules/lambda_pipeline?ref=v0.1.7"
  application_name                           = "releasable_target"
  destination_builds_bucket_name             = module.common.destination_builds_bucket_name
  lambdas                                    = [aws_lambda_function.main]
  aws_sns_topic_api_upload_subscription_name = module.common.aws_sns_topic_env_build_notification_name
}

module "api_gateway" {
  source       = "git@github.com:deathtumble/terraform_modules.git//modules/api_gateway?ref=v0.1.21"
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

