"""Food Truck Analytics Dashboard Application."""

from os import environ

import boto3
import pandas as pd
import streamlit as st
import awswrangler as wr
import plotly.express as px
from dotenv import load_dotenv

load_dotenv()

# Page configuration
st.set_page_config(
    page_title="Food Truck Analytics Dashboard",
    page_icon="🚚",
    layout="wide"
)

# -----------------------------------------------------------------------------
# Custom Styling for Sidebar & Visual Components
# -----------------------------------------------------------------------------
st.markdown("""
    <style>
        /* Custom styling for sidebar headers and badges */
        .sidebar-section {
            font-size: 1.1rem;
            font-weight: 600;
            margin-top: 1rem;
            margin-bottom: 0.5rem;
            color: #1E293B;
        }
        .filter-badge {
            background-color: #F1F5F9;
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 0.85rem;
            color: #475569;
            font-weight: 500;
        }
    </style>
""", unsafe_allow_html=True)

# Title & Stakeholder Overview
st.title("🚚 Food Truck Performance Dashboard")
st.caption(
    "A simple view of sales, truck performance, and spend patterns across Lichfield.")

# -----------------------------------------------------------------------------
# Data Loading & Merging with Caching
# -----------------------------------------------------------------------------


@st.cache_data(ttl=600)  # Caches data for 10 minutes to speed up reload times
def load_data():
    """Load and merge transaction, truck, and payment method data from Athena."""
    my_session = boto3.Session(region_name=environ.get("AWS_REGION"))
    database_name = environ.get("DATABASE_NAME")
    s3_output_location = environ.get("S3_OUTPUT_LOCATION")

    # Fetch Transactions
    query_transactions = """
    SELECT transaction_id, truck_id, payment_method_id, total, at
    FROM transactions
    ORDER BY transaction_id;
    """
    df_transactions = wr.athena.read_sql_query(
        sql=query_transactions,
        database=database_name,
        s3_output=s3_output_location,
        boto3_session=my_session
    )

    # Fetch Trucks Metadata
    query_trucks = """
    SELECT *
    FROM trucks;
    """
    df_trucks = wr.athena.read_sql_query(
        sql=query_trucks,
        database=database_name,
        s3_output=s3_output_location,
        boto3_session=my_session
    )

    # Fetch Payment Methods
    query_payment_methods = """
    SELECT *
    FROM payment_methods;
    """
    df_payment_methods = wr.athena.read_sql_query(
        sql=query_payment_methods,
        database=database_name,
        s3_output=s3_output_location,
        boto3_session=my_session
    )

    # Merge transactions with truck details and payment methods
    df = pd.merge(df_transactions, df_trucks, on="truck_id", how="inner")
    df = pd.merge(df, df_payment_methods, on="payment_method_id", how="left")

    # Data transformation
    df['at'] = pd.to_datetime(df['at'])
    df['total'] = df['total'] / 100.0  # Convert pennies to pounds

    # Extract clean truck name without ID suffix
    if 'name' in df.columns:
        df['truck_label'] = df['name']
    elif 'truck_name' in df.columns:
        df['truck_label'] = df['truck_name']
    else:
        df['truck_label'] = "Truck " + df['truck_id'].astype(str)

    # Clean payment method text column
    if 'payment_method' in df.columns:
        df['payment_method'] = df['payment_method'].str.title()
    else:
        df['payment_method'] = "Unknown"

    return df


with st.spinner("Loading transaction and truck data..."):
    try:
        df = load_data()
    except Exception as e:
        st.error(f"Error fetching data from Athena: {e}")
        st.stop()

# -----------------------------------------------------------------------------
# Enhanced Sidebar Filters
# -----------------------------------------------------------------------------
st.sidebar.title("🔍 Controls & Filters")
st.sidebar.markdown("Tailor performance analytics across dates and vendors.")

st.sidebar.divider()

