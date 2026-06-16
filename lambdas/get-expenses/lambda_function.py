import json
import boto3
from decimal import Decimal
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('table-Name')  # Replace with your DynamoDB table name

HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
}

def decimal_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError

def lambda_handler(event, context):
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
        response = table.query(
            IndexName='user_id-upload_date-index',
            KeyConditionExpression=Key('user_id').eq(user_id),
            ScanIndexForward=False,
            Limit=50
        )
        items = response.get('Items', [])
        return {
            'statusCode': 200,
            'headers': HEADERS,
            'body': json.dumps({
                'count': len(items),
                'expenses': json.loads(json.dumps(items, default=decimal_default))
            })
        }
    except Exception as e:
        print("Error:", str(e))
        return {
            'statusCode': 500,
            'headers': HEADERS,
            'body': json.dumps({'message': str(e)})
        }
