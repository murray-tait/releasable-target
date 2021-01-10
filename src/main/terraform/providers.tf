provider "aws" {
  region  = "eu-west-1"
  version = "~> 3.11"
  profile = module.common.all.aws_profile
}

provider "template" {
  version = "~> 2.1"
}

provider "aws" {
  alias   = "global"
  region  = "us-east-1"
  version = "~> 3.11"
  profile = module.common.all.aws_profile
}

provider "archive" {
  version = "~> 1.2"
}

provider "aws" {
  alias = "account_description"
  region  = "eu-west-1"
  version = "~> 3.11"
  profile = "973963482762_AccountDescriptionAccess"
}