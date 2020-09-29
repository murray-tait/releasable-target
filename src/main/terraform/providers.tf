provider "aws" {
  region  = "eu-west-1"
  version = "~> 2.21"
  profile = module.common.all.aws_profile
}

provider "template" {
  version = "~> 2.1"
}

provider "aws" {
  alias   = "global"
  region  = "us-east-1"
  version = "~> 2.21"
  profile = module.common.all.aws_profile
}

provider "archive" {
  version = "~> 1.2"
}

provider "aws" {
  alias   = "dns_account"
  region  = "eu-west-1"
  version = "~> 2.21"
  profile = "453254632971_NetworkAdministrator"
}