import json
import boto3
import uuid
from datetime import datetime

s3 = boto3.client('s3')
BUCKET_NAME = "bucket-name"  # Replace with your S3 bucket name

HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
}

def lambda_handler(event, context):
    print("=== GeneratePresignedUrl Called ===")

    if event.get('httpMethod') == 'OPTIONS':
        return {'statusCode': 200, 'headers': HEADERS, 'body': ''}

    try:
        user_id = event['requestContext']['authorizer']['claims']['sub']
    except (KeyError, TypeError):
        return {
            'statusCode': 401,
            'headers': HEADERS,
            'body': json.dumps({'message': 'Unauthorized'})
        }

    try:
        timestamp = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
        file_id = uuid.uuid4().hex
        key = f"uploads/{user_id}/{timestamp}-{file_id}.jpg"

        presigned_url = s3.generate_presigned_url(
            'put_object',
            Params={'Bucket': BUCKET_NAME, 'Key': key},
            ExpiresIn=900
        )

        return {
            'statusCode': 200,
            'headers': HEADERS,
            'body': json.dumps({
                'presignedUrl': presigned_url,
                'key': key,
                'user_id': user_id
            })
        }
    except Exception as e:
        print("ERROR:", str(e))
        return {
            'statusCode': 500,
            'headers': HEADERS,
            'body': json.dumps({'message': str(e)})
        }
