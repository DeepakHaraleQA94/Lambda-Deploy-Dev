<<<<<<< HEAD
# CloudMedia Lambda deployment starter

This repository keeps the Lambda source code as normal, unzipped files. GitHub Actions creates the deployment ZIP automatically and updates the existing Lambda function after a push to `main`.

## Repository layout

```text
.
├── lambda_function.py
├── requirements.txt
├── .gitignore
├── README.md
└── .github/
    └── workflows/
        └── deploy-lambda.yml
```

## Before the first deployment

1. Confirm the AWS Lambda function already exists.
2. In AWS IAM, create or update an IAM role trusted by GitHub's OIDC provider.
3. Grant that role permission to update **only the intended Lambda function** (`lambda:UpdateFunctionCode`; add `lambda:GetFunction` if you want to inspect deployments). Do not put AWS access keys in the repository.
4. In GitHub, open **Settings → Secrets and variables → Actions**:
   - Add repository secret `AWS_ROLE_ARN` with the ARN of the GitHub OIDC deployment role.
   - Add repository variable `AWS_REGION`, for example `ap-south-1`.
   - Add repository variable `LAMBDA_FUNCTION_NAME` with the exact existing Lambda function name.

The deployment role's trust policy must restrict the GitHub OIDC subject to this repository and branch, for example `repo:OWNER/REPOSITORY:ref:refs/heads/main`. Replace `OWNER/REPOSITORY` with the actual GitHub owner and repository. The AWS account must have the GitHub OIDC identity provider `token.actions.githubusercontent.com` configured.

## Lambda environment variables

Set these on the Lambda function in AWS Console → Configuration → Environment variables:

- `USERS_TABLE` — exact existing users table name
- `MEDIA_TABLE` — exact existing media table name
- `ACCESS_TABLE` — exact existing access table name
- `MEDIA_BUCKET` — exact existing S3 bucket name
- `AWS_REGION` — your AWS region (Lambda also supplies `AWS_REGION` automatically)

The Lambda execution role needs read permissions for the three DynamoDB tables and `s3:ListBucket` on the bucket for the `/health` check. The function code uses its execution role; GitHub's deployment role and Lambda's execution role are separate roles.

## Deploy

Commit and push changes to the `main` branch. The workflow will package the files and call `aws lambda update-function-code`. You can also start it manually from the repository's **Actions** tab using **Run workflow**.

## Test

After deployment, invoke the function with an API Gateway HTTP API event for `GET /health`, or use a simple Lambda test event:

```json
{
  "rawPath": "/health",
  "requestContext": {
    "http": {
      "method": "GET"
    }
  }
}
```

A successful response reports the DynamoDB table statuses and S3 bucket connectivity. This is a starter health-check API, not the complete user/media/playlist access-management application.
=======
# Lambda-Deploy-Dev
AWS Lambda deployment using GitHub Actions
>>>>>>> c04b436858d45b31e8662643f5e5e6eb507a9eb3
