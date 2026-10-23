"""
Generate a Standalone Interactive HTML Daily Report (Yesterday's Data)
and upload directly to AWS S3, then send email via AWS SES.
"""

import html
from os import environ
import boto3
import pandas as pd
import awswrangler as wr
import plotly.express as px
import plotly.io as pio
from dotenv import load_dotenv

# Load local .env variables if running locally
load_dotenv()

S3_BUCKET_NAME = environ.get("S3_BUCKET_NAME", "c26-aloysius-t3-s3")
REPORT_S3_KEY = "reports/food_truck_daily_report.html"

AWS_REGION = environ.get("AWS_REGION", "eu-west-2")

s3_client = boto3.client("s3", region_name=AWS_REGION)

SENDER = environ.get("SES_SENDER_EMAIL")
RECIPIENT = environ.get("RECIPIENT_EMAIL")

# -----------------------------------------------------------------------------
# 1. Data Extraction (Athena - Filtered for Yesterday)
# -----------------------------------------------------------------------------


def load_yesterday_data() -> pd.DataFrame:
    database_name = environ.get("DATABASE_NAME", "c26-aloysius-t3-glue-db")
    s3_output_location = environ.get(
        "S3_OUTPUT_LOCATION", "s3://c26-aloysius-t3-s3/t3-output/"
    )

    if not s3_output_location.endswith("/"):
        s3_output_location += "/"

    my_session = boto3.Session(region_name=AWS_REGION)

    # Filter directly in Athena for yesterday's records (Europe/London time zone adjusted)
    query_transactions = """
    SELECT transaction_id, truck_id, payment_method_id, total, at
    FROM transactions
    WHERE CAST(at AT TIME ZONE 'Europe/London' AS DATE) = CURRENT_DATE - INTERVAL '1' DAY
    ORDER BY at ASC;
    """

    df_transactions = wr.athena.read_sql_query(
        sql=query_transactions,
        database=database_name,
        s3_output=s3_output_location,
        boto3_session=my_session,
    )

    if df_transactions.empty:
        return df_transactions

    df_trucks = wr.athena.read_sql_query(
        sql="SELECT * FROM trucks;",
        database=database_name,
        s3_output=s3_output_location,
        boto3_session=my_session,
    )

    df_payment_methods = wr.athena.read_sql_query(
        sql="SELECT * FROM payment_methods;",
        database=database_name,
        s3_output=s3_output_location,
        boto3_session=my_session,
    )

    df = pd.merge(df_transactions, df_trucks, on="truck_id", how="inner")
    df = pd.merge(df, df_payment_methods, on="payment_method_id", how="left")

    df["at"] = pd.to_datetime(df["at"])
    df["total"] = df["total"] / 100.0

    if "name" in df.columns:
        df["truck_label"] = df["name"]
    elif "truck_name" in df.columns:
        df["truck_label"] = df["truck_name"]
    else:
        df["truck_label"] = "Truck " + df["truck_id"].astype(str)

    if "payment_method" in df.columns:
        df["payment_method"] = df["payment_method"].str.title()
    else:
        df["payment_method"] = "Unknown"

    return df


# -----------------------------------------------------------------------------
# 2. Build Charts
# -----------------------------------------------------------------------------


CHART_CONFIG = {
    "responsive": True,
    "displayModeBar": False,
    "scrollZoom": False,
    "doubleClick": False,
    "showTips": False,
}


