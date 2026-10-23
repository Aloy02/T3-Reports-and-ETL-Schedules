# 📊 Daily Food Truck Report Generator

This service automatically builds a daily report of **yesterday's** food truck sales and **emails a link to it**. It runs in the cloud on AWS, so once it's set up nobody has to press anything.

## 📋 Table of Contents

- [What It Does](#-what-it-does)
- [How It Fits Together](#️-how-it-fits-together)
- [Project Structure](#-project-structure)
- [Before You Start (One-Off Setup)](#-before-you-start-one-off-setup)
- [Step-by-Step: Deploy to AWS](#-step-by-step-deploy-to-aws)
- [Updating the Report After Code Changes](#-updating-the-report-after-code-changes)
- [Testing on Your Own Computer](#-testing-on-your-own-computer)
- [📧 How the Email (SES) Works](#-how-the-email-ses-works)

---

## 💡 What It Does

Each time it runs, the service:

1. **Reads yesterday's sales** (UK time) from the data lake using AWS Athena.
2. **Builds a web page report** with:
   - Headline figures: total revenue, number of orders, average spend per order
   - **📈 Hourly Performance** tab: revenue per truck, hour by hour, plus a summary table
   - **💰 Truck Breakdown** tab: total revenue per truck
   - **💳 Payment Methods** tab: card vs cash split, revenue per truck by payment type, and which trucks accept cards
3. **Saves the report** to S3 at `s3://c26-aloysius-t3-s3/reports/food_truck_daily_report.html`.
4. **Returns an email message** (subject, body and a link that works for **24 hours**) to a **Step Function**, which sends it using Amazon SES.

If there were no sales yesterday, no report is produced and the Lambda returns a "skipped" message instead of the email details (so the Step Function's email step will fail on that day).

The report is designed to work on **phones as well as computers**. You can hover over or tap a chart to see exact figures, but zooming and dragging are switched off so the charts don't jump around.

---

## 🏗️ How It Fits Together

```
 ⏰ EventBridge Scheduler ──▶ 🔀 Step Function ──1──▶ λ Lambda (our Docker image)
                                  │                        │
                                  │               ┌────────┴─────────┐
                                  │               ▼                  ▼
                                  │      🔎 Athena / Glue      🪣 S3 (saves report)
                                  │      (reads yesterday)
                                  │                        │
                                  └──2── 📧 SES sends email ◀── Lambda returns the
                                          with the link          subject, body and link
```

The Lambda **builds the report**. The Step Function **sends the email**. Keeping them separate means the Lambda has one job, and a failure in either step shows up clearly in Step Functions.

| Piece | What it is | Where it's defined |
|---|---|---|
| **Docker image** | A packaged copy of the Python code and everything it needs | [`Dockerfile`](./Dockerfile) |
| **ECR repository** | AWS's storage for Docker images | [`ecr_terraform/`](./ecr_terraform/) |
| **Lambda function** | Runs the Docker image in the cloud | [`lambda_and_steps/main.tf`](./lambda_and_steps/main.tf) |
| **Lambda IAM role** | Lets the Lambda use S3, Athena, Glue and logging | [`lambda_and_steps/main.tf`](./lambda_and_steps/main.tf) |
| **Step Function** | Runs the Lambda, then sends the email with SES | [`lambda_and_steps/main.tf`](./lambda_and_steps/main.tf) |
| **Step Function IAM role** | Lets the Step Function invoke the Lambda and send email | [`lambda_and_steps/main.tf`](./lambda_and_steps/main.tf) |
| **SES identities** | Verified email addresses that are allowed to send and receive | [`lambda_and_steps/main.tf`](./lambda_and_steps/main.tf) |
| **EventBridge schedule** | The timer that starts the Step Function automatically | [`lambda_and_steps/main.tf`](./lambda_and_steps/main.tf) |
| **Python code** | Reads data, builds charts, uploads the report, returns the email details | [`generator/create_report.py`](./generator/create_report.py) |

---

## 📂 Project Structure

```
report/
├── README.md                    # You are here
├── Dockerfile                   # Recipe for building the Docker image
├── .env                         # Your local settings for testing (NOT committed – you create it)
│
├── Build_Image.sh               # Build the Docker image on your computer
├── Lambda_Local_Image.sh        # Build + run the image locally, pretending to be Lambda
├── Lambda_Local_Test_Image.sh   # Send a test "run" to the local container
├── Push_To_ECR_Pipeline.sh      # Log in to AWS, build the image and upload it to ECR
├── Pull_Image.sh                # Tell the Lambda to switch to the newest uploaded image
│
├── generator/
│   ├── create_report.py         # The main program
│   └── requirements.txt         # Python libraries the program needs
│
├── ecr_terraform/               # Step 1 of infrastructure: creates the ECR repository
│   ├── main.tf
│   ├── variables.tf
│   └── terraform.tfvars         # Your values (not committed)
│
├── lambda_and_steps/            # Step 2 of infrastructure: Lambda, Step Function, IAM, SES, schedule
│   ├── main.tf
│   ├── variables.tf
│   └── terraform.tfvars         # Your values, including email addresses (not committed)
│
└── local_tests/                 # Screenshots of a successful local test run
```

---

## 🧰 Before You Start (One-Off Setup)

You only need to do this once per computer.

### 1. Install the tools

| Tool | Why you need it | Install guide |
|---|---|---|
| **Docker Desktop** | Builds and runs the packaged app | https://www.docker.com/products/docker-desktop |
| **AWS CLI** | Lets your computer talk to AWS | https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html |
| **Terraform** | Creates the AWS resources from the `.tf` files | https://developer.hashicorp.com/terraform/install |

Check they're installed by opening a terminal and running:

```bash
docker --version
aws --version
terraform --version
```

Each command should print a version number. Also make sure **Docker Desktop is open and running** before using any of the `.sh` scripts.

### 2. Connect your computer to AWS

```bash
aws configure
```

Enter the **Access Key ID**, **Secret Access Key** and region `eu-west-2` when asked. Ask your AWS administrator for the keys if you don't have them. **Never share these keys or commit them to Git.**

### 3. Make sure the data pipeline already exists

This report reads data that the main pipeline puts in S3 and catalogues with Glue (see the root [`terraform/`](../terraform/) and [`pipeline/`](../pipeline/) folders). The report expects:

- S3 bucket: `c26-aloysius-t3-s3`
- Glue/Athena database: `c26-aloysius-t3-glue-db` with tables `transactions`, `trucks` and `payment_methods`

### 4. Fill in the Terraform settings files

Both `ecr_terraform/` and `lambda_and_steps/` need a file called `terraform.tfvars`. This holds your values and **must not be committed** (it contains passwords). Use this template and replace the placeholder values:

```hcl
AWS_REGION = "eu-west-2"

S3_TAGS = {
  # any tags your organisation requires, e.g.
  Owner = "your-name"
}

ENVIRONMENT_PREFIX = "c26-aloysius-t3"   # used to name every resource
S3_TARGET_BUCKET   = "c26-aloysius-t3-s3"
S3_TARGET_PATH     = "t3-input/"
VPC_NAME           = "your-vpc-name"
SUBNET_1_NAME      = "your-subnet-name"

DB_HOST     = "your-database-host"
DB_NAME     = "your-database-name"
DB_USER     = "your-database-user"
DB_PORT     = "your-database-port"
DB_PASSWORD = "your-database-password"

# Only needed in lambda_and_steps/terraform.tfvars
SENDER_EMAIL    = "the-address-emails-come-from@example.com"
RECIPIENT_EMAIL = "the-address-that-receives-the-report@example.com"
```

> ℹ️ If you change `ENVIRONMENT_PREFIX`, the AWS resource names change too. The `.sh` scripts have `c26-aloysius-t3` and the AWS account ID `129033205317` written into them, so update those scripts to match.

---

## 🚀 Step-by-Step: Deploy to AWS

Run every command from inside the `report/` folder unless told otherwise.

### Step 1 – Create the image storage (ECR)

```bash
cd ecr_terraform
terraform init      # only needed the first time
terraform apply     # type "yes" when asked
cd ..
```

This creates an ECR repository called `c26-aloysius-t3-report-generator`.

### Step 2 – Build the app and upload it

```bash
bash Push_To_ECR_Pipeline.sh
```

This script:
1. Logs Docker in to your AWS account's ECR
2. Builds the Docker image (for the `linux/amd64` platform Lambda uses)
3. Tags it as `latest`
4. Uploads it to ECR

### Step 3 – Create the Lambda, permissions, email identities and schedule

```bash
cd lambda_and_steps
terraform init      # only needed the first time
terraform apply     # type "yes" when asked
cd ..
```

This creates:
- The **Lambda function** `c26-aloysius-t3-report-generator` (512 MB memory, 2-minute timeout)
- An **IAM role** that lets it read/write the S3 bucket, run Athena queries, read Glue tables and write logs
- A **Step Function** (`c26-aloysius-state-morning-report`) with two steps: run the Lambda, then send the email through SES. It has its own IAM role.
- **SES email identities** for the sender and recipient (see [How the Email Works](#-how-the-email-ses-works))
- An **EventBridge schedule** that starts the Step Function every day at 09:30 UTC

### Step 4 – ✉️ Confirm the email addresses (important!)

After Step 3, AWS sends a **verification email** to both `SENDER_EMAIL` and `RECIPIENT_EMAIL`. Open each inbox and **click the link** in the email from Amazon Web Services. Check your spam folder too.

Emails won't send until both addresses are verified. You can check their status in the AWS Console → **Amazon SES** → **Identities** (region **eu-west-2 / London**). Both should say **Verified**.

### Step 5 – Try it

Run the whole thing (report + email) by starting the Step Function. Replace `<account-id>` with your AWS account ID:

```bash
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:eu-west-2:<account-id>:stateMachine:c26-aloysius-state-morning-report \
  --region eu-west-2
```

An email with a link to the report should arrive. You can also click **Start execution** on the state machine in the AWS Console and watch each step turn green.

To test only the Lambda (no email is sent, it just returns the details):

```bash
aws lambda invoke \
  --function-name c26-aloysius-t3-report-generator \
  --region eu-west-2 \
  response.json

cat response.json
```

You should see `"statusCode": 200` and a `report_url`.

To watch the logs live:

```bash
aws logs tail /aws/lambda/c26-aloysius-t3-report-generator --follow --region eu-west-2
```

---

## 🔄 Updating the Report After Code Changes

When you change `create_report.py` you need **two** steps:

```bash
bash Push_To_ECR_Pipeline.sh   # 1. build and upload the new image
bash Pull_Image.sh             # 2. tell the Lambda to use it
```

> ⚠️ **Why is step 2 needed?** When a Lambda is created from an image tagged `latest`, AWS locks it to *that exact image*. Uploading a new `latest` doesn't change the Lambda, and `terraform apply` won't either, because the address in the Terraform hasn't changed. [`Pull_Image.sh`](./Pull_Image.sh) runs `aws lambda update-function-code`, which makes the Lambda pick up the newest image. Give it about 30 seconds before testing.

If you change **settings** in `terraform.tfvars` or `main.tf` (for example, email addresses or the Step Function), run `terraform apply` in `lambda_and_steps/` again.

---

## 🧪 Testing on Your Own Computer

You can run the exact same Docker image locally before uploading it.

### 1. Create `report/.env`

Create a file called `.env` in the `report/` folder:

```env
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_REGION=eu-west-2

S3_BUCKET_NAME=c26-aloysius-t3-s3
DATABASE_NAME=c26-aloysius-t3-glue-db
S3_OUTPUT_LOCATION=s3://c26-aloysius-t3-s3/t3-output/

SES_SENDER_EMAIL=the-address-emails-come-from@example.com
RECIPIENT_EMAIL=the-address-that-receives-the-report@example.com
```

> ⚠️ Docker reads this file literally. Use plain `KEY=value` lines with **no quotes** and **no `export`** in front. This file is separate from Terraform: changing an email in `terraform.tfvars` does **not** change it here, and vice versa.

### 2. Start the app (Terminal 1)

```bash
bash Lambda_Local_Image.sh
```

This builds the image and starts it on your computer, pretending to be AWS Lambda on port 9000. Leave this terminal open; the logs appear here.

### 3. Trigger a run (Terminal 2)

Open a second terminal in the `report/` folder:

```bash
bash Lambda_Local_Test_Image.sh
```

Terminal 1 will show the data being loaded, the report being uploaded and the email being sent. Terminal 2 shows the final result. See [`local_tests/`](./local_tests/) for screenshots of a successful run.

> ℹ️ A local test **really** uploads to S3 using your real AWS account. It does **not** send an email, because the email is now sent by the Step Function. The result in Terminal 2 contains the email subject, body and report link.

---

## 📧 How the Email (SES) Works

### What SES is

**Amazon Simple Email Service (SES)** is AWS's email-sending service. Our Step Function asks SES to send the email; SES then delivers it to the recipient's inbox (e.g. Gmail).

### What happens on each run

1. After uploading the report, the Lambda creates a **pre-signed link** to it in S3. This is a special private URL that lets someone download that one file **without an AWS login**, and it **expires after 24 hours**. The S3 bucket itself stays private.
2. The Lambda **returns** the email subject (`Your Report is Ready`), an HTML body and a plain-text body, each containing the link.
3. The Step Function's **SendEmail** step passes these to SES (`sendEmail`) with:
   - **From:** `SENDER_EMAIL`
   - **To:** `RECIPIENT_EMAIL`
4. SES checks the sender is allowed to send, then delivers the email.

### How I've set it up

| Part | How it's configured | File |
|---|---|---|
| **Email addresses** | `SENDER_EMAIL` and `RECIPIENT_EMAIL` variables | `lambda_and_steps/terraform.tfvars` |
| **Sending the email** | The `SendEmail` step in the Step Function uses the sender, recipient and the subject/body returned by the Lambda | `lambda_and_steps/main.tf` (`aws_sfn_state_machine`) |
| **Verifying the addresses** | Two `aws_ses_email_identity` resources (`sender_email` and `receiver_email`) register both addresses with SES, which triggers the verification emails | `lambda_and_steps/main.tf` (section 4) |
| **Permission to send** | The Step Function's IAM policy includes `ses:SendEmail` and `ses:SendRawEmail` (the Lambda no longer needs them) | `lambda_and_steps/main.tf` (`sfn_permissions`) |
| **Region** | SES is used in `eu-west-2` (London); identities are **per region** | `AWS_REGION` in code / tfvars |
| **Building the message** | The end of `lambda_handler` returns `email_subject`, `email_body_html`, `email_body_text` and `report_url` | `generator/create_report.py` |

### Things to know

- **🧪 SES "sandbox" mode.** New AWS accounts start in the SES sandbox. In the sandbox you can only send **to and from verified addresses**, which is why the recipient is verified as well as the sender. To email anyone without verifying them, request **production access** in the SES console (Account dashboard → *Request production access*).
- **📮 Choosing a sender address.** The sender must be an address whose domain allows SES to send on its behalf. I originally used a work address (`@sigmalabs.co.uk`). Gmail **rejected** those emails with a *"Delivery Status Notification (Failure)"*, because that domain has strict anti-spoofing rules (DMARC) and hadn't authorised SES. I switched the sender to a **Gmail address**, which works. To send from a company domain, the **whole domain** must be verified in SES with DKIM, which needs access to the domain's DNS settings.
- **⏳ The link expires.** The emailed link only works for 24 hours. After that, a new run creates a new link.
- **🔁 Changing addresses.** Update `terraform.tfvars` → `terraform apply` → click the new verification email. For local testing, also update `report/.env`.

---

## ⚙️ Settings Reference

### ⏰ Schedule

The schedule is set in `lambda_and_steps/main.tf` (`aws_scheduler_schedule.daily_report_schedule`) using a "cron" expression in **UTC**. It starts the **Step Function**, not the Lambda directly.

| Goal | `schedule_expression` |
|---|---|
| Once a day at 09:30 UTC (**current setting**) | `cron(30 9 * * ? *)` |
| Every 20 minutes (handy for testing) | `cron(*/20 * * * ? *)` |

After changing it, run `terraform apply` in `lambda_and_steps/`.