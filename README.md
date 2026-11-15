# CloudMedia – AWS Lambda Backend

This repository contains the CloudMedia serverless backend. Source files stay in GitHub as normal Python modules. GitHub Actions packages all root-level Python modules and deploys them to the existing Lambda function `CloudMediaHandler`.

## Current architecture

```text
lambda_function.py       Lambda entry point and /health check
cloudmedia_api.py        HTTP routing and role checks
base_service.py          Shared DynamoDB CRUD and API errors
auth_service.py          PBKDF2 password hashing and signed bearer tokens
user_service.py          User records and password-safe responses
media_service.py         Media metadata CRUD
access_service.py        User-to-media access records
playlist_service.py      Playlist metadata CRUD
s3_service.py            Presigned S3 upload/playback URLs
expiry_service.py        Access expiry evaluation
notification_service.py  SES expiry email helper
infrastructure/
  playlists-table.yml    CloudFormation template for playlist table
  expiry-schedule.yml   CloudFormation template for daily expiry worker
```

## Existing DynamoDB key schema

| Table | Partition key | Sort key |
|---|---|---|
| CloudMedia-Users-DEV | userId (String) | — |
| CloudMedia-Media-DEV | mediaID (String) | — |
| CloudMedia-Access-DEV | userId (String) | mediaID (String) |
| CloudMedia-Playlists-DEV | playlistId (String) | — |

The first three tables were confirmed in the AWS console. The playlist table is a new resource: deploy `infrastructure/playlists-table.yml` in CloudFormation before using playlist endpoints. Deploy `infrastructure/expiry-schedule.yml` separately with the existing Lambda ARN to enable daily expiry processing.

## Required Lambda environment variables

Set these in Lambda → Configuration → Environment variables. Do not commit secret values.

| Variable | Purpose |
|---|---|
| AWS_REGION | AWS region (Lambda normally provides this automatically) |
| USERS_TABLE | Defaults to CloudMedia-Users-DEV |
| MEDIA_TABLE | Defaults to CloudMedia-Media-DEV |
| ACCESS_TABLE | Defaults to CloudMedia-Access-DEV |
| PLAYLISTS_TABLE | Defaults to CloudMedia-Playlists-DEV |
| MEDIA_BUCKET | Defaults to cloudmedia-assets-dev-01 |
| ADMIN_USERNAME | Bootstrap administrator username |
| ADMIN_PASSWORD | Bootstrap administrator password; use a strong unique value |
| AUTH_TOKEN_SECRET | Random secret of at least 32 characters for signing bearer tokens |
| AUTH_TOKEN_TTL_SECONDS | Optional token lifetime; defaults to 3600 |
| SES_FROM_EMAIL | Verified SES sender address for expiry email notifications |
| S3_URL_TTL_SECONDS | Optional presigned URL lifetime; defaults to 300 |

The bootstrap admin is configured through environment variables. Normal users are created through the authenticated admin API. User passwords are PBKDF2-HMAC-SHA256 hashed before storage. Password hashes and salts are omitted from user API responses.

## API routes currently implemented

All routes except `GET /health`, `POST /auth/login`, and CORS preflight require a valid bearer token. Administrative CRUD and management routes require a token with role `admin`.

| Method | Route | Purpose |
|---|---|---|
| GET | /health | DynamoDB and S3 health check |
| POST | /auth/login | Bootstrap admin or user login |
| GET | /auth/me | Current token identity |
| GET/POST | /users | List/create users |
| GET/PATCH/DELETE | /users/{userId} | Read/update/delete user |
| GET/POST | /media | List/create media metadata |
| GET/PATCH/DELETE | /media/{mediaID} | Read/update/delete media metadata |
| POST | /media/upload-url | Create short-lived S3 PUT URL |
| POST | /media/playback-url | Create short-lived S3 GET URL |
| GET/POST | /access | List by userId/create access |
| GET/PATCH/DELETE | /access/{userId}/{mediaID} | Read/update/delete access |
| GET | /access/check?mediaID=... | Check caller's own access; admin may specify userId |
| GET/POST | /playlists | List/create playlists |
| GET/PATCH/DELETE | /playlists/{playlistId} | Read/update/delete playlist |
| POST | /notifications/expiry | Send one expiry email via SES |

Send the login token in the `Authorization: Bearer <token>` header for protected endpoints. Login JSON body:

```json
{"username":"your-admin-username","password":"your-admin-password"}
```

User creation JSON includes `userId`, `username`, `password`, and optional `email`, `role`, and profile fields. The default role is `user`.

## AWS permissions still required on the Lambda execution role

The Lambda execution role (not the GitHub Actions deployment role) needs the permissions listed in `infrastructure/lambda-execution-policy.json`. Review the resource ARNs and attach the policy to the existing `CloudMedia_Lambda_Execution_DEV_Role`. Keep `AWSLambdaBasicExecutionRole` (or equivalent CloudWatch Logs permissions) attached as well.

The code deployment role used by GitHub Actions is separate and only deploys the Lambda code.

## Expiry and notifications

`GET /access/check` evaluates `expiresAt` (ISO-8601 timestamp) and changes expired records to `EXPIRED`. `POST /notifications/expiry` sends an email when called by an administrator. The daily worker is wired into the Lambda handler for EventBridge events. Deploy `infrastructure/expiry-schedule.yml` with the existing Lambda ARN to activate the daily schedule. SES sender verification and `ses:SendEmail` permission are required for email delivery. The worker scans the access table, marks expired grants as `EXPIRED`, and sends one email per grant when the user has an email address and SES is configured.

## Deployment

A push to `main` that changes a root Python file, `requirements.txt`, or the workflow triggers GitHub Actions. The workflow validates Python syntax, packages all root Python modules, assumes the AWS deployment role through OIDC, and updates `CloudMediaHandler`. It can also be started manually using `workflow_dispatch`.

## Important validation status

The workflow proves that the Python files compile and the Lambda code update command succeeds. It does not prove every API route works against live AWS resources. Before end-to-end testing, configure the Lambda environment variables, create the playlist table, and update the Lambda execution role permissions described above. API Gateway routes must also forward the paths and HTTP methods to this Lambda.