def build_charts(df: pd.DataFrame) -> dict:
    unique_trucks = sorted(df["truck_label"].unique())

    plotly_colors = px.colors.qualitative.Plotly
    truck_color_map = {
        truck: plotly_colors[i % len(plotly_colors)]
        for i, truck in enumerate(unique_trucks)
    }

    df["hour"] = df["at"].dt.hour

    hourly_sales = (
        df.groupby(["hour", "truck_label"])
        .agg(total=("total", "sum"), orders=("transaction_id", "count"))
        .reset_index()
    )

    if not df.empty:
        min_hour = df["hour"].min()
        max_hour = df["hour"].max()
        active_hours = list(range(min_hour, max_hour + 1))
    else:
        active_hours = list(range(24))

    multi_idx = pd.MultiIndex.from_product(
        [active_hours, unique_trucks], names=["hour", "truck_label"]
    )

    hourly_truck_sales = (
        hourly_sales.set_index(["hour", "truck_label"])
        .reindex(multi_idx, fill_value=0)
        .reset_index()
    )

    hourly_truck_sales["total"] = hourly_truck_sales["total"].astype(float)
    hourly_truck_sales["orders"] = hourly_truck_sales["orders"].astype(int)
    hourly_truck_sales["hour_label"] = hourly_truck_sales["hour"].apply(
        lambda h: f"{h:02d}:00"
    )

    fig_line = px.line(
        hourly_truck_sales,
        x="hour_label",
        y="total",
        color="truck_label",
        color_discrete_map=truck_color_map,
        custom_data=["orders"],
        labels={
            "hour_label": "Hour of Day",
            "total": "Revenue (£)",
            "truck_label": "Truck",
        },
        title="Yesterday's Hourly Revenue Trend per Truck",
    )

    fig_line.update_traces(
        hovertemplate="<b>%{x}</b><br>Revenue: £%{y:,.2f}<br>Orders: %{customdata[0]}<extra></extra>"
    )
    fig_line.update_xaxes(type="category", tickangle=-45)
    fig_line.update_layout(
        margin=dict(l=20, r=20, t=40, b=80),
        hovermode="x unified",
        autosize=True,
    )

    # Chart 2
    truck_spend = (
        df.groupby("truck_label")["total"]
        .agg(Total_Spend="sum", Avg_Spend="mean")
        .reset_index()
        .sort_values(by="Total_Spend", ascending=False)
    )

    fig_spend = px.bar(
        truck_spend,
        x="truck_label",
        y="Total_Spend",
        color="truck_label",
        color_discrete_map=truck_color_map,
        labels={"truck_label": "Truck", "Total_Spend": "Total Spend (£)"},
        text="Total_Spend",
        title="Yesterday's Revenue by Truck",
    )
    fig_spend.update_traces(
        texttemplate="£%{text:,.2f}", textposition="outside")
    fig_spend.update_layout(
        showlegend=False, margin=dict(l=20, r=20, t=40, b=20), autosize=True
    )

    # Charts 3 & 4
    pay_summary = (
        df.groupby("payment_method")["total"].agg(
            ["sum", "count"]).reset_index()
    )
    fig_pie = px.pie(
        pay_summary,
        names="payment_method",
        values="sum",
        title="Yesterday's Fleet Revenue by Payment Method",
        hole=0.4,
        color="payment_method",
        color_discrete_map={"Card": "#3B82F6", "Cash": "#10B981"},
    )
    fig_pie.update_traces(textinfo="percent+label")
    fig_pie.update_layout(autosize=True)

    truck_pay = (
        df.groupby(["truck_label", "payment_method"])[
            "total"].sum().reset_index()
    )
    fig_truck_pay = px.bar(
        truck_pay,
        x="truck_label",
        y="total",
        color="payment_method",
        barmode="stack",
        title="Revenue per Truck by Payment Method (£)",
        labels={
            "truck_label": "Truck",
            "total": "Revenue (£)",
            "payment_method": "Payment Method",
        },
        color_discrete_map={"Card": "#3B82F6", "Cash": "#10B981"},
    )
    fig_truck_pay.update_layout(autosize=True)

    # Legends below the plot and tighter titles so charts fit narrow screens
    for fig in (fig_line, fig_spend, fig_pie, fig_truck_pay):
        # Keep hover tooltips but block zoom/pan/selection
        fig.update_layout(dragmode=False)
        fig.update_xaxes(fixedrange=True)
        fig.update_yaxes(fixedrange=True)
        fig.update_layout(
            title=dict(font=dict(size=15), x=0.5, xanchor="center"),
            legend=dict(orientation="h", yanchor="top",
                        y=-0.25, x=0.5, xanchor="center"),
            font=dict(size=11),
        )
    fig_spend.update_xaxes(tickangle=-30, automargin=True)
    fig_truck_pay.update_xaxes(tickangle=-30, automargin=True)
    fig_spend.update_layout(margin=dict(l=10, r=10, t=50, b=20))
    fig_pie.update_layout(margin=dict(l=10, r=10, t=50, b=20))
    fig_truck_pay.update_layout(margin=dict(l=10, r=10, t=50, b=20))
    fig_line.update_layout(margin=dict(l=10, r=10, t=50, b=80))

    return {
        "chart_line": pio.to_html(
            fig_line,
            full_html=False,
            include_plotlyjs="cdn",
            config=CHART_CONFIG,
        ),
        "chart_spend": pio.to_html(
            fig_spend,
            full_html=False,
            include_plotlyjs=False,
            config=CHART_CONFIG,
        ),
        "chart_pie": pio.to_html(
            fig_pie,
            full_html=False,
            include_plotlyjs=False,
            config=CHART_CONFIG,
        ),
        "chart_truck_pay": pio.to_html(
            fig_truck_pay,
            full_html=False,
            include_plotlyjs=False,
            config=CHART_CONFIG,
        ),
    }


# -----------------------------------------------------------------------------
# 3. Save String directly to S3
# -----------------------------------------------------------------------------


