terraform {
  required_version = ">= 0.13"
  backend "s3" {
    region         = "eu-west-1"
    key            = "releasable-target/terraform.tfstate"
    bucket         = "uk.co.urbanfortress.terraform"
    profile        = "973963482762_TerraformStateAccess"
    dynamodb_table = "uk.co.urbanfortress.terraform.lock"
    acl            = "bucket-owner-full-control"
  }         
}