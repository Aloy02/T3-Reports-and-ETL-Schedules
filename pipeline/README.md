# 🚚 Food Truck ETL Pipeline

This pipeline automatically copies new food truck sales from the company database into AWS, cleans them up, and makes them ready to analyse. It runs on its own **every 3 hours** in the cloud, so once it's set up nobody has to press anything.

The [dashboard](../dashboard/README.md) and the [daily email report](../report/README.md) both read the data this pipeline produces, so **set this up first**.

## 📋 Table of Contents

- [What It Does](#-what-it-does)
- [How It Fits Together](#️-how-it-fits-together)
- [Project Structure](#-project-structure)
- [Before You Start (One-Off Setup)](#-before-you-start-one-off-setup)
- [Step-by-Step: Deploy to AWS](#-step-by-step-deploy-to-aws)
- [Updating the Pipeline After Code Changes](#-updating-the-pipeline-after-code-changes)
- [Running It on Your Own Computer](#-running-it-on-your-own-computer)
- [Where the Data Ends Up](#️-where-the-data-ends-up)
- [Settings Reference](#️-settings-reference)
- [Business Insights & Recommendations](#-business-insights--recommendations)

---

## 💡 What It Does

Each run goes through four stages, in order:

| # | Stage | What happens | Code |
|---|---|---|---|
| 1 | **Extract** | Connects to the company's MySQL database and copies out: <br>• the list of **trucks** and **payment methods** (a full fresh copy every time) <br>• only the **new sales** since the last run | [`src/extract.py`](./src/extract.py) |
| 2 | **Transform** | Throws away bad sales records: <br>• missing any required details (ID, truck, payment method, amount, time) <br>• an unknown payment method or truck <br>• a negative or non-numeric amount | [`src/transform.py`](./src/transform.py) |
| 3 | **Load** | Saves the clean data to S3 in **Parquet** format (a compact file type built for analysis). Sales are organised into one folder per day. | [`src/load.py`](./src/load.py) |
| 4 | **Crawl** | Starts an AWS **Glue crawler**, which scans the new files and updates the table definitions so they can be queried with **Athena** (SQL for files in S3) | [`src/crawl.py`](./src/crawl.py) |

[`src/pipeline.py`](./src/pipeline.py) runs the four stages one after another and logs what happens at each step.

### 🔖 How it avoids copying the same sales twice

After each successful extract, the pipeline saves the **highest sale ID it has seen** to a small file, `s3://c26-aloysius-t3-s3/state.json`. The next run only asks the database for sales with a **higher** ID. If there are no new sales, the extract stage says so and nothing new is added.

> To re-load everything from scratch, delete `state.json` from the bucket. The next run will then copy every sale again, so delete the old `t3-input/transactions/` folder too, or you'll get duplicates.

---

## 🏗️ How It Fits Together

```
 ⏰ EventBridge Scheduler (every 3 hours)
          │ starts
          ▼
 📦 ECS Fargate task (runs our Docker image from ECR)
          │
          ├─ 1. Extract ──▶ 🗄️ MySQL database (RDS)  ──▶ CSV copies in S3 (raw-data/, master-data/)
          ├─ 2. Transform ─▶ removes invalid sales
          ├─ 3. Load ─────▶ 🪣 S3 Parquet files (t3-input/)
          └─ 4. Crawl ────▶ 🕷️ Glue crawler ──▶ 📚 Glue database ──▶ 🔎 Athena
                                                                       │
                                                  used by 📊 Dashboard & 📧 Daily Report
```

| Piece | What it is | Where it's defined |
|---|---|---|
| **Docker image** | A packaged copy of the Python code and everything it needs | [`Dockerfile`](./Dockerfile) |
| **ECR repository** `c26-aloysius-t3-pipeline-image` | AWS's storage for the Docker image | [`../terraform/main.tf`](../terraform/main.tf) |
| **S3 bucket** `c26-aloysius-t3-s3` | Cloud storage where all the data is saved | [`../terraform/main.tf`](../terraform/main.tf) |
| **Glue database** `c26-aloysius-t3-glue-db` and **crawler** `c26-aloysius-t3-crawler` | Catalogues the S3 files as queryable tables | [`../terraform/main.tf`](../terraform/main.tf) |
| **ECS task definition** | Tells AWS how to run the image (0.25 vCPU, 512 MB) on the existing `c26-ecs-cluster` | [`../terraform/main.tf`](../terraform/main.tf) |
| **EventBridge schedule** | The timer that starts the pipeline every 3 hours | [`../terraform/main.tf`](../terraform/main.tf) |
| **IAM roles** | Permissions for ECS, Glue and EventBridge to do their jobs | [`../terraform/main.tf`](../terraform/main.tf) |
| **CloudWatch log group** `/ecs/c26-aloysius-t3-pipeline` | Stores the run logs for 7 days | [`../terraform/main.tf`](../terraform/main.tf) |

> ℹ️ The infrastructure for the pipeline lives in the **root [`terraform/`](../terraform/) folder**, not inside `pipeline/`.

---

## 📂 Project Structure

```
pipeline/
├── README.md                    # You are here
├── Dockerfile                   # Recipe for building the Docker image
├── .env                         # Your local settings and passwords (NOT committed – you create it)
│
├── Build_Image.sh               # Build the Docker image on your computer
├── Run_Image.sh                 # Run the built image once on your computer
├── Build_And_Run_Pipeline.sh    # Do both of the above in one go
├── Push_To_ECR_Pipeline.sh      # Log in to AWS, build the image and upload it to ECR
│
├── src/
│   ├── pipeline.py              # Runs all four stages in order
│   ├── connect.py               # Connects to the MySQL database
│   ├── extract.py               # Stage 1 – copy data out of the database
│   ├── transform.py             # Stage 2 – remove invalid sales
│   ├── load.py                  # Stage 3 – save to S3 as Parquet
│   ├── crawl.py                 # Stage 4 – start the Glue crawler
│   ├── logger.py                # Logging setup (screen + pipeline.log)
│   └── requirements.txt         # Python libraries the pipeline needs
│
├── requirements.txt             # Extra libraries for the analysis notebook
├── visualise.ipynb              # Notebook for exploring the data and making charts
├── Orders Per Food Truck.png    # Example chart from the notebook
└── Revenue Per Food Truck.png   # Example chart from the notebook

terraform/                       # (in the project root) All AWS infrastructure for the pipeline
├── main.tf
├── variables.tf
└── terraform.tfvars             # Your values, including DB password (not committed)
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
| **Python 3.14** *(optional)* | Only for running without Docker, or for the notebook | https://www.python.org/downloads/ |

Check they're installed by opening a terminal and running:

```bash
docker --version
aws --version
terraform --version
```

Each command should print a version number. Make sure **Docker Desktop is open and running** before using any of the `.sh` scripts.

### 2. Connect your computer to AWS

```bash
aws configure
```

Enter the **Access Key ID**, **Secret Access Key** and region `eu-west-2` when asked. Ask your AWS administrator for the keys if you don't have them. **Never share these keys or commit them to Git.**

### 3. Things that must already exist

The Terraform **looks up** these, rather than creating them, so ask your administrator to confirm they exist:

- A VPC and a public subnet (names go in `VPC_NAME` and `SUBNET_1_NAME`)
- An ECS cluster called **`c26-ecs-cluster`**
- The **MySQL database** holding the sales data, plus its host, name, username, password and port

### 4. Fill in the Terraform settings file

Create `terraform/terraform.tfvars` in the **project root** with your values. It holds passwords, so it **must not be committed** (it is already in `.gitignore`).

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
SUBNET_1_NAME      = "your-public-subnet-name"

DB_HOST     = "your-database-host"
DB_NAME     = "your-database-name"
DB_USER     = "your-database-user"
DB_PORT     = "your-database-port"
DB_PASSWORD = "your-database-password"
```

> ⚠️ The bucket name `c26-aloysius-t3-s3`, the crawler name and the AWS account ID `129033205317` are also **written directly into the Python code and `.sh` scripts**. If you change `ENVIRONMENT_PREFIX` or `S3_TARGET_BUCKET`, update [`src/extract.py`](./src/extract.py), [`src/transform.py`](./src/transform.py), [`src/load.py`](./src/load.py), [`src/crawl.py`](./src/crawl.py) and [`Push_To_ECR_Pipeline.sh`](./Push_To_ECR_Pipeline.sh) to match.

---

## 🚀 Step-by-Step: Deploy to AWS

### Step 1 – Create the AWS infrastructure

From the **project root**:

```bash
cd terraform
terraform init      # only needed the first time
terraform apply     # type "yes" when asked
cd ..
```

This creates the S3 bucket, the Glue database and crawler, the ECR repository, the ECS task definition, the IAM roles, the CloudWatch log group and the 3-hourly EventBridge schedule.

### Step 2 – Build the pipeline and upload it

```bash
cd pipeline
bash Push_To_ECR_Pipeline.sh
```

This script:
1. Logs Docker in to your AWS account's ECR
2. Creates the ECR repository `c26-aloysius-t3-pipeline-image` if it doesn't already exist
3. Builds the Docker image for the `linux/amd64` platform AWS uses
4. Tags it as `latest` and uploads it

### Step 3 – Wait for (or trigger) a run

The schedule runs the pipeline at **00:00, 03:00, 06:00 … 21:00 UTC**. To check that a run worked, watch the logs:

```bash
aws logs tail /ecs/c26-aloysius-t3-pipeline --follow --region eu-west-2
```

A successful run ends with `# ETL PIPELINE COMPLETED SUCCESSFULLY`.

To check that the crawler ran:

```bash
aws glue get-crawler --name c26-aloysius-t3-crawler --region eu-west-2
```

After the first successful run and crawl, the Glue database has three tables: **`transactions`**, **`trucks`** and **`payment_methods`**. The dashboard and report can now use them.

---

## 🔄 Updating the Pipeline After Code Changes

```bash
cd pipeline
bash Push_To_ECR_Pipeline.sh
```

That's all. Each scheduled run starts a **brand new** ECS task, which downloads the latest image at that moment. The next run after your push uses the new code automatically. (This differs from the report's Lambda, which needs an extra step.)

If you change **settings** in `terraform/terraform.tfvars` or `terraform/main.tf`, run `terraform apply` in the `terraform/` folder again.

---

## 🧪 Running It on Your Own Computer

> ⚠️ A local run uses the **real** database and the **real** S3 bucket. It moves the `state.json` bookmark forward, so the next scheduled cloud run won't re-copy those sales.

### 1. Create `pipeline/.env`

Create a file called `.env` in the `pipeline/` folder:

```env
DB_HOST=your-database-host
DB_NAME=your-database-name
DB_USER=your-database-user
DB_PASSWORD=your-database-password
DB_PORT=your-database-port

AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_DEFAULT_REGION=eu-west-2
```

If your AWS keys are temporary, also add `AWS_SESSION_TOKEN=...`.

> ⚠️ Docker reads this file literally. Use plain `KEY=value` lines with **no quotes** and **no `export`** in front.

### 2a. Run with Docker (recommended)

```bash
cd pipeline
bash Build_And_Run_Pipeline.sh
```

This builds the image (`Build_Image.sh`) and then runs it once (`Run_Image.sh`). The logs appear in your terminal, and the container removes itself when finished.

If you get `Permission denied`, run `chmod +x *.sh` once and try again.

### 2b. Run with Python directly (optional)

```bash
cd pipeline
python3 -m venv .venv
source .venv/bin/activate
pip install -r src/requirements.txt

set -a; source .env; set +a     # load the .env settings
cd src
python pipeline.py
```

Run the commands from inside `src/`, because the code uses folder paths relative to it. You can also run a single stage, e.g. `python extract.py` or `python crawl.py`.

#### Logging options

| Option | Effect |
|---|---|
| `python pipeline.py -w DEBUG` | Show more detail (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`) |
| `python pipeline.py -d` | Hide messages on screen and only write them to `src/pipeline.log` |

### 3. Explore the data (optional)

Open [`visualise.ipynb`](./visualise.ipynb) in VS Code or Jupyter (`pip install -r requirements.txt` first) and run all cells to create charts like `Orders Per Food Truck.png` and `Revenue Per Food Truck.png`.

---

## 🗂️ Where the Data Ends Up

Everything is stored in the S3 bucket **`c26-aloysius-t3-s3`**:

| Location | What's in it | Written by |
|---|---|---|
| `state.json` | Bookmark: the highest sale ID already copied | Extract |
| `raw-data/FACT_Transaction.csv` | New sales from the latest run (before cleaning) | Extract |
| `master-data/DIM_Truck.csv` | Full list of trucks | Extract |
| `master-data/DIM_Payment_Method.csv` | Full list of payment methods | Extract |
| `t3-input/transactions/date_partition=YYYY_MM_DD/` | **Clean** sales, one folder per day, **added to** each run | Load |
| `t3-input/trucks/` | Trucks table, **replaced** each run | Load |
| `t3-input/payment_methods/` | Payment methods table, **replaced** each run | Load |

The Glue crawler only scans `t3-input/`. That folder becomes the Athena tables `transactions`, `trucks` and `payment_methods` in the `c26-aloysius-t3-glue-db` database.

---

## ⚙️ Settings Reference

### Environment variables

| Variable | What it's for | Set where |
|---|---|---|
| `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_PORT` | How to connect to the MySQL database | `terraform.tfvars` (cloud) / `pipeline/.env` (local) |
| `AWS_DEFAULT_REGION` | AWS region (`eu-west-2`) | Set by Terraform (cloud) / `pipeline/.env` (local) |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | Your AWS login | **Local only.** In the cloud the ECS task uses its IAM role instead |

### ⏰ Schedule

Set in [`../terraform/main.tf`](../terraform/main.tf) (`aws_scheduler_schedule.trigger_ecs`), in **UTC**:

| Goal | `schedule_expression` |
|---|---|
| Every 3 hours (**current setting**) | `cron(0 */3 * * ? *)` |
| Every 5 minutes (for testing; commented out in the file) | `cron(*/5 * * * ? *)` |

Run `terraform apply` after changing it.

---

## 💼 Business Insights & Recommendations

Analysis of the cleaned transaction data reveals the following patterns and actionable insights:

### Key Findings

**Market Leaders:** Kings of Kebabs (1,322 orders, highest revenue) and Burrito Madness (1,300 orders) demonstrate strong, stable customer demand. Their consistent order volumes and profitability make them the foundation of the business.

**Demand Volatility:** Burrito Madness and Cupcakes by Michelle experience significant day-to-day order fluctuations, reaching peaks of 320+ orders but also steep drops. In contrast, Kings of Kebabs maintains steady, predictable demand patterns.

**Underperformers:** Hartmann's Jellied Eels remains consistently low with only 291 total orders and minimal revenue, indicating limited market appeal. Emerging trucks like SuperSmoothie and Yoghurt Heaven show early market entry but require strategic focus to grow.

### Strategic Recommendations

1. **Stabilise High-Volatility Trucks:** Investigate demand drivers for Burrito Madness and Cupcakes by Michelle. Implement promotional strategies or adjust inventory management to reduce order volatility and capture peak-demand periods more effectively.

2. **Evaluate Underperforming Trucks:** Conduct a detailed review of Hartmann's Jellied Eels. Determine whether to invest in marketing, rebrand, or reallocate resources to higher-performing or emerging trucks.
