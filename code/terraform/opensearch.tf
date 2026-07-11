# OpenSearch Serverless removed.
#
# Replaced by Amazon S3 Vectors — see s3_vectors.tf and bedrock_kb.tf.
# Reasons: $11-12/day minimum cost vs $0/day at demo scale, complex
# provisioning (local-exec SigV4 signing), and unnecessary for this workload.
