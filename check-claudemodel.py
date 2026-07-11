import boto3
import json

def test_active_claude_models():
    try:
        # Create session with profile
        session = boto3.Session(profile_name='tzg-sandbox')
        
        # Create Bedrock client
        client = session.client(
            'bedrock-runtime',
            region_name='us-east-1'
        )
        
        # Test the ACTIVE models found in your IAM check
        active_models = [
            # These are the ACTIVE models from your account
            'anthropic.claude-sonnet-4-6',                    # ACTIVE
            'anthropic.claude-haiku-4-5-20251001-v1:0',      # ACTIVE
            
            # Try inference profiles for these models
            'us.anthropic.claude-sonnet-4-6',                # Inference profile
            'us.anthropic.claude-haiku-4-5-20251001-v1:0',   # Inference profile
        ]
        
        for model_id in active_models:
            print(f"\n🔄 Testing ACTIVE model: {model_id}")
            try:
                response = client.invoke_model(
                    modelId=model_id,
                    body=json.dumps({
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": 100,
                        "messages": [
                            {
                                "role": "user", 
                                "content": "Hello! Please confirm you're working and tell me which Claude model you are."
                            }
                        ]
                    })
                )
                
                response_body = json.loads(response['body'].read())
                print(f"✅ SUCCESS with: {model_id}")
                print(f"📝 Response: {response_body['content'][0]['text']}")
                print(f"\n🎯 WORKING MODEL: {model_id}")
                return model_id
                
            except Exception as e:
                error_msg = str(e)
                print(f"❌ Failed: {error_msg}")
                
                if "throughput isn't supported" in error_msg:
                    print("   → This model requires inference profile")
                elif "use case details" in error_msg:
                    print("   → This model requires use case form")
                else:
                    print(f"   → Other error: {error_msg[:100]}...")
        
        print("\n❌ All ACTIVE models failed.")
        return None
        
    except Exception as e:
        print(f"❌ Client setup error: {e}")
        return None

if __name__ == "__main__":
    print("🚀 Testing ACTIVE Claude models...")
    
    working_model = test_active_claude_models()
    
    if working_model:
        print(f"\n🎉 SUCCESS! Use this model: {working_model}")
        print("\n📋 Working example:")
        print(f"""
import boto3
import json

session = boto3.Session(profile_name='tzg-sandbox')
client = session.client('bedrock-runtime', region_name='us-east-1')

response = client.invoke_model(
    modelId='{working_model}',
    body=json.dumps({{
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1000,
        "messages": [
            {{"role": "user", "content": "Your prompt here"}}
        ]
    }})
)

response_body = json.loads(response['body'].read())
print(response_body['content'][0]['text'])
""")
    else:
        print("\n🔧 If ACTIVE models still fail, you have two options:")
        print("1. Submit Anthropic use case form (required for older models)")
        print("2. Try Amazon Nova models instead (no form required)")
        print("\n📝 Amazon Nova alternative:")
        print("   - amazon.nova-pro-v1:0")
        print("   - amazon.nova-lite-v1:0")
        print("   - amazon.nova-micro-v1:0")

