# 🚚 Food Truck Report Scheduler

An end-to-end automated system that collects food truck sales data, analyzes it, and delivers insights via a daily email report and interactive analytics dashboard.

## 📋 What It Does

**Every 3 hours:** A pipeline automatically pulls new sales from the database, cleans the data, and stores it in AWS.

**Every day:** A report generator creates an HTML report of yesterday's sales and emails a link to it.

**Anytime:** An interactive dashboard lets you explore sales trends, truck performance, and payment methods—filtered by date and truck.

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Data Collection                          │
│  ⏰ EventBridge (every 3 hours) ──▶ 📦 ECS Fargate Task    │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
         🚚 Pipeline (ETL)
         • Extract from MySQL
         • Transform & clean
         • Load to S3 as Parquet
         • Crawl with AWS Glue
                 │
         ┌───────┴──────────┐
         ▼                  ▼
    🪣 S3 Data Lake    📊 Glue Catalog
         │                  │
         └────────┬─────────┘
                  ▼
            🔎 Athena (SQL)
                  │
        ┌─────────┴──────────┐
        ▼                    ▼
    📧 Report Generator   📊 Dashboard
    (Daily Lambda)        (Streamlit App)
        │                    │
        ▼                    ▼
    SES Email           Web Browser
```

---

## 📂 Project Structure

| Folder | Purpose |
|--------|---------|
| **[pipeline/](./pipeline/)** | ETL pipeline (Extract, Transform, Load). Runs automatically every 3 hours in ECS Fargate. |
| **[report/](./report/)** | Daily report generator. Lambda function that builds an HTML report and emails it. |
| **[dashboard/](./dashboard/)** | Interactive Streamlit dashboard. Explore trends, filter by date/truck, see charts. |
| **[terraform/](./terraform/)** | Infrastructure as Code. Defines all AWS resources (S3, Glue, IAM, etc.). |

---

## 🚀 Quick Start

### Option 1: Run Everything on AWS (Recommended)
```bash
# 1. Set up infrastructure
cd terraform
terraform init
terraform apply

# 2. Deploy pipeline
cd ../pipeline
./Build_And_Run_Pipeline.sh
./Push_To_ECR_Pipeline.sh

# 3. Deploy report generator
cd ../report
./Build_And_Run_Image.sh
./Push_To_ECR_Pipeline.sh

# 4. Run dashboard
cd ../dashboard
./Build_And_Run_Dashboard.sh
```

### Option 2: Run Locally (Development)
```bash
# Pipeline
cd pipeline
python -m src.pipeline

# Dashboard (requires pipeline to have run once)
cd dashboard
streamlit run app/app.py

# Report generator
cd report
python generator/create_report.py
```

---

## 📊 What You Get

**📈 Pipeline Output:**
- Clean sales data stored daily in S3
- Queryable via AWS Athena (SQL)
- Automatically indexed with Glue

**📧 Daily Email:**
- Hourly revenue breakdown by truck
- Payment method split (card vs cash)
- Truck performance comparison
- 24-hour link to download the full report

**📊 Interactive Dashboard:**
- Real-time charts and metrics
- Filter by date range and trucks
- Three tabs: Truck Performance, Spend & Pricing, Payment Methods
- Cached for performance (updates every 10 minutes)

---

## 🔧 Key Technologies

- **Data Processing:** Python (pandas, SQLAlchemy)
- **Cloud Services:** AWS S3, Glue, Athena, Lambda, ECS Fargate, EventBridge, SES
- **Analytics:** Streamlit (dashboard), Plotly (charts)
- **Infrastructure:** Terraform (IaC)
- **Containerization:** Docker

---

## 📚 Where to Go Next

- **Getting started with the pipeline?** → [pipeline/README.md](./pipeline/README.md)
- **Setting up the report generator?** → [report/README.md](./report/README.md)
- **Running the dashboard?** → [dashboard/README.md](./dashboard/README.md)

---

## ⚙️ How the Pieces Work Together

1. **Pipeline** extracts new sales from the database every 3 hours and stores them in S3
2. **Glue Crawler** automatically catalogs the data so it can be queried
3. **Report Generator** wakes up daily, queries Athena for yesterday's data, and emails a summary
4. **Dashboard** lets you explore the data interactively whenever you want

All services run automatically in the cloud once deployed. No manual intervention needed.

---

## 🛠️ Common Tasks

| Task | Command |
|------|---------|
| Deploy all to AWS | `cd terraform && terraform apply` |
| Run pipeline locally | `cd pipeline && python -m src.pipeline` |
| Start dashboard | `cd dashboard && streamlit run app/app.py` |
| Check pipeline logs | View CloudWatch Logs in AWS Console |
| Test report locally | `cd report && python generator/create_report.py` |
| Re-sync all data | Delete `s3://.../state.json` and re-run pipeline |

---

**Questions?** Check the README in each component folder for detailed instructions and troubleshooting.