def save_html_to_s3(html_content: str, bucket_name: str, s3_key: str) -> None:
    s3_client.put_object(
        Bucket=bucket_name,
        Key=s3_key,
        Body=html_content.encode("utf-8"),
        ContentType="text/html",
        CacheControl="no-cache, no-store, must-revalidate",
    )


# -----------------------------------------------------------------------------
# 4. Generate & Upload Pipeline
# -----------------------------------------------------------------------------


def generate_and_upload_report(df: pd.DataFrame) -> None:
    yesterday_date_str = (
        df["at"].dt.strftime("%B %d, %Y").iloc[0] if not df.empty else "N/A"
    )

    total_revenue = df["total"].sum() if not df.empty else 0.0
    total_orders = len(df)
    avg_spend = df["total"].mean() if total_orders > 0 else 0.0

    truck_summary = (
        df.groupby("truck_label")
        .agg(
            Total_Revenue=("total", "sum"),
            Order_Count=("total", "count"),
            Avg_Order_Value=("total", "mean"),
        )
        .reset_index()
        .sort_values(by="Total_Revenue", ascending=False)
    )

    capability_df = (
        df.groupby("truck_label")
        .agg(
            Total_Orders=("transaction_id", "count"),
            Card_Orders=("payment_method", lambda x: (x == "Card").sum()),
            Cash_Orders=("payment_method", lambda x: (x == "Cash").sum()),
            Total_Revenue=("total", "sum"),
        )
        .reset_index()
    )

    capability_df["Acceptance"] = capability_df["Card_Orders"].apply(
        lambda x: "💳 Accepts Card & Cash" if x > 0 else "💵 Cash Only"
    )
    capability_df["Card_Share"] = (
        capability_df["Card_Orders"]
        / capability_df["Total_Orders"].replace(0, 1)
        * 100
    ).fillna(0)

    charts = build_charts(df)

    summary_rows = "".join(
        f"<tr><td>{html.escape(str(r['truck_label']))}</td>"
        f"<td>£{r['Total_Revenue']:,.2f}</td>"
        f"<td>{r['Order_Count']:,}</td>"
        f"<td>£{r['Avg_Order_Value']:,.2f}</td></tr>"
        for _, r in truck_summary.iterrows()
    )

    capability_rows = "".join(
        f"<tr><td>{html.escape(str(r['truck_label']))}</td>"
        f"<td>{r['Acceptance']}</td>"
        f"<td>{r['Total_Orders']:,}</td>"
        f"<td>{r['Card_Orders']:,}</td>"
        f"<td>{r['Cash_Orders']:,}</td>"
        f"<td>{r['Card_Share']:.1f}%</td>"
        f"<td>£{r['Total_Revenue']:,.2f}</td></tr>"
        for _, r in capability_df.iterrows()
    )

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Daily Food Truck Performance Report - {yesterday_date_str}</title>
    <style>
        :root {{
            --bg-color: #F8FAFC;
            --card-bg: #FFFFFF;
            --text-main: #0F172A;
            --text-sub: #64748B;
            --border-color: #E2E8F0;
            --primary: #3B82F6;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            margin: 0;
            padding: 2rem;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .header {{ margin-bottom: 2rem; }}
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }}
        .kpi-card {{
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 1.5rem;
        }}
        .kpi-title {{ font-size: 0.875rem; color: var(--text-sub); text-transform: uppercase; font-weight: 600; }}
        .kpi-value {{ font-size: 2rem; font-weight: 700; margin-top: 0.5rem; }}

        .tabs {{ display: flex; gap: 1rem; border-bottom: 2px solid var(--border-color); margin-bottom: 1.5rem; }}
        .tab-btn {{
            background: none; border: none; font-size: 1rem; font-weight: 600;
            padding: 0.75rem 1rem; color: var(--text-sub); cursor: pointer;
            border-bottom: 3px solid transparent; margin-bottom: -2px;
        }}
        .tab-btn.active {{ color: var(--primary); border-color: var(--primary); }}
        .tab-content {{ display: none; }}
        .tab-content.active {{ display: block; }}
        table {{
            width: 100%; border-collapse: collapse; background: var(--card-bg);
            border-radius: 8px; overflow: hidden; border: 1px solid var(--border-color);
            margin-top: 1.5rem;
        }}
        th, td {{ padding: 0.75rem 1rem; text-align: left; border-bottom: 1px solid var(--border-color); }}
        th {{ background-color: #F1F5F9; font-weight: 600; }}
        .grid-2col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }}
        .table-wrap {{ overflow-x: auto; -webkit-overflow-scrolling: touch; }}
        .table-wrap table {{ min-width: 480px; }}
        .grid-2col > div {{ min-width: 0; }}
        .plotly-graph-div {{ max-width: 100%; }}
        @media (max-width: 768px) {{
            .grid-2col {{ grid-template-columns: 1fr; }}
            body {{ padding: 1rem; }}
            h1 {{ font-size: 1.4rem; }}
            .kpi-grid {{ grid-template-columns: 1fr; gap: 0.75rem; }}
            .kpi-card {{ padding: 1rem; }}
            .kpi-value {{ font-size: 1.5rem; }}
            .tabs {{ overflow-x: auto; gap: 0.25rem; white-space: nowrap; }}
            .tab-btn {{ padding: 0.6rem 0.75rem; font-size: 0.875rem; flex: 0 0 auto; }}
            th, td {{ padding: 0.5rem 0.6rem; font-size: 0.8rem; }}
        }}
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>🚚 Daily Food Truck Performance Report</h1>
        <p>Performance Figures for <strong>{yesterday_date_str}</strong> • Direct S3 Export</p>
    </div>

    <div class="kpi-grid">
        <div class="kpi-card">
            <div class="kpi-title">Yesterday's Revenue</div>
            <div class="kpi-value">£{total_revenue:,.2f}</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">Total Orders</div>
            <div class="kpi-value">{total_orders:,}</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">Avg. Spend / Order</div>
            <div class="kpi-value">£{avg_spend:,.2f}</div>
        </div>
    </div>

    <div class="tabs">
        <button class="tab-btn active" onclick="switchTab('tab1', this)">📈 Hourly Performance</button>
        <button class="tab-btn" onclick="switchTab('tab2', this)">💰 Truck Breakdown</button>
        <button class="tab-btn" onclick="switchTab('tab3', this)">💳 Payment Methods</button>
    </div>

    <div id="tab1" class="tab-content active">
        {charts['chart_line']}
        <h3>Daily Performance Summary</h3>
        <div class="table-wrap">
        <table>
            <thead>
                <tr><th>Truck</th><th>Total Revenue</th><th>Order Count</th><th>Avg Order Value</th></tr>
            </thead>
            <tbody>
                {summary_rows}
            </tbody>
        </table>
        </div>
    </div>

    <div id="tab2" class="tab-content">
        {charts['chart_spend']}
    </div>

    <div id="tab3" class="tab-content">
        <div class="grid-2col">
            <div>{charts['chart_pie']}</div>
            <div>{charts['chart_truck_pay']}</div>
        </div>
        <h3>Truck Acceptance Capabilities</h3>
        <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th>Truck</th><th>Acceptance</th><th>Total Orders</th>
                    <th>Card Orders</th><th>Cash Orders</th><th>Card Share (%)</th><th>Total Revenue</th>
                </tr>
            </thead>
            <tbody>
                {capability_rows}
            </tbody>
        </table>
        </div>
    </div>
