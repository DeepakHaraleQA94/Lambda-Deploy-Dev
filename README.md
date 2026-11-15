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
profile_service.py       Private profile, documents and face photo quality checks
location_service.py      ISO country/state and city catalog APIs
infrastructure/
  playlists-table.yml    CloudFormation template for playlist table
  expiry-schedule.yml   CloudFormation template for daily expiry worker
  locations-table.yml   CloudFormation template for city catalog
  cities-seed-example.csv Sample city rows for import
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

User profile fields include first/middle/last name, qualification, current/permanent address, mobile and alternate mobile, passing year, designation, year gap, previous company name/address. Both current and permanent addresses can store countryCode/country, stateCode/state and city in addition to the free-text street address. Country and first-level administrative subdivision lists come from the ISO 3166 data in `pycountry`; city choices come from `CloudMedia-Locations-DEV` and must be populated with the cities you want to offer. The UI should clear state/city when country changes and clear city when state changes. Aadhaar, PAN, degree certificates, profile photo and passport-size photo are uploaded directly to private S3 using short-lived presigned URLs. The backend stores object keys, not raw Aadhaar/PAN numbers. Profile photos must contain exactly one detectable face and meet basic sharpness/brightness/front-facing checks using Amazon Rekognition; this is a photo-quality check, not identity verification or face matching. Profile documents are viewable by the user only while at least one access grant is active; view links expire after five minutes. Administrators can view/update profiles using admin routes. Restrict admin access carefully and obtain user consent before collecting identity documents.

For storage format: profile fields are JSON attributes nested under the user's `profile` map in `CloudMedia-Users-DEV`; profile document binaries are private S3 objects under `private-profiles/{userId}/{documentType}/...`; only S3 object keys and metadata are stored in DynamoDB. The access table stores grants/expiry as ISO-8601 timestamps. Location catalog rows store `countryState` and `cityName` as DynamoDB strings. Uploaded PDF/JPEG/PNG files keep their original binary file format in S3; photo face checks apply only to JPEG/PNG images.

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
| GET/PATCH | /profile | View/update own profile while access is active for viewing |
| POST | /profile/upload-url | Create private upload URL for Aadhaar/PAN/degree/profile/passport photo |
| POST | /profile/complete-upload | Validate uploaded file and save its private object key |
| POST | /profile/document-url | View own private profile document while access is active |
| GET | /locations/countries | Country dropdown data (authenticated) |
| GET | /locations/states?countryCode=IN | State/province dropdown for selected country |
| GET | /locations/cities?countryCode=IN&stateCode=IN-MH | Cities available for selected state |
| GET/PATCH | /users/{userId}/profile | Admin view/update a user's profile |
| POST | /profile/admin-document-url | Admin view a user's private profile document |

Send the login token in the `Authorization: Bearer <token>` header for protected endpoints. Login JSON body:

```json
{"username":"your-admin-username","password":"your-admin-password"}
```

User creation JSON includes `userId`, `username`, `password`, and optional `email`, `role`, and profile fields. The default role is `user`.

## AWS permissions still required on the Lambda execution role

Deploy `infrastructure/locations-table.yml` before using city dropdowns. Import city rows into `CloudMedia-Locations-DEV` with partition key `countryState` (for example `IN-MH`) and sort key `cityName`; see `infrastructure/cities-seed-example.csv`. The current sample contains only a few India cities, not a complete worldwide city database. The Lambda execution role (not the GitHub Actions deployment role) needs the permissions listed in `infrastructure/lambda-execution-policy.json`, including `rekognition:DetectFaces` for profile photo quality checks and read/query access to the locations table. Review the resource ARNs and attach the policy to the existing `CloudMedia_Lambda_Execution_DEV_Role`. Keep `AWSLambdaBasicExecutionRole` (or equivalent CloudWatch Logs permissions) attached as well.

The code deployment role used by GitHub Actions is separate and only deploys the Lambda code.

## Expiry and notifications

`GET /access/check` evaluates `expiresAt` (ISO-8601 timestamp) and changes expired records to `EXPIRED`. `POST /notifications/expiry` sends an email when called by an administrator. The daily worker is wired into the Lambda handler for EventBridge events. Deploy `infrastructure/expiry-schedule.yml` with the existing Lambda ARN to activate the daily schedule. SES sender verification and `ses:SendEmail` permission are required for email delivery. The worker scans the access table, marks expired grants as `EXPIRED`, and sends one email per grant when the user has an email address and SES is configured.

## Deployment

A push to `main` that changes a root Python file, `requirements.txt`, or the workflow triggers GitHub Actions. The workflow validates Python syntax, packages all root Python modules, assumes the AWS deployment role through OIDC, and updates `CloudMediaHandler`. It can also be started manually using `workflow_dispatch`.

## Important validation status

The workflow proves that the Python files compile and the Lambda code update command succeeds. It does not prove every API route works against live AWS resources. Before end-to-end testing, configure the Lambda environment variables, create the playlist table, and update the Lambda execution role permissions described above. API Gateway routes must also forward the paths and HTTP methods to this Lambda.

## Web frontend

The React/Vite admin and user portal is in `frontend/`. It includes sign-in, admin overview, user creation, access grants, profile editing, cascading current/permanent address selectors, private document upload, and active-access document viewing.

Run locally:

```bash
cd frontend
cp .env.example .env.local
# Set VITE_API_BASE_URL in .env.local to your API Gateway URL
npm install
npm run dev
```

Build with `npm run build`; output is `frontend/dist/`. GitHub Actions validates the frontend build and uploads the dist folder as a workflow artifact. Hosting is not automatic yet: configure an S3/CloudFront hosting destination and deployment credentials before publishing the UI. Configure API Gateway CORS for the frontend origin and S3 bucket CORS for browser PUT uploads.

For city options, create `CloudMedia-Locations-DEV` from `infrastructure/locations-table.yml`, then import your city CSV using `python scripts/import_cities.py path/to/cities.csv`. CSV columns are `countryState,cityName`, with state identifiers such as `IN-MH`. The checked-in CSV is only a small sample; populate a complete maintained city dataset before production use.
