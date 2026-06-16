import json
import boto3

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('table-name')  # Replace with your DynamoDB table name
s3 = boto3.client('s3')

RECEIPT_BUCKET = '<RECEIPT_BUCKET_NAME>'  # Replace with your S3 bucket name
URL_EXPIRY_SECONDS = 300

HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'GET,OPTIONS'
}


def lambda_handler(event, context):
    if event.get('httpMethod') == 'OPTIONS':
        return {'statusCode': 200, 'headers': HEADERS, 'body': ''}

    try:
        user_id = event['requestContext']['authorizer']['claims']['sub']
    except (KeyError, TypeError):
        return {'statusCode': 401, 'headers': HEADERS,
                'body': json.dumps({'message': 'Unauthorized'})}

    expense_id = event.get('pathParameters', {}).get('expense_id')
    if not expense_id:
        return {'statusCode': 400, 'headers': HEADERS,
                'body': json.dumps({'message': 'Missing expense_id'})}

    try:
        existing = table.get_item(Key={'user_id': user_id, 'expense_id': expense_id})
        if 'Item' not in existing:
            return {'statusCode': 404, 'headers': HEADERS,
                    'body': json.dumps({'message': 'Expense not found'})}

        original_key = existing['Item'].get('original_key')
        if not original_key:
            return {'statusCode': 404, 'headers': HEADERS,
                    'body': json.dumps({'message': 'No receipt image on record'})}

        url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': RECEIPT_BUCKET, 'Key': original_key},
            ExpiresIn=URL_EXPIRY_SECONDS
        )

        return {
            'statusCode': 200,
            'headers': HEADERS,
            'body': json.dumps({'image_url': url})
        }
    except Exception as e:
        print("Error:", str(e))
        return {'statusCode': 500, 'headers': HEADERS,
                'body': json.dumps({'message': str(e)})}