# --- Section 1: Date Filter ---
st.sidebar.markdown("**📅 Date Range**")
min_date = df['at'].dt.date.min()
max_date = df['at'].dt.date.max()

selected_dates = st.sidebar.date_input(
    "Select Date Window",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date,
    label_visibility="collapsed"
)

# Handle single date vs range selection
if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
    start_date, end_date = selected_dates
else:
    start_date = end_date = selected_dates[0] if isinstance(
        selected_dates, tuple) else selected_dates

st.sidebar.divider()

# --- Section 2: Truck Multi-Select Filter ---
all_truck_labels = sorted(df['truck_label'].unique())

st.sidebar.markdown(
    "**🚚 Select Fleet Trucks**",
    unsafe_allow_html=True
)

# Default state initialization
if "selected_trucks" not in st.session_state:
    st.session_state["selected_trucks"] = all_truck_labels

# Multiselect input with custom key
selected_truck_labels = st.sidebar.multiselect(
    "Filter by Truck",
    options=all_truck_labels,
    default=st.session_state["selected_trucks"],
    key="truck_multiselect",
    placeholder="Choose trucks...",
    label_visibility="collapsed"
)

# Active selection summary indicator
active_count = len(selected_truck_labels)
if active_count == len(all_truck_labels):
    st.sidebar.caption("✅ Showing full fleet performance")
elif active_count > 0:
    st.sidebar.caption(
        f"🎯 Showing {active_count} of {len(all_truck_labels)} trucks")
else:
    st.sidebar.warning("⚠️ No trucks selected. Select at least one truck.")

# Filter Data
filtered_df = df[
    (df['at'].dt.date >= start_date) &
    (df['at'].dt.date <= end_date) &
    (df['truck_label'].isin(selected_truck_labels))
]

# Guard clause: handle empty selection safely
if filtered_df.empty:
    st.warning(
        "⚠️ No data available for the selected filters. Please select at least one truck or adjust the date range.")
    st.stop()

# -----------------------------------------------------------------------------
# Summary KPIs
# -----------------------------------------------------------------------------
total_revenue = filtered_df['total'].sum()
total_orders = len(filtered_df)
avg_spend = filtered_df['total'].mean() if total_orders > 0 else 0.0

col1, col2, col3 = st.columns(3)
col1.metric("Total Revenue", f"£{total_revenue:,.2f}")
col2.metric("Total Orders", f"{total_orders:,}")
col3.metric("Avg. Spend / Order", f"£{avg_spend:,.2f}")

st.divider()

# -----------------------------------------------------------------------------
# Main Visualizations
# -----------------------------------------------------------------------------
tab1, tab2, tab3 = st.tabs(
    ["📈 Truck Performance", "💰 Spend & Pricing", "💳 Payment Methods"])

# -----------------------------------------------------------------------------
# Global Color Mapping (Place before TAB 1 so colors stay consistent)
# -----------------------------------------------------------------------------
unique_trucks = sorted(df['truck_label'].unique())
plotly_colors = px.colors.qualitative.Plotly

truck_color_map = {
    truck: plotly_colors[i % len(plotly_colors)]
    for i, truck in enumerate(unique_trucks)
}

