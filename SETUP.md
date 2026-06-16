# Setup Guide

This document covers two things: (1) how to export the current AWS configuration into this repo for documentation purposes, and (2) how to run or redeploy the project.

This project was built incrementally through the AWS Console, so there's no single "deploy" command yet — this guide focuses on capturing the existing setup cleanly and getting the frontend running locally.

---

## Prerequisites

- AWS CLI installed and configured (`aws configure`) with credentials that have read access to the relevant services
- The AWS account ID and region where the project lives (e.g. `ap-south-1`)
- Python 3.9+ if you want to inspect or modify Lambda code locally
- A modern browser; no build tooling is required for the frontend

---

## 1. Exporting AWS configuration into `docs/`

Run these from the repo root. Replace placeholders (`<...>`) with your actual resource names — you can find most of these in the AWS Console under each service.

### DynamoDB

```bash
# Table schema: keys, attribute types, GSIs
aws dynamodb describe-table \
  --table-name <your-table-name> \
  > docs/dynamodb-table.json

# A couple of real records, to document the data shape
aws dynamodb scan \
  --table-name <your-table-name> \
  --max-items 2 \
  > docs/dynamodb-sample-items.json
```

### IAM

First, find the roles attached to your Lambda functions (visible in each function's Configuration → Permissions tab, or list them directly):

```bash
aws iam list-roles \
  --query "Roles[?contains(RoleName,'receipt')].RoleName" \
  --output table
```

For each role:

```bash
mkdir -p docs/iam

aws iam list-role-policies \
  --role-name <role-name> \
  > docs/iam/<role-name>-inline-list.json

aws iam list-attached-role-policies \
  --role-name <role-name> \
  > docs/iam/<role-name>-attached-list.json

# For each inline policy found above, get the actual document:
aws iam get-role-policy \
  --role-name <role-name> \
  --policy-name <policy-name> \
  > docs/iam/<role-name>-<policy-name>.json
```

### API Gateway

Find your API ID:

```bash
aws apigateway get-rest-apis --query "items[*].{id:id,name:name}" --output table
```

Export the route tree and full spec:

```bash
aws apigateway get-resources \
  --rest-api-id <api-id> \
  > api-gateway/resources.json

aws apigateway get-export \
  --rest-api-id <api-id> \
  --stage-name prod \
  --export-type oas30 \
  api-gateway/openapi.json
```

### Step Functions

```bash
aws stepfunctions list-state-machines --query "stateMachines[*].{name:name,arn:stateMachineArn}" --output table

aws stepfunctions describe-state-machine \
  --state-machine-arn <state-machine-arn> \
  --query 'definition' \
  --output text \
  > step-functions/receipt-workflow.asl.json
```

### Cognito

```bash
aws cognito-idp list-user-pools --max-results 10 --query "UserPools[*].{Id:Id,Name:Name}" --output table

aws cognito-idp describe-user-pool \
  --user-pool-id <user-pool-id> \
  > docs/cognito-user-pool.json

aws cognito-idp describe-user-pool-client \
  --user-pool-id <user-pool-id> \
  --client-id <client-id> \
  > docs/cognito-app-client.json
```

### Lambda functions (if you need to re-download any)

```bash
aws lambda get-function \
  --function-name <function-name> \
  --query 'Code.Location' \
  --output text
```

This returns a presigned S3 URL — download it and unzip into `lambdas/<function-name>/`.

> **Before committing:** scan exported JSON files for account IDs, ARNs, and bucket/table names. These aren't usually sensitive, but it's good practice to redact account IDs (`123456789012` → `<account-id>`) if the repo is public. Never commit anything from `~/.aws/credentials`.

---

## 2. Running the frontend locally

The frontend is a single static HTML file with no build step.

```bash
cd frontend
python3 -m http.server 8080
```

Then open `http://localhost:8080`. It will still talk to the real deployed API Gateway and Cognito — this just serves the static file locally instead of via CloudFront.

> **Note on redirect URI:** Cognito's hosted login redirects back to whatever `REDIRECT_URI` is configured in `index.html` and registered in the Cognito app client's callback URLs. If you serve locally on a different origin (e.g. `localhost:8080`), you'll need to add that URL to the app client's allowed callback URLs in the Cognito console, or sign-in will fail with a redirect mismatch error.

---

## 3. Redeploying a Lambda function after editing

If you've edited a function under `lambdas/<name>/` and want to push the change back to AWS without setting up full CI/CD yet:

```bash
cd lambdas/<name>
zip -r function.zip .

aws lambda update-function-code \
  --function-name <function-name> \
  --zip-file fileb://function.zip
```

---

## 4. Order of operations if rebuilding from scratch

If you ever need to recreate this stack in a new account, the dependency order is:

1. **DynamoDB table** (with the GSI) — nothing else depends on it existing first, but Lambdas need its name/ARN
2. **S3 bucket** — for receipt images
3. **Cognito user pool + app client** — configure PKCE, callback URLs, and Managed Login branding
4. **IAM roles** — one per Lambda, scoped to only the resources that function touches (Textract, the specific DynamoDB table, the specific S3 bucket)
5. **Lambda functions** — deploy each from `lambdas/<name>/`
6. **Step Functions state machine** — import `step-functions/receipt-workflow.asl.json`, wire in the Lambda ARNs
7. **S3 → Step Functions trigger** — EventBridge rule or S3 event notification on object creation
8. **API Gateway** — create routes per `api-gateway/resources.json`, attach Cognito authorizer, integrate each route with its Lambda
9. **CloudFront distribution** — point at the S3 bucket or hosting origin for `frontend/index.html`, set as the Cognito callback/logout URI
10. **Update `index.html`** — fill in `COGNITO_DOMAIN`, `CLIENT_ID`, `REDIRECT_URI`, and `API_BASE` to match the new deployment

This is documented for reference; turning these steps into actual IaC (SAM, CDK, or Terraform) is a natural next step once the manual setup is fully captured here.

---

## Troubleshooting notes

A few issues that came up during development, kept here so they don't get rediscovered the hard way:

- **CORS errors on authenticated requests** — make sure API Gateway's CORS configuration explicitly allows the `Authorization` header, not just `Content-Type`.
- **PKCE verifier missing after redirect** — use `localStorage`, not `sessionStorage`, for the code verifier; some browsers treat the OAuth redirect as a new tab/session context.
- **Managed Login UI not loading** — Cognito's newer Managed Login (v2) requires a branding/style to be explicitly configured for the app client, even if using defaults.
- **`SaveToDatabase` writing the wrong user** — extract the Cognito `sub` from the S3 object key path (set during upload) rather than trusting any client-supplied user ID field.
- **₹ symbol disappearing during parsing** — avoid calling `.upper()` on lines containing the rupee symbol in some encodings; use a per-line regex match instead, with a fallback chain for vendor detection.
