# Receipt Processor

A serverless receipt-processing application built on AWS. Users upload a photo of a receipt, the system extracts vendor, amount, category, and date using OCR, and stores it as a structured expense record tied to their account.


---

## Overview

This project started as a way to explore an end-to-end serverless pipeline: authentication, file upload, OCR extraction, structured storage, and a per-user dashboard, all without managing a single server. It's built entirely on managed AWS services and a static frontend.

**Core flow:**

1. User signs in via Cognito (Authorization Code + PKCE flow, Managed Login).
2. Frontend requests a presigned S3 URL and uploads the receipt image directly to S3.
3. The S3 upload triggers a Step Functions workflow.
4. The workflow runs the image through Textract (FORMS mode), parses vendor / amount / date / category, and writes the result to DynamoDB — scoped to the authenticated user.
5. The frontend reads, edits, and deletes expenses through API Gateway, and can fetch a fresh presigned URL to view the original receipt image at any time.

---

## Architecture

```
┌──────────┐     ┌──────────┐     ┌──────────────┐     ┌───────────┐
│ Frontend │────▶│ Cognito  │     │ API Gateway  │────▶│  Lambda   │
│ (SPA)    │     │ (PKCE)   │     │ (Bearer auth)│     │ functions │
└────┬─────┘     └──────────┘     └──────────────┘     └─────┬─────┘
     │                                                        │
     │ presigned PUT                                          ▼
     ▼                                                  ┌───────────┐
┌──────────┐     S3 event      ┌──────────────┐         │ DynamoDB  │
│    S3    │──────────────────▶│ Step         │         │ (per-user │
│ (images) │                   │ Functions    │         │  GSI)     │
└──────────┘                   └──────┬───────┘         └───────────┘
                                       │
                                       ▼
                                ┌──────────────┐
                                │   Textract   │
                                │ (FORMS mode) │
                                └──────────────┘
```

| Layer | Service | Purpose |
|---|---|---|
| Auth | Cognito | User pool, hosted Managed Login UI, PKCE authorization code flow |
| Frontend | Static HTML/CSS/JS | Single-page app, served via CloudFront |
| Edge / CDN | CloudFront | Serves the frontend, single redirect URI for OAuth |
| API | API Gateway | REST endpoints, validates Cognito bearer tokens |
| Compute | Lambda | One function per responsibility (upload URL, parse, CRUD, image fetch) |
| Orchestration | Step Functions | Coordinates the OCR → parse → store pipeline after upload |
| OCR | Textract | FORMS mode extraction from receipt images |
| Storage (files) | S3 | Raw receipt images, keyed by user |
| Storage (data) | DynamoDB | Structured expense records, with a GSI for per-user queries |
| Permissions | IAM | Scoped roles per Lambda function |

---

## Features

- Email/password sign-in via Cognito Managed Login (no custom auth code)
- Drag-and-drop or click-to-upload receipt images, with client-side size validation
- Asynchronous OCR pipeline orchestrated by Step Functions (decoupled from the upload request)
- Automatic vendor / amount / date / category extraction, with fallback handling for non-standard formats (e.g. Indian vendor names, ₹ symbol parsing, multiple date formats)
- Per-user data isolation enforced at the DynamoDB query layer via a GSI on `user_id`
- Expense list with running totals (all-time and current month)
- Edit any expense field, with the original receipt image shown side-by-side for verification
- Delete expenses, with confirmation and toast feedback
- Fresh presigned URLs generated on demand for viewing receipt images (never cached, since they expire)

---

## Repository structure

```
receipt-processor/
├── README.md
├── SETUP.md
├── frontend/
│   └── index.html                  # Single-file SPA
├── lambdas/
│   ├── upload-url/                 # Generates presigned S3 PUT URL
│   ├── process-receipt/            # Textract + parsing logic
│   ├── get-expenses/                # GET /expenses
│   ├── update-expense/              # PUT /expenses/{id}
│   ├── delete-expense/              # DELETE /expenses/{id}
│   └── get-receipt-image/           # GET /expenses/{id}/image
├── step-functions/
│   └── receipt-workflow.asl.json   # State machine definition
├── api-gateway/
│   ├── openapi.json                # Exported route + integration spec
│   └── resources.json              # Raw path tree
└── docs/
    ├── dynamodb-table.json         # Table schema, keys, GSI
    ├── dynamodb-sample-items.json  # Example expense records
    ├── cognito-user-pool.json      # User pool configuration
    ├── cognito-app-client.json     # App client (PKCE) configuration
    └── iam/                        # Role policies per Lambda
```

---

## API reference

All endpoints require `Authorization: Bearer <id_token>` and are scoped to the authenticated user.

| Method | Path | Description |
|---|---|---|
| `POST` | `/upload-url` | Returns a presigned S3 URL for uploading a receipt image |
| `GET` | `/expenses` | Lists all expenses for the authenticated user |
| `PUT` | `/expenses/{expense_id}` | Updates vendor, amount, category, or date |
| `DELETE` | `/expenses/{expense_id}` | Permanently deletes an expense |
| `GET` | `/expenses/{expense_id}/image` | Returns a fresh presigned URL for the original receipt image |

See `api-gateway/openapi.json` for the full request/response schema.

---

## Data model

Expense records in DynamoDB look roughly like:

```json
{
  "expense_id": "uuid",
  "user_id": "cognito-sub",
  "vendor": "string",
  "amount": "number",
  "category": "Food & Dining | Groceries | Online Shopping | ...",
  "expense_date": "YYYY-MM-DD",
  "upload_date": "ISO 8601 timestamp",
  "raw_text": "string (Textract output)",
  "s3_key": "string"
}
```

A GSI on `user_id` (and `upload_date` for sort order) allows per-user queries without scanning the whole table. See `docs/dynamodb-table.json` for the exact schema and `docs/dynamodb-sample-items.json` for real examples.

---

## Tech notes

A few non-obvious decisions worth knowing if you're reading the code:

- **PKCE over implicit/client-secret flow** — the frontend is a public SPA client with no backend to hold a secret, so Cognito's Authorization Code + PKCE flow is used, with the verifier stored in `localStorage` (not `sessionStorage`, since the redirect leaves and returns to the page).
- **Step Functions, not direct Lambda chaining** — decouples the OCR pipeline from the upload request/response cycle, and makes retries/error handling at each stage explicit and inspectable in the AWS console.
- **Presigned URLs are never cached** — both for image viewing and upload, since they expire; the frontend always requests a fresh one when needed.
- **Currency parsing** — the ₹ symbol is preserved through a per-line regex rather than relying on naive string casing, since `.upper()` on certain encodings silently dropped the symbol.

