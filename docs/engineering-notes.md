# Engineering notes

This project was built incrementally in the AWS Console as a hands-on exercise in connecting managed AWS services into one authenticated application. The notes below record problems that occurred while the deployed system was being assembled and debugged.

They are included because the final architecture alone hides most of the work involved in getting the individual services to behave correctly together.

## CloudFront and S3

### CloudFront returned `Access Denied`

**Symptom:** The frontend bucket contained the expected files, but the CloudFront distribution could not serve them.

**Cause:** The distribution had been configured with `CustomOriginConfig` instead of an S3 origin configuration. The Origin Access Control therefore could not sign requests to the private S3 origin as intended.

**Change:** Reconfigured the origin as S3, attached the OAC to the distribution, and redeployed the distribution configuration.

**What this taught me:** A private S3 + CloudFront setup depends on the origin type as well as the bucket policy and OAC itself. Having an OAC resource created is not enough if the distribution is not actually using it.

### CloudFront kept serving old frontend files

**Symptom:** New files were uploaded to S3, but the browser continued receiving the previous version.

**Cause:** Cached CloudFront objects had not expired.

**Change:** Invalidated the relevant CloudFront paths after frontend updates.

**What this taught me:** Updating the origin and updating what CloudFront serves are separate operations.

## API Gateway and CORS

### `403 Missing Authentication Token` on update

**Symptom:** An expense update looked like an authentication failure.

**Cause:** `PUT` had initially been configured on `/expenses` instead of `/expenses/{expense_id}`. API Gateway could not match the browser request to the intended resource.

**Change:** Added the update method to the parameterized resource and used the path parameter in the Lambda integration.

**What this taught me:** API Gateway's `Missing Authentication Token` response can also indicate route/method mismatch; it should not automatically be treated as a Cognito problem.

### DELETE worked at the API layer but failed in the browser

**Symptom:** The browser blocked the request before the authenticated DELETE call was sent.

**Cause:** The `OPTIONS` response did not include `DELETE` in `Access-Control-Allow-Methods`.

**Change:** Updated the preflight configuration and redeployed the API stage.

**What this taught me:** With API Gateway, the real method and its browser preflight are separate pieces of configuration. A working Lambda integration does not imply the browser is allowed to call it.

### CORS appeared broken even after the configuration was fixed

**Symptom:** The browser kept showing the previous CORS failure after the API had been redeployed.

**Cause:** The browser had cached the earlier preflight response.

**Change:** Retested after clearing the cached response / hard refreshing.

## Cognito authentication

### PUT worked from Postman but stopped working in the browser

**Symptom:** The API and Lambda appeared healthy when called independently, while the frontend request failed during a longer debugging session.

**Cause:** The Cognito ID token had reached its expiry time.

**Change:** Re-authenticated and obtained a fresh token.

**What this taught me:** When an authenticated flow works from one client but not another, token lifetime and client state need to be checked before changing backend logic.

### Login succeeded but redirect failed

**Symptom:** Cognito authentication completed, but the hosted login could not return to the deployed frontend correctly.

**Cause:** The CloudFront URL was missing from the Cognito app client's allowed callback URLs.

**Change:** Added the deployed CloudFront URL to the callback configuration.

## Lambda, IAM, and DynamoDB

### Update Lambda failed before `UpdateItem`

**Symptom:** Updating an expense raised `AccessDeniedException` on DynamoDB `GetItem`.

**Cause:** The update function had an auto-generated execution role without the DynamoDB permissions used by the other receipt Lambdas. The ownership check calls `GetItem` before any update is attempted, so the request never reached `UpdateItem`.

**Change:** Corrected the Lambda execution role and permissions.

**What this taught me:** Debug the first failing AWS call in the execution path. The operation visible to the user is not necessarily the operation that failed internally.

### Early records were stored under `test-user`

**Symptom:** An authenticated user could receive `404 Expense not found` for an expense that existed in DynamoDB.

**Cause:** Early versions propagated a temporary `test-user` value through the processing workflow. DynamoDB uses both `user_id` and `expense_id` as the primary key, so a record written under `test-user` could not be found using the authenticated Cognito `sub`.

**Change:** The maintained code derives the user identity from the user-scoped S3 object key (`uploads/{user_id}/...`) created by the authenticated presigned-upload path and carries that value through the workflow.

**What this taught me:** Identity needs to be consistent across authentication, object keys, workflow state, and database keys. A composite-key lookup can look like a missing record when the real problem is identity propagation.

## Receipt OCR and parsing

Amazon Textract `DetectDocumentText` is intentionally used as the OCR layer. It returns detected text/LINE blocks; the project-specific parser is responsible for deciding which detected text represents the vendor, final amount, date, and category.

Failures encountered while testing included:

- an item amount being selected instead of the receipt total;
- subtotal / pre-tax amounts competing with the final payable total;
- receipts containing more than one total-like value;
- inconsistent `₹`, `Rs`, and `INR` formatting;
- incomplete OCR output;
- semantically incorrect OCR such as an item name being read as a different phrase.

The parser can improve field selection when the correct information exists in the OCR text. It cannot reliably reconstruct information that Textract itself read incorrectly. The application therefore keeps the original receipt image accessible and allows the user to edit parsed expense fields after processing.

## Scope decisions

A monthly-report path was started as an extension to the Step Functions workflow and later abandoned. It has been removed from the maintained repository workflow rather than being completed only to make the architecture look larger.

The project remains console-first. Rebuilding every deployed resource in SAM/CDK/Terraform would be a separate infrastructure-as-code exercise; it is not presented as part of the original implementation.
