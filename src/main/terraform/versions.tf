terraform {
  required_providers {
    archive = {
      source = "hashicorp/archive"
      version = "~> 1.3.0"
    }
    aws = {
      source = "hashicorp/aws"
      version = "~> 3.29.0"
    }
    template = {
      source = "hashicorp/template"
      version = "~> 2.2.0"
    }
    myaws = {
      source = "registry.terraform.io/deathtumble/aws"
      version = "~> 3.99.5"
    }
  }
  required_version = ">= 0.13"
}
