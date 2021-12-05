locals {
  application_name = "releasable-target"
}

module "lambda_pipeline" {
  source = "git@github.com:deathtumble/terraform_modules.git//modules/lambda_pipeline?ref=v0.1.43"
  #  source                         = "../../../../../infra2/terraform/modules/lambda_pipeline"
  application_name                          = local.application_name
  destination_builds_bucket_name            = module.common.destination_builds_bucket_name
  lambdas                                   = [aws_lambda_function.lambda]
  aws_sns_topic_env_build_notification_name = module.common.aws_sns_topic_env_build_notification_name
  aws_account_id                            = local.aws_account_id
}
