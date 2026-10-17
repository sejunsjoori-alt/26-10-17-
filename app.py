import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io

# ---------------------------------------------------------------------------
# 1. 데이터 로드 및 전처리
# ---------------------------------------------------------------------------
@st.cache_data
def load_data(file_content: bytes, filename: str = "seoul_temperature.csv") -> pd.DataFrame:
    """
    업로드된 바이트 또는 로컬 파일 경로를 받아 DataFrame 으로 반환한다.
    - 날짜 컬럼 앞뒤의 탭·공백 제거
    - 연·월·일 분리
    """
    # 파일로 읽거나, 바이트면 StringIO 로 감싸서 읽는다
    if isinstance(file_content, bytes):
        df = pd.read_csv(io.BytesIO(file_content), encoding="utf-8-sig")
    else:
        df = pd.read_csv(file_content, encoding="utf-8-sig")

    # 날짜 컬럼: 탭·앞뒤 공백 제거 (원본 데이터에 "\t1907-10-01" 형태 있음)
    df["날짜"] = df["날짜"].astype(str).str.strip()

    # 날짜 파싱 → 연도·월 추출
    dt = pd.to_datetime(df["날짜"], errors="coerce")
    df["연도"] = dt.dt.year
    df["월"]   = dt.dt.month

    # 기온 컬럼을 숫자형으로 강제 변환 (빈 값·비정상 값 처리)
    for col in ["평균기온(℃)", "최저기온(℃)", "최고기온(℃)"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

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
    # 5년 중심 이동평균 (현재 연도 ±2년, 데이터가 1년 이상이면 계산)
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

    # --- CSV 파일 로드 (사이드바 업로더 또는 로컬 경로) ---
    st.sidebar.header("📁 데이터 파일")
    uploaded = st.sidebar.file_uploader(
        "CSV 파일 업로드 (선택)",
        type=["csv"],
        help="seoul_temperature.csv 를 이곳에 끌어다 놓으세요.",
    )

    if uploaded is not None:
        df_raw = load_data(uploaded.getvalue())
        st.sidebar.success(f"업로드된 파일: {uploaded.name} ({len(df_raw):,}행)")
    else:
        # 업로드가 없으면 기본 경로 파일 시도
        try:
            df_raw = load_data("seoul_temperature.csv")
            st.sidebar.info("기본 경로 'seoul_temperature.csv' 를 사용 중입니다.")
        except FileNotFoundError:
            st.sidebar.error(
                "CSV 파일을 찾을 수 없습니다.\n"
                "사이드바에 파일을 업로드하거나,\n"
                "코드에서 load_data('실제_파일_경로.csv') 로 경로를 수정하세요."
            )
            st.stop()

    # --- 연도별 집계 ---
    yearly = compute_yearly(df_raw)

    if yearly.empty:
        st.error("연도 데이터가 없습니다. CSV 의 '날짜' 컬럼 형식을 확인하세요.")
        st.stop()

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
    avg_val = selected["평균기온"].mean()
    max_val = selected["최고기온"].mean()
    min_val = selected["최저기온"].mean()

    # 방침: 평균기온이 있는 해만 센 '데이터일수' 기준도 함께 표시
    days_with_data = selected[selected["데이터일수"] > 0]["데이터일수"].sum()

    st.sidebar.metric("평균기온 (연평균)", f"{avg_val:.2f}℃")
    st.sidebar.metric("최고기온 (연평균)",  f"{max_val:.2f}℃")
    st.sidebar.metric("최저기온 (연평균)",  f"{min_val:.2f}℃")
    st.sidebar.caption(f"기온 값 있는 날 합계: {int(days_with_data):,}일")

    # --- Plotly 꺾은선 그래프 ---
    fig = make_subplots(specs=[[{"secondary_y": False}]])

    # 연도별 평균기온 (파란 선, 마커 있음)
    fig.add_trace(
        go.Scatter(
            x=selected["연도"],
            y=selected["평균기온"],
            mode="lines+markers",
            name="연도별 평균기온",
            line=dict(color="#1f77b4", width=2),
            marker=dict(size=5),
            hovertemplate="연도: %{x}<br>평균기온: %{y:.2f}℃<extra></extra>",
        ),
        secondary_y=False,
    )

    # 5년 이동평균 (주황 선, 점선)
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

    # --- 추가: 최저·최고기온 5년 이동평균도 별도 그래프로 표시 (옵션) ---
    with st.expander("📈 최저·최고기온 5년 이동평균 보기"):
        fig2 = make_subplots(specs=[[{"secondary_y": False}]])
        fig2.add_trace(
            go.Scatter(
                x=selected["연도"],
                y=selected["최저기온"],
                mode="lines",
                name="연도별 최저기온 평균",
                line=dict(color="#2ca02c", width=1.5),
                hovertemplate="연도: %{x}<br>최저기온: %{y:.2f}℃<extra></extra>",
            ),
            secondary_y=False,
        )
        fig2.add_trace(
            go.Scatter(
                x=selected["연도"],
                y=selected["최저기온_5년이동평균"],
                mode="lines",
                name="최저기온 5년 이동평균",
                line=dict(color="#2ca02c", width=3, dash="dot"),
                hovertemplate="연도: %{x}<br>최저 5년이동평균: %{y:.2f}℃<extra></extra>",
            ),
            secondary_y=False,
        )
        fig2.add_trace(
            go.Scatter(
                x=selected["연도"],
                y=selected["최고기온"],
                mode="lines",
                name="연도별 최고기온 평균",
                line=dict(color="#d62728", width=1.5),
                hovertemplate="연도: %{x}<br>최고기온: %{y:.2f}℃<extra></extra>",
            ),
            secondary_y=False,
        )
        fig2.add_trace(
            go.Scatter(
                x=selected["연도"],
                y=selected["최고기온_5년이동평균"],
                mode="lines",
                name="최고기온 5년 이동평균",
                line=dict(color="#d62728", width=3, dash="dot"),
                hovertemplate="연도: %{x}<br>최고 5년이동평균: %{y:.2f}℃<extra></extra>",
            ),
            secondary_y=False,
        )
        fig2.update_layout(
            title="연도별 최저·최고기온 및 5년 이동평균",
            xaxis_title="연도",
            yaxis_title="기온 (℃)",
            hovermode="x unified",
            legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
            margin=dict(l=40, r=20, t=50, b=40),
            height=400,
        )
        fig2.update_xaxes(range=[year_range[0] - 0.5, year_range[1] + 0.5], dtick=5)
        st.plotly_chart(fig2, use_container_width=True)

    # --- 원본 데이터 미리보기 (옵션) ---
    with st.expander("📁 원본 데이터 미리보기 (앞 20행)"):
        st.dataframe(
            df_raw[["날짜", "지점", "평균기온(℃)", "최저기온(℃)", "최고기온(℃)"]]
            .head(20)
            .style.format({
                "평균기온(℃)": "{:.1f}",
                "최저기온(℃)": "{:.1f}",
                "최고기온(℃)": "{:.1f}",
            }),
            use_container_width=True,
        )
        st.caption("※ 날짜 컬럼 앞뒤의 탭· 공백이 제거된 상태로 표시됩니다.")


if __name__ == "__main__":
    main()