</div>

<script>
    function switchTab(tabId, btn) {{
        document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        
        const targetTab = document.getElementById(tabId);
        targetTab.classList.add('active');
        btn.classList.add('active');

        setTimeout(() => {{
            if (window.Plotly) {{
                targetTab.querySelectorAll('.plotly-graph-div').forEach(graph => {{
                    Plotly.Plots.resize(graph);
                }});
            }}
        }}, 50);
    }}
</script>
</body>
</html>
"""

    save_html_to_s3(html_content, S3_BUCKET_NAME, REPORT_S3_KEY)


# -----------------------------------------------------------------------------
# 5. Entrypoint
# -----------------------------------------------------------------------------


def lambda_handler(event, context):
    try:
        df = load_yesterday_data()

        if df.empty:
            print("No transactions found for yesterday.")
            return {
                "statusCode": 200,
                "body": "No transactions found for yesterday. Report generation skipped.",
            }

        generate_and_upload_report(df)
    except Exception as e:
        print(f"Error generating report: {e}")
        return {"statusCode": 500, "body": str(e)}

    # Generate pre-signed URL for S3 download
    presigned_url = s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": S3_BUCKET_NAME, "Key": REPORT_S3_KEY},
        ExpiresIn=86400,
    )

    return {
        "statusCode": 200,
        "report_url": presigned_url,
        "email_subject": "Your Report is Ready",
        "email_body_html": f"<html><body><h2>Your Report is Ready</h2><p><a href=\"{presigned_url}\">View Report</a></p></body></html>",
        "email_body_text": f"Your report is ready for download:\n\n{presigned_url}"
    }


if __name__ == "__main__":
    test_event = {}
    test_context = None
    res = lambda_handler(test_event, test_context)
    print("Local Test Execution Result:", res)
