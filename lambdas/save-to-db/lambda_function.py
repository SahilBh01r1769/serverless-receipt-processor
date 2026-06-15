import boto3
from decimal import Decimal
from datetime import datetime

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('expenses')

def lambda_handler(event, context):
    record = event['expense_record']

    # Extract user_id from S3 key if it's still test-user or missing
    # Key format: uploads/{user_id}/{timestamp}-{file_id}.jpg
    user_id = record.get('user_id', 'unknown')
    original_key = record.get('original_key', '')

    if user_id == 'test-user' or user_id == 'unknown':
        try:
            # uploads/51532dea-70f1-70d8-4d47-5bebba10bd42/20260611-123456-abcd.jpg
            user_id = original_key.split('/')[1]
            print(f"Extracted user_id from key: {user_id}")
        except (IndexError, AttributeError):
            print("Could not extract user_id from key, using fallback")

    cleaned_record = {
        'user_id': user_id,
        'expense_id': record['expense_id'],
        'original_key': original_key,
        'upload_date': record['upload_date'],
        'created_at': datetime.utcnow().isoformat(),
        'category': record.get('category', 'Miscellaneous'),
        'amount': Decimal(str(record.get('amount', 0.0))),
        'vendor': record.get('vendor', 'Unknown'),
        'expense_date': record.get('expense_date', ''),
        'raw_text': record.get('raw_text', '')[:2000],
        'status': record.get('status', 'processed')
    }

    try:
        table.put_item(Item=cleaned_record)
        print(f"Saved record for expense {record['expense_id']} under user {user_id}")
        return {
            'statusCode': 200,
            'message': 'Expense saved successfully',
            'expense_id': record['expense_id']
        }
    except Exception as e:
        print("DynamoDB Save Error:", str(e))
        raise e