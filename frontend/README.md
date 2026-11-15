# CloudMedia Web Portal

React + Vite frontend for the CloudMedia Lambda API.

## Run locally
1. Install Node.js 20 or newer.
2. Copy `.env.example` to `.env.local`.
3. Set `VITE_API_BASE_URL` to the API Gateway base URL (no trailing slash).
4. Run `npm install`, then `npm run dev`.

## Build
`npm run build` creates `dist/`.

## Included screens
- Admin/user login
- Admin dashboard and user list
- User creation
- Media/playlist access grant with duration/custom expiry
- User profile with education/work details
- Current and permanent country → state → city dropdowns
- Private document/photo upload using signed S3 URLs

## Deployment
Host the `dist/` directory on a private or public CloudFront/S3 website according to your access requirements. Configure API Gateway CORS for the frontend origin and S3 bucket CORS to allow PUT from the frontend origin with Content-Type and x-amz-server-side-encryption headers. Do not put AWS credentials in frontend variables.

The country and subdivision lists are supplied by the backend. City dropdown values come from the CloudMedia-Locations-DEV DynamoDB table and require the city seed dataset to be imported.