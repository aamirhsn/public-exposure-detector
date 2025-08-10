terraform {
  required_version = ">= 1.2.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 4.0"
    }
  }
}

provider "aws" {
  # Remove region from here if you prefer to set via env var AWS_REGION or AWS_PROFILE
  region = var.aws_region
}