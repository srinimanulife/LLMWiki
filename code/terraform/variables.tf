variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "AWS CLI profile to use"
  type        = string
  default     = "tzg-sandbox"
}

variable "account_id" {
  description = "AWS account ID (auto-populated)"
  type        = string
  default     = ""
}

variable "bedrock_model_id" {
  description = "Bedrock model for wiki page generation"
  type        = string
  default     = "us.anthropic.claude-sonnet-4-6"
}

variable "bedrock_embedding_model_id" {
  description = "Bedrock model for embeddings (must produce 1024-dim vectors to match S3 Vectors index)"
  type        = string
  default     = "amazon.titan-embed-text-v2:0"
}

variable "lambda_memory_mb" {
  description = "Memory for Lambda functions in MB"
  type        = number
  default     = 1024
}

variable "lambda_timeout_seconds" {
  description = "Timeout for Lambda functions in seconds"
  type        = number
  default     = 900
}

variable "textract_timeout_seconds" {
  description = "Timeout for Textract Lambda in seconds"
  type        = number
  default     = 900
}

variable "streamlit_port" {
  description = "Port Streamlit runs on"
  type        = number
  default     = 8501
}

variable "streamlit_desired_count" {
  description = "Number of Streamlit ECS tasks (set 0 to stop, 1 to start)"
  type        = number
  default     = 1
}
