locals {
  terraform_build_artifact_key = "builds/${local.application_name}/refs/branch/${terraform.workspace}/terraform.zip"
}

module "terraform_pipeline" {
  source       = "git@github.com:deathtumble/terraform_modules.git//modules/terraform_pipeline?ref=v0.1.31"
#  source           = "../../../../../infra2/terraform/modules/terraform_pipeline"
  destination_builds_bucket_name = module.common.destination_builds_bucket_name
  application_name = local.application_name
  role_arn = ""
  build_artifact_key = local.terraform_build_artifact_key
  aws_region   = module.common.aws_region
  repo_token   = local.repo_token
  terraform_bucket_name = module.common.terraform_bucket_name
  terraform_dynamodb_table = module.common.terraform_dynamodb_table
}

data "aws_secretsmanager_secret_version" "repo_token" {
  secret_id = "repo_token"
}

locals {
  repo_token = "${jsondecode(data.aws_secretsmanager_secret_version.repo_token.secret_string)["github_token"]}"
}