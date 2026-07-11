import boto3

# check which identity is being used
sts = boto3.client("sts")
identity = sts.get_caller_identity()
print("✅ Current Identity:")
print(identity)

# create bedrock runtime client
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

print("\n✅ Bedrock client created successfully")