# -----------------------------------------------------------------------------
# TAB 1: Truck Performance
# -----------------------------------------------------------------------------
with tab1:
    st.subheader("Truck Performance Over Time")

    # 1. Metric Selector for Performance View
    col_perf_metric, _ = st.columns([2, 2])
    with col_perf_metric:
        perf_metric = st.radio(
            "Select Performance Metric:",
            options=["Revenue (£)", "Order Volume (Count)"],
            horizontal=True
        )

    # 2. Prepare aggregated data based on metric selection
    if perf_metric == "Revenue (£)":
        daily_truck_sales = filtered_df.groupby(
            [filtered_df['at'].dt.date.rename('date'), 'truck_label']
        )['total'].sum().reset_index()
        y_col = 'total'
        y_axis_label = 'Revenue (£)'
    else:
        daily_truck_sales = filtered_df.groupby(
            [filtered_df['at'].dt.date.rename('date'), 'truck_label']
        )['transaction_id'].count().reset_index()
        daily_truck_sales.rename(
            columns={'transaction_id': 'orders'}, inplace=True)
        y_col = 'orders'
        y_axis_label = 'Order Volume'

    # 3. Create Plotly Line Chart
    fig_line = px.line(
        daily_truck_sales,
        x='date',
        y=y_col,
        color='truck_label',
        color_discrete_map=truck_color_map,
        labels={'date': 'Date', y_col: y_axis_label, 'truck_label': 'Truck'}
    )

    fig_line.update_xaxes(fixedrange=True)
    fig_line.update_yaxes(fixedrange=True)

    st.plotly_chart(
        fig_line,
        width='stretch',
        config={'staticPlot': False,
                'scrollZoom': False, 'displayModeBar': False}
    )

    # 4. Summary Table Sorted by Active Metric (Clean Headers & No Index)
    st.subheader("Truck Performance Summary Table")

    truck_summary = filtered_df.groupby('truck_label').agg(
        **{
            'Total Revenue': ('total', 'sum'),
            'Order Count': ('total', 'count'),
            'Avg Order Value': ('total', 'mean')
        }
    ).reset_index()

    truck_summary.rename(columns={'truck_label': 'Truck'}, inplace=True)

    # Sort table by active metric using clean column names
    sort_by_column = 'Total Revenue' if perf_metric == "Revenue (£)" else 'Order Count'
    truck_summary = truck_summary.sort_values(
        by=sort_by_column, ascending=False)

    st.dataframe(
        truck_summary.style.format({
            'Total Revenue': '£{:,.2f}',
            'Order Count': '{:,}',
            'Avg Order Value': '£{:,.2f}'
        }),
        hide_index=True,  # Hides the pandas index column
        width='stretch'
    )

# -----------------------------------------------------------------------------
# TAB 2: Customer Spend & Pricing (Single Chart View with Formatted Labels)
# -----------------------------------------------------------------------------
with tab2:
    st.subheader("Customer Spend & Pricing Overview (£)")
    st.caption(
        "Analysis of customer payments and order values across fleet trucks."
    )

    # 1. Aggregate metrics
    truck_spend_metrics = filtered_df.groupby('truck_label')['total'].agg(
        Total_Paid=('sum'),
        Avg_Transaction_Value=('mean')
    ).reset_index()

    truck_spend_metrics.columns = [
        'Truck', 'Total Customer Spend (£)', 'Average Spend per Order (£)'
    ]

    # 2. View Selection & Sorting Controls
    col_metric, col_order = st.columns([2, 2])

    with col_metric:
        selected_metric = st.radio(
            "Select Metric to Display:",
            options=["Total Customer Spend (£)",
                     "Average Spend per Order (£)"],
            horizontal=True
        )

    with col_order:
        sort_order = st.radio(
            "Sort Direction:",
            options=["Descending (Highest First)", "Ascending (Lowest First)"],
            horizontal=True
        )

    is_ascending = sort_order.startswith("Ascending")

    # Apply sorting dynamically based on the selected metric
    truck_spend_metrics = truck_spend_metrics.sort_values(
        by=selected_metric, ascending=is_ascending
    )

    # Round metric values to 2 decimal places explicitly
    truck_spend_metrics[selected_metric] = truck_spend_metrics[selected_metric].round(
        2)

    st.divider()

    # 3. Dynamic Chart Rendering (Single Graph)
    if selected_metric == "Total Customer Spend (£)":
        chart_title = "##### Total Amount Paid by Customers"
        y_label = "Total Paid (£)"
    else:
        chart_title = "##### Average Customer Spend per Order"
        y_label = "Average Order Value (£)"

    st.markdown(chart_title)

    fig = px.bar(
        truck_spend_metrics,
        x='Truck',
        y=selected_metric,
        color='Truck',
        color_discrete_map=truck_color_map,
        labels={'Truck': 'Truck', selected_metric: y_label},
        text=selected_metric  # Pass formatted metric directly
    )
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    fig.update_traces(
        texttemplate='£%{text:,.2f}',  # Enforces exactly 2 decimal places
        textposition='outside'
    )
    fig.update_layout(showlegend=False)

    st.plotly_chart(
        fig,
        width='stretch',
        config={'staticPlot': False,
                'scrollZoom': False, 'displayModeBar': False}
    )

# TAB 3: Payment Methods & Acceptance
with tab3:
    st.subheader("Payment Methods Breakdown")
    st.caption(
        "Analysis of payment preferences across fleet trucks. Note: Trucks accepting card payments also accept cash.")

    pay_col1, pay_col2 = st.columns([1, 2])

    with pay_col1:
        pay_summary = filtered_df.groupby('payment_method')['total'].agg(
            ['sum', 'count']).reset_index()
        pay_summary.columns = ['Payment Method', 'Revenue (£)', 'Transactions']

        fig_pie = px.pie(
            pay_summary,
            names='Payment Method',
            values='Revenue (£)',
            title="Fleet Revenue by Payment Method",
            hole=0.4,
            color='Payment Method',
            color_discrete_map={'Card': '#3B82F6', 'Cash': '#10B981'}
        )
        fig_pie.update_traces(textinfo='percent+label')

        st.plotly_chart(
            fig_pie,
            width='stretch',
            config={'staticPlot': False,
                    'scrollZoom': False, 'displayModeBar': False}
        )

    with pay_col2:
        truck_pay = filtered_df.groupby(['truck_label', 'payment_method'])[
            'total'].sum().reset_index()

        fig_truck_pay = px.bar(
            truck_pay,
            x='truck_label',
            y='total',
            color='payment_method',
            barmode='stack',
            title="Revenue per Truck by Payment Method (£)",
            labels={'truck_label': 'Truck',
                    'total': 'Revenue (£)', 'payment_method': 'Payment Method'},
            color_discrete_map={'Card': '#3B82F6', 'Cash': '#10B981'}
        )

        fig_truck_pay.update_xaxes(fixedrange=True)
        fig_truck_pay.update_yaxes(fixedrange=True)

        st.plotly_chart(
            fig_truck_pay,
            width='stretch',
            config={'staticPlot': False,
                    'scrollZoom': False, 'displayModeBar': False}
        )

    st.subheader("Truck Acceptance Capabilities")

    capability_df = filtered_df.groupby('truck_label').agg(
        Total_Orders=('transaction_id', 'count'),
        Card_Orders=('payment_method', lambda x: (x == 'Card').sum()),
        Cash_Orders=('payment_method', lambda x: (x == 'Cash').sum()),
        Total_Revenue=('total', 'sum')
    ).reset_index()

    capability_df['Acceptance capability'] = capability_df['Card_Orders'].apply(
        lambda x: "💳 Accepts Card & Cash" if x > 0 else "💵 Cash Only"
    )

    capability_df['Card Share (%)'] = (
        capability_df['Card_Orders'] / capability_df['Total_Orders'] * 100).fillna(0)

    capability_df.rename(columns={'truck_label': 'Truck'}, inplace=True)
    capability_df = capability_df[['Truck', 'Acceptance capability', 'Total_Orders',
                                   'Card_Orders', 'Cash_Orders', 'Card Share (%)', 'Total_Revenue']]

    st.dataframe(
        capability_df.style.format({
            'Total_Revenue': '£{:,.2f}',
            'Total_Orders': '{:,}',
            'Card_Orders': '{:,}',
            'Cash_Orders': '{:,}',
            'Card Share (%)': '{:.1f}%'
        }),
        width='stretch'
    )
