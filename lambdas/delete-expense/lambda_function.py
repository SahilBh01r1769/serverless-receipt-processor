import json
import boto3

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('expenses')
s3 = boto3.client('s3')

RECEIPT_BUCKET = 'receipt-processor-project-storage'

HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'DELETE,OPTIONS'
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
        # Verify the item belongs to this user and get the S3 key
        existing = table.get_item(Key={'user_id': user_id, 'expense_id': expense_id})
        if 'Item' not in existing:
            return {'statusCode': 404, 'headers': HEADERS,
                    'body': json.dumps({'message': 'Expense not found'})}

        item = existing['Item']
        original_key = item.get('original_key')

        # Delete the DynamoDB record
        table.delete_item(Key={'user_id': user_id, 'expense_id': expense_id})

        # Best-effort delete of the S3 receipt image
        if original_key:
            try:
                s3.delete_object(Bucket=RECEIPT_BUCKET, Key=original_key)
            except Exception as s3_err:
                print(f"Warning: could not delete S3 object {original_key}: {s3_err}")

        return {
            'statusCode': 200,
            'headers': HEADERS,
            'body': json.dumps({'message': 'Deleted successfully', 'expense_id': expense_id})
        }
    except Exception as e:
        print("Error:", str(e))
        return {'statusCode': 500, 'headers': HEADERS,
                'body': json.dumps({'message': str(e)})}