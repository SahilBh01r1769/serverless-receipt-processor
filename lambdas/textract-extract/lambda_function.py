import json
import boto3
import uuid
from urllib.parse import unquote_plus

textract = boto3.client('textract')

def lambda_handler(event, context):
    print("Event received:", json.dumps(event))
    
    bucket = event['bucket']
    key = unquote_plus(event['key'])
    user_id = event.get('user_id', 'test-user')
    
    try:
        # Using Textract DetectDocumentText
        response = textract.detect_document_text(
            Document={
                'S3Object': {
                    'Bucket': bucket,
                    'Name': key
                }
            }
        )
        
        expense_id = f"{user_id}-{uuid.uuid4()}"
        
        return {
            'statusCode': 200,
            'bucket': bucket,
            'key': key,
            'expense_id': expense_id,
            'user_id': user_id,
            'textract_response': response
        }
    except Exception as e:
        print("Textract Error:", str(e))
        raise e