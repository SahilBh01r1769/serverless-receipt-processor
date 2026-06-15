import json
import boto3
from decimal import Decimal
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('expenses')

HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'PUT,OPTIONS'
}

# Fields a user is allowed to edit
EDITABLE_FIELDS = {'vendor', 'amount', 'category', 'expense_date'}

VALID_CATEGORIES = {
    'Food & Dining', 'Groceries', 'Online Shopping', 'Fuel & Transport',
    'Health & Pharmacy', 'Utilities', 'Fashion', 'Miscellaneous'
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
        return {'statusCode': 401, 'headers': HEADERS,
                'body': json.dumps({'message': 'Unauthorized'})}

    expense_id = event.get('pathParameters', {}).get('expense_id')
    if not expense_id:
        return {'statusCode': 400, 'headers': HEADERS,
                'body': json.dumps({'message': 'Missing expense_id'})}

    try:
        body = json.loads(event.get('body') or '{}')
    except json.JSONDecodeError:
        return {'statusCode': 400, 'headers': HEADERS,
                'body': json.dumps({'message': 'Invalid JSON body'})}

    # Build update expression from allowed fields only
    update_parts = []
    expr_values = {}
    expr_names = {}

    for field, value in body.items():
        if field not in EDITABLE_FIELDS:
            continue

        if field == 'amount':
            try:
                value = Decimal(str(value))
                if value < 0:
                    return {'statusCode': 400, 'headers': HEADERS,
                            'body': json.dumps({'message': 'Amount cannot be negative'})}
            except Exception:
                return {'statusCode': 400, 'headers': HEADERS,
                        'body': json.dumps({'message': 'Invalid amount'})}

        if field == 'category' and value not in VALID_CATEGORIES:
            return {'statusCode': 400, 'headers': HEADERS,
                    'body': json.dumps({'message': f'Invalid category: {value}'})}

        if field == 'vendor':
            value = str(value)[:100]

        placeholder = f':{field}'
        name_placeholder = f'#{field}'
        update_parts.append(f'{name_placeholder} = {placeholder}')
        expr_values[placeholder] = value
        expr_names[name_placeholder] = field

    if not update_parts:
        return {'statusCode': 400, 'headers': HEADERS,
                'body': json.dumps({'message': 'No valid fields to update'})}

    update_expr = 'SET ' + ', '.join(update_parts)

    try:
        # First verify the item belongs to this user
        existing = table.get_item(Key={'user_id': user_id, 'expense_id': expense_id})
        if 'Item' not in existing:
            return {'statusCode': 404, 'headers': HEADERS,
                    'body': json.dumps({'message': 'Expense not found'})}

        response = table.update_item(
            Key={'user_id': user_id, 'expense_id': expense_id},
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expr_values,
            ExpressionAttributeNames=expr_names,
            ReturnValues='ALL_NEW'
        )

        return {
            'statusCode': 200,
            'headers': HEADERS,
            'body': json.dumps({
                'message': 'Updated successfully',
                'expense': json.loads(json.dumps(response['Attributes'], default=decimal_default))
            })
        }
    except Exception as e:
        print("Error:", str(e))
        return {'statusCode': 500, 'headers': HEADERS,
                'body': json.dumps({'message': str(e)})}