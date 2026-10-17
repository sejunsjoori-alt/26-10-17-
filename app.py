import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ---------------------------------------------------------------------------
# 1. 데이터 로드 및 전처리
# ---------------------------------------------------------------------------
@st.cache_data
def load_data(filepath: str = "seoul_temperature.csv") -> pd.DataFrame:
    """CSV를 읽고 날짜 전처리(탭·앞뒤 공백 제거) 후 반환한다."""
    df = pd.read_csv(
        filepath,
        encoding="utf-8",
        dtype={"지점": str},
    )
    # 날짜 컬럼 앞/뒤 공백 및 탭 문자 제거
    df["날짜"] = df["날짜"].astype(str).str.strip()
    # 연·월·일 분리
    df["연도"] = pd.to_datetime(df["날짜"], errors="coerce").dt.year
    df["월"]   = pd.to_datetime(df["날짜"], errors="coerce").dt.month
    return df


# ---------------------------------------------------------------------------
# 2. 연도별 집계 + 5년 이동평균
# ---------------------------------------------------------------------------
def compute_yearly(df: pd.DataFrame) -> pd.DataFrame:
    """연도별 평균·최저·최고기온을 계산하고 5년 이동평균을 덧붙인다."""
    yearly = (
        df.dropna(subset=["연도"])
        .groupby("연도")
        .agg(
            평균기온=("평균기온(℃)", "mean"),
            최저기온=("최저기온(℃)", "mean"),
            최고기온=("최고기온(℃)", "mean"),
            데이터일수=("평균기온(℃)", "count"),
        )
        .reset_index()
    )
    # 5년 이동평균 (중심 이동평균: 현재 연도 ± 2년)
    for col in ["평균기온", "최저기온", "최고기온"]:
        yearly[f"{col}_5년이동평균"] = (
            yearly[col]
            .rolling(window=5, center=True, min_periods=1)
            .mean()
        )
    return yearly


# ---------------------------------------------------------------------------
# 3. Streamlit UI
# ---------------------------------------------------------------------------
def main() -> None:
    st.set_page_config(page_title="서울 기온 대시보드", layout="wide")
    st.title("🌡️ 서울 연도별 기온 분석")

    # --- 데이터 로드 ---
    df_raw = load_data("seoul_temperature.csv")
    yearly = compute_yearly(df_raw)

    if yearly.empty:
        st.error("데이터가 비어 있습니다. CSV 파일 경로와 인코딩을 확인하세요.")
        return

    min_year = int(yearly["연도"].min())
    max_year = int(yearly["연도"].max())

    # --- 사이드바: 연도 범위 슬라이더 ---
    st.sidebar.header("📅 기간 설정")
    year_range = st.sidebar.slider(
        "연도 범위",
        min_value=min_year,
        max_value=max_year,
        value=(min_year, max_year),
        step=1,
    )
    selected = yearly[
        (yearly["연도"] >= year_range[0]) & (yearly["연도"] <= year_range[1])
    ].copy()

    # --- 선택 구간 통계 ---
    st.sidebar.subheader("📊 선택 구간 요약")
    avg_val   = selected["평균기온"].mean()
    max_val   = selected["최고기온"].mean()
    min_val   = selected["최저기온"].mean()
    st.sidebar.metric("평균기온 (연평균)", f"{avg_val:.2f}℃")
    st.sidebar.metric("최고기온 (연평균)",  f"{max_val:.2f}℃")
    st.sidebar.metric("최저기온 (연평균)",  f"{min_val:.2f}℃")

    # --- Plotly 꺾은선 그래프 ---
    fig = make_subplots(specs=[[{"secondary_y": False}]])

    # 연도별 평균기온 (파란 선)
    fig.add_trace(
        go.Scatter(
            x=selected["연도"],
            y=selected["평균기온"],
            mode="lines+markers",
            name="연도별 평균기온",
            line=dict(color="#1f77b4", width=2),
            marker=dict(size=4),
            hovertemplate="연도: %{x}<br>평균기온: %{y:.2f}℃<extra></extra>",
        ),
        secondary_y=False,
    )

    # 5년 이동평균 (주황 선)
    fig.add_trace(
        go.Scatter(
            x=selected["연도"],
            y=selected["평균기온_5년이동평균"],
            mode="lines",
            name="5년 이동평균",
            line=dict(color="#ff7f0e", width=3, dash="dot"),
            hovertemplate="연도: %{x}<br>5년이동평균: %{y:.2f}℃<extra></extra>",
        ),
        secondary_y=False,
    )

    fig.update_layout(
        title="연도별 평균기온 및 5년 이동평균",
        xaxis_title="연도",
        yaxis_title="기온 (℃)",
        hovermode="x unified",
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
        margin=dict(l=40, r=20, t=50, b=40),
        height=480,
    )
    fig.update_xaxes(
        range=[year_range[0] - 0.5, year_range[1] + 0.5],
        dtick=5,
    )

    st.plotly_chart(fig, use_container_width=True)

    # --- 원본 데이터 미리보기 (옵션) ---
    with st.expander("📁 원본 데이터 미리보기"):
        st.dataframe(
            df_raw[["날짜", "지점", "평균기온(℃)", "최저기온(℃)", "최고기온(℃)"]]
            .head(20)
            .style.format({"평균기온(℃)": "{:.1f}", "최저기온(℃)": "{:.1f}", "최고기온(℃)": "{:.1f}"}),
            use_container_width=True,
        )
        st.caption("※ 날짜 컬럼 앞/뒤의 탭· 공백이 제거된 상태로 표시됩니다.")


if __name__ == "__main__":
    main()
