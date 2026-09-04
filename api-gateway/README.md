# API Gateway notes

The files in this directory were exported from the console-built API and are retained as deployment snapshots. Because the project was assembled and debugged incrementally, the historical export contains one known stale route: an accidental `PUT /expenses` method that was created before the correct parameterized route was added.

The maintained application route set is:

| Method | Route | Lambda responsibility |
|---|---|---|
| `POST` | `/upload-url` | Generate a user-scoped presigned S3 upload URL |
| `GET` | `/expenses` | Query recent expenses for the authenticated Cognito user |
| `PUT` | `/expenses/{expense_id}` | Update allowed fields after ownership verification |
| `DELETE` | `/expenses/{expense_id}` | Delete the user's expense and best-effort remove its S3 image |
| `GET` | `/expenses/{expense_id}/image` | Return a short-lived presigned URL for the original receipt |

All application methods use the Cognito user-pool authorizer. `OPTIONS` methods are unauthenticated CORS preflight endpoints.

## Why keep the old export?

The export is evidence of the console-first development process rather than an infrastructure-as-code source of truth. The stale route is documented instead of being presented as intentional design. The README and table above describe the route set that should be maintained going forward.
