import boto3
from decimal import Decimal
from datetime import datetime

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('table-name')  # Replace with your DynamoDB table name


def lambda_handler(event, context):
    record = event['expense_record']

    cleaned_record = {
        'user_id': record['user_id'],
        'expense_id': record['expense_id'],
        'original_key': record.get('original_key', ''),
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
        print(
            f"Saved record for expense {record['expense_id']} "
            f"under user {record['user_id']}"
        )
        return {
            'statusCode': 200,
            'message': 'Expense saved successfully',
            'expense_id': record['expense_id']
        }
    except Exception as e:
        print("DynamoDB Save Error:", str(e))
        raise
