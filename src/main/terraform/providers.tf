provider "aws" {
  region  = "eu-west-1"
  profile = module.common.all.aws_profile
}

provider "template" {
}

provider "aws" {
  alias   = "global"
  region  = "us-east-1"
  profile = module.common.all.aws_profile
}

provider "archive" {
}

provider "myaws" {
  region  = "eu-west-1"
  profile = "453254632971_ListAccountsAccess"
}