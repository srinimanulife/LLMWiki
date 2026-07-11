terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.0"
    }
  }

  backend "s3" {
    bucket         = "llmwiki-tfstate-392568849512"
    key            = "llmwiki/dev/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "llmwiki-tfstate-lock"
    encrypt        = true
    profile        = "tzg-sandbox"
  }
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile

  default_tags {
    tags = {
      Owner       = "859600@cognizant.com"
      Application = "LLMWiki"
      Environment = "Dev"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
