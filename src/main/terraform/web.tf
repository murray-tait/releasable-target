locals {
  build_artifact_key = "builds/${local.application_name}/refs/branch/${terraform.workspace}/cloudfront.zip"
}

locals {
  config = {
    REACT_APP_API_ENDPOINT                     = "https://${var.application_name}-api.${module.common.fqdn_no_app}/query"
    REACT_APP_PRIMARY_SLDN                     = module.common.fqdn_no_app
    REACT_APP_API_SLDN                         = module.common.fqdn_no_app
    REACT_APP_SSO_COOKIE_SLDN                  = module.common.fqdn_no_app
    REACT_APP_AWS_COGNITO_REGION               = module.common.aws_region
    REACT_APP_AWS_COGNITO_IDENTITY_POOL_REGION = module.common.aws_region
    REACT_APP_AWS_COGNITO_AUTH_FLOW_TYPE       = "USER_SRP_AUTH"
    REACT_APP_AWS_COGNITO_COOKIE_EXPIRY_MINS   = tonumber(55)
    REACT_APP_AWS_COGNITO_COOKIE_SECURE        = tobool(true)
  }
  app_config = {
    REACT_APP_API_ENDPOINT = "https://${var.application_name}-api.${module.common.fqdn_no_app}/query"
  }
}

module "web" {
  source       = "git@github.com:deathtumble/terraform_modules.git//modules/web?ref=v0.1.39"
#  source                         = "../../../../../infra2/terraform/modules/web"
  aws_profile  = module.common.aws_profile
  fqdn         = "web${module.common.fqdn}"
  fqdn_no_app  = module.common.fqdn_no_app
  web_acl_name = module.common.web_acl_name
  providers = {
    aws.global = aws.global
  }
  environment_config = merge(local.config,
    local.app_config
  )
}

module "cloudfront_pipeline" {
  source                         = "git@github.com:deathtumble/terraform_modules.git//modules/cloudfront_pipeline?ref=v0.1.39"
#  source                         = "../../../../../infra2/terraform/modules/cloudfront_pipeline"
  fqdn                           = "web${module.common.fqdn}"
  destination_builds_bucket_name = module.common.destination_builds_bucket_name
  application_name               = local.application_name
  branch_name                    = terraform.workspace
  artifacts_bucket_name          = module.common.artifacts_bucket_name
  build_artifact_key             = local.build_artifact_key
}