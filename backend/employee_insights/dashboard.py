import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
import streamlit as st
import pandas as pd
import plotly.express as px

from backend.employee_insights.analysis.frequency_analyzer import FrequencyAnalyzer
from backend.employee_insights.database.db_manager import DatabaseManager
from backend.employee_insights.preprocessing.employee_identifier import EmployeeIdentifier


st.set_page_config(
    page_title="Employee Performance Insights",
    page_icon="📊",
    layout="wide"
)


@st.cache_resource
def get_analyzer():
    return FrequencyAnalyzer()


@st.cache_resource
def get_database():
    return DatabaseManager()


def load_data():

    analyzer = get_analyzer()
    database = get_database()

    employee_data = analyzer.analyze()
    feedback_records = database.get_all_feedback()
    monthly_data = analyzer.monthly_analysis()

    return employee_data, feedback_records, monthly_data


st.title("Employee Performance Insights")
st.caption("Email-based employee feedback analysis")

st.sidebar.title("Navigation")

page = st.sidebar.radio(
    "Select Section",
    [
        "Dashboard",
        "Employee Overview",
        "Employee Comparison",
        "Feedback History"
    ]
)

st.sidebar.divider()

st.sidebar.subheader("Email Processing")

max_emails = st.sidebar.number_input(
    "Maximum emails to collect",
    min_value=1,
    max_value=500,
    value=100
)

if st.sidebar.button("Process New Emails", use_container_width=True):

    from backend.employee_insights.email_collector.email_processor import EmailProcessor

    try:
        with st.spinner("Collecting and analysing emails..."):

            processor = EmailProcessor()

            result = processor.process_emails(
                query="in:anywhere -in:spam -in:trash",
                max_results=int(max_emails)
            )

        st.sidebar.success(
            f"Processed {result['emails_collected']} emails. "
            f"Saved {result['feedback_saved']} new feedback records."
        )

        st.cache_resource.clear()
        st.rerun()

    except Exception as error:

        st.sidebar.error(f"Email processing failed: {error}")


employee_data, feedback_records, monthly_data = load_data()

df_employees = pd.DataFrame(employee_data)
df_feedback = pd.DataFrame(feedback_records)


# DASHBOARD

if page == "Dashboard":

    st.header("Overview")

    total_feedback = len(feedback_records)

    positive = sum(
        1 for record in feedback_records
        if record["sentiment"] == "POSITIVE"
    )

    negative = sum(
        1 for record in feedback_records
        if record["sentiment"] == "NEGATIVE"
    )

    neutral = sum(
        1 for record in feedback_records
        if record["sentiment"] == "NEUTRAL"
    )

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total Feedback", total_feedback)
    col2.metric("Positive", positive)
    col3.metric("Negative", negative)
    col4.metric("Neutral", neutral)

    st.divider()

    left, right = st.columns(2)

    with left:

        st.subheader("Employee-wise Feedback")

        chart_data = df_employees.melt(
            id_vars=["employee_name"],
            value_vars=["positive", "negative", "neutral"],
            var_name="Sentiment",
            value_name="Count"
        )

        fig = px.bar(
            chart_data,
            x="employee_name",
            y="Count",
            color="Sentiment",
            barmode="group",
            title="Feedback Distribution by Employee"
        )

        st.plotly_chart(fig, use_container_width=True)

    with right:

        st.subheader("Overall Sentiment Distribution")

        sentiment_df = pd.DataFrame({
            "Sentiment": ["Positive", "Negative", "Neutral"],
            "Count": [positive, negative, neutral]
        })

        fig = px.pie(
            sentiment_df,
            names="Sentiment",
            values="Count",
            hole=0.45,
            title="Sentiment Breakdown"
        )

        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    st.subheader("Monthly Feedback Trends")

    if monthly_data:

        monthly_df = pd.DataFrame.from_dict(
            monthly_data,
            orient="index"
        )

        monthly_df.index.name = "Month"
        monthly_df = monthly_df.reset_index()

        monthly_chart_data = monthly_df.melt(
            id_vars=["Month"],
            value_vars=["positive", "negative", "neutral"],
            var_name="Sentiment",
            value_name="Count"
        )

        fig = px.bar(
            monthly_chart_data,
            x="Month",
            y="Count",
            color="Sentiment",
            barmode="stack",
            title="Monthly Sentiment Trends"
        )

        st.plotly_chart(fig, use_container_width=True)

    else:

        st.info("No monthly feedback data available.")


# EMPLOYEE OVERVIEW

elif page == "Employee Overview":

    st.header("Employee Overview")

    st.dataframe(
        df_employees[
            [
                "employee_id",
                "employee_name",
                "total_feedback",
                "positive",
                "negative",
                "neutral",
                "positive_percentage"
            ]
        ],
        use_container_width=True,
        hide_index=True
    )

    st.caption(
        "Positive percentage is calculated using positive and negative "
        "feedback only. Neutral mentions are excluded."
    )

    selected_employee = st.selectbox(
        "Select Employee",
        df_employees["employee_name"].tolist()
    )

    employee = next(
        item for item in employee_data
        if item["employee_name"] == selected_employee
    )

    st.divider()

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total Feedback", employee["total_feedback"])
    col2.metric("Positive", employee["positive"])
    col3.metric("Negative", employee["negative"])
    col4.metric("Neutral", employee["neutral"])

    employee_records = [
        record for record in feedback_records
        if record["employee_id"] == employee["employee_id"]
    ]

    st.subheader("Employee Feedback")

    if employee_records:

        for record in employee_records:

            with st.container(border=True):

                st.write(record["feedback"])

                st.caption(
                    f"Sentiment: {record['sentiment']} | "
                    f"Confidence: {record['confidence']} | "
                    f"Date: {record['email_date']}"
                )

    else:

        st.info("No feedback records found for this employee.")


# EMPLOYEE COMPARISON

elif page == "Employee Comparison":

    st.header("Employee Comparison")

    comparison_df = df_employees[
        [
            "employee_name",
            "positive",
            "negative",
            "neutral",
            "total_feedback"
        ]
    ]

    fig = px.bar(
        comparison_df,
        x="employee_name",
        y=["positive", "negative", "neutral"],
        barmode="group",
        title="Sentiment Comparison Across Employees"
    )

    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Feedback Volume Comparison")

    fig = px.bar(
        comparison_df,
        x="employee_name",
        y="total_feedback",
        title="Total Feedback Received"
    )

    st.plotly_chart(fig, use_container_width=True)


# FEEDBACK HISTORY

elif page == "Feedback History":

    st.header("Feedback History")

    if df_feedback.empty:

        st.info("No feedback records available.")

    else:

        employees = ["All"] + sorted(
            df_feedback["employee_name"].unique().tolist()
        )

        selected_employee = st.selectbox(
            "Filter by Employee",
            employees
        )

        sentiments = ["All", "POSITIVE", "NEGATIVE", "NEUTRAL"]

        selected_sentiment = st.selectbox(
            "Filter by Sentiment",
            sentiments
        )

        filtered_df = df_feedback.copy()

        if selected_employee != "All":

            filtered_df = filtered_df[
                filtered_df["employee_name"] == selected_employee
            ]

        if selected_sentiment != "All":

            filtered_df = filtered_df[
                filtered_df["sentiment"] == selected_sentiment
            ]

        display_columns = [
            "employee_name",
            "feedback",
            "sentiment",
            "confidence",
            "email_date"
        ]

        st.dataframe(
            filtered_df[display_columns],
            use_container_width=True,
            hide_index=True
        )

        st.caption(
            f"Showing {len(filtered_df)} feedback records."
        )