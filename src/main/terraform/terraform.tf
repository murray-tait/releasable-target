locals {
  terraform_build_artifact_key = "builds/${local.application_name}/refs/branch/${terraform.workspace}/terraform.zip"
}

module "terraform_pipeline" {
  source = "git@github.com:deathtumble/terraform_modules.git//modules/terraform_pipeline?ref=v0.2.4"
  #  source                         = "../../../../../infra2/terraform/modules/terraform_pipeline"
  destination_builds_bucket_name = module.common.destination_builds_bucket_name
  application_name               = local.application_name
  policy_arns                    = [aws_iam_policy.terraform_policy.arn]
  build_artifact_key             = local.terraform_build_artifact_key
  aws_region                     = module.common.aws_region
  repo_token                     = local.repo_token
  terraform_bucket_name          = module.common.terraform_bucket_name
  terraform_dynamodb_table       = module.common.terraform_dynamodb_table
  aws_account_id                 = module.common.aws_account_id
  terraform_state_role_arn       = module.common.terraform_state_role_arn
}

data "aws_secretsmanager_secret_version" "repo_token" {
  secret_id = "repo_token"
}

locals {
  repo_token = jsondecode(data.aws_secretsmanager_secret_version.repo_token.secret_string)["github_token"]
}

resource "aws_iam_policy" "terraform_policy" {
  name   = "${local.application_name}-terraform-pipeline-BulkResourcesAcccess"
  policy = data.template_file.terraform_policy.rendered
}

data "template_file" "terraform_policy" {
  template = file("${path.module}/policies/terraform_policy.json")
}
