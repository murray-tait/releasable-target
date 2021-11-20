provider "aws" {
  region  = "eu-west-1"
  profile = module.common.all.aws_profile
  #assume_role { role_arn = "arn:aws:iam::481652375433:role/releasable-target-terraform-pipleine-CodeBuildRole" }
}

provider "template" {
}

provider "aws" {
  alias   = "global"
  region  = "us-east-1"
  profile = module.common.all.aws_profile
  #assume_role { role_arn = "arn:aws:iam::481652375433:role/releasable-target-terraform-pipleine-CodeBuildRole" }
}

provider "archive" {
}
