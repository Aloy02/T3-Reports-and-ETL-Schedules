# 📊 Food Truck Analytics Dashboard

An interactive website that shows food truck sales, truck performance and payment trends. You can filter by date and by truck, and every chart updates instantly.

It reads the data produced by the [ETL pipeline](../pipeline/README.md), so the pipeline must be set up and have run at least once first.

## 📋 Table of Contents

- [What You'll See](#-what-youll-see)
- [How It Fits Together](#️-how-it-fits-together)
- [Project Structure](#-project-structure)
- [Before You Start (One-Off Setup)](#-before-you-start-one-off-setup)
- [Running the Dashboard](#️-running-the-dashboard)
- [Uploading the Image to AWS (ECR)](#️-uploading-the-image-to-aws-ecr)
- [Settings Reference](#️-settings-reference)
- [Technologies Used](#️-technologies-used)

---

## 👀 What You'll See

**Headline figures** at the top: **Total Revenue**, **Total Orders** and **Average Spend per Order** for whatever you've filtered.

**Sidebar filters (🔍 Controls & Filters):**
- **📅 Date Range:** choose which days to include
- **Trucks:** pick one, several or all trucks

**Three tabs:**

| Tab | What it shows |
|---|---|
| **📈 Truck Performance** | Revenue for each truck over time, plus a summary table per truck |
| **💰 Spend & Pricing** | How much customers spend per order at each truck (£) |
| **💳 Payment Methods** | Card vs cash split, revenue per truck by payment type, and which trucks accept cards |

You can hover over any chart to see exact figures. The data is cached for **10 minutes**, so new pipeline runs can take up to 10 minutes to appear (or refresh the page after that).

---

## 🏗️ How It Fits Together

```
 🚚 Pipeline ──▶ 🪣 S3 (Parquet) ──▶ 🕷️ Glue crawler ──▶ 🔎 Athena tables
                                                              │
                                                              ▼
                                         📊 Dashboard (Streamlit, this folder)
                                                              │
                                                              ▼
                                               🌐 Your browser: http://localhost:8501
```

The dashboard runs three Athena queries (`transactions`, `trucks`, `payment_methods`) against the Glue database `c26-aloysius-t3-glue-db`, joins the results and draws the charts.

---

## 📂 Project Structure

```
dashboard/
├── README.md                    # You are here
├── Dockerfile                   # Recipe for building the Docker image
├── .env                         # Your local settings (NOT committed – you create it)
│
├── Build_Image.sh               # Build the Docker image
├── Run_Image.sh                 # Run the image and open it on port 8501
├── Build_And_Run_Dashboard.sh   # Do both of the above in one go
├── Push_To_ECR_Pipeline.sh      # Log in to AWS, build the image and upload it to ECR
│
└── app/
    ├── app.py                   # The dashboard itself (Streamlit)
    └── requirements.txt         # Python libraries the dashboard needs
```

---

## 🧰 Before You Start (One-Off Setup)

### 1. Install the tools

| Tool | Why you need it | Install guide |
|---|---|---|
| **Docker Desktop** | Builds and runs the packaged app (recommended) | https://www.docker.com/products/docker-desktop |
| **AWS CLI** | Lets your computer talk to AWS | https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html |
| **Python 3.14** *(optional)* | Only if you want to run it without Docker | https://www.python.org/downloads/ |

Make sure **Docker Desktop is open and running** before using any of the `.sh` scripts.

### 2. Connect your computer to AWS

```bash
aws configure
```

Enter the **Access Key ID**, **Secret Access Key** and region `eu-west-2` when asked. The Docker scripts **share these saved credentials** with the container (read-only), so you don't need to put AWS keys in `.env`.

Your AWS user needs permission to run **Athena** queries, read the **Glue** database, and read/write the **S3** bucket `c26-aloysius-t3-s3` (Athena saves its query results there).

### 3. Create `dashboard/.env`

Create a file called `.env` in the `dashboard/` folder:

```env
AWS_REGION=eu-west-2
DATABASE_NAME=c26-aloysius-t3-glue-db
S3_OUTPUT_LOCATION=s3://c26-aloysius-t3-s3/t3-output/
```

> ⚠️ Docker reads this file literally. Use plain `KEY=value` lines with **no quotes** and **no `export`** in front. This file is already in `.gitignore`; never commit it.

---

## ▶️ Running the Dashboard

### Option 1: Docker (recommended)

```bash
cd dashboard
bash Build_And_Run_Dashboard.sh
```

This builds the image (`Build_Image.sh`) and then starts it (`Run_Image.sh`). When the terminal shows that Streamlit is running, open **http://localhost:8501** in your browser.

Press **Ctrl + C** in the terminal to stop it. After the first build, you can start it again more quickly with `bash Run_Image.sh`.

If you get `Permission denied`, run `chmod +x *.sh` once and try again.

### Option 2: Python directly

```bash
cd dashboard
python3 -m venv .venv
source .venv/bin/activate
pip install -r app/requirements.txt

streamlit run app/app.py
```

Then open **http://localhost:8501**. The app loads `.env` automatically and uses the AWS credentials from `aws configure`.

---

## ☁️ Uploading the Image to AWS (ECR)

```bash
cd dashboard
bash Push_To_ECR_Pipeline.sh
```

This logs in to ECR, builds the image for `linux/amd64`, tags it and uploads it to the repository **`c26-aloysius-t3-dashboard-image`**.

> ⚠️ **No Terraform creates this repository or hosts the dashboard.** The script only uploads the image.
> - If the repository doesn't exist yet, create it once:
>   ```bash
>   aws ecr create-repository --repository-name c26-aloysius-t3-dashboard-image --region eu-west-2
>   ```
> - To make the dashboard available online, you'd need to run the image yourself (for example as an ECS service). That isn't set up in this project.

The AWS account ID `129033205317` is written into the script. Change it if you're using a different account.

---

## ⚙️ Settings Reference

| Variable | What it's for | Example |
|---|---|---|
| `AWS_REGION` | AWS region to query | `eu-west-2` |
| `DATABASE_NAME` | Glue/Athena database holding the tables | `c26-aloysius-t3-glue-db` |
| `S3_OUTPUT_LOCATION` | Where Athena saves temporary query results | `s3://c26-aloysius-t3-s3/t3-output/` |

All three are **required**; the dashboard has no defaults for them.

---

## 🛠️ Technologies Used

| Technology | Purpose |
|---|---|
| **Streamlit** | Turns the Python script into a web page |
| **Plotly** | Interactive charts |
| **Pandas** | Joining and summarising the data |
| **AWS Wrangler** | Runs Athena queries and returns the results as tables |
| **Boto3** | Connects to AWS |
| **python-dotenv** | Loads settings from `.env` |
| **Docker** | Packages the app so it runs the same on any computer |
