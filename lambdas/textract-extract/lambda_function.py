import json
import boto3
import uuid
from urllib.parse import unquote_plus

textract = boto3.client('textract')


def _user_id_from_key(key):
    """Extract the Cognito user id from uploads/{user_id}/{filename}."""
    parts = key.split('/')
    if len(parts) < 3 or parts[0] != 'uploads' or not parts[1]:
        raise ValueError(f"Unexpected receipt object key: {key}")
    return parts[1]


def lambda_handler(event, context):
    print("Event received:", json.dumps(event))

    bucket = event['bucket']
    key = unquote_plus(event['key'])
    user_id = _user_id_from_key(key)

    try:
        # DetectDocumentText provides generic OCR lines. Receipt-specific field
        # selection is handled by ReviewAndCategorize in the next workflow step.
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
        raise
