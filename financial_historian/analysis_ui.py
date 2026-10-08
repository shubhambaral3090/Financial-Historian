"""Educational browser views of the same calculation graph used in Excel."""
from __future__ import annotations

import html
from decimal import Decimal
import streamlit as st
import altair as alt

from .analysis import build_analysis, display_value, currency
from .export import _safe_source_url


def matrix(rows, periods, label):
    if not rows:
        st.info("No supported disclosures were retrieved for this schedule. Missing components are not estimated.")
        return
    headers = "".join(f"<th scope='col'>{html.escape(p)}</th>" for p in periods)
    body = []
    for row in rows:
        cells = []
        for p in periods:
            item = row.cells[p]
            title = item.reason or row.definition.formula
            text = html.escape(display_value(item))
            if item.fact and _safe_source_url(item.fact.source_url):
                text = f"<a href='{html.escape(item.fact.source_url,quote=True)}' target='_blank' rel='noopener noreferrer'>{text}</a>"
            cells.append(f"<td title='{html.escape(title,quote=True)}'>{text}</td>")
        body.append(f"<tr><th scope='row'>{html.escape(row.definition.label)}</th>{''.join(cells)}</tr>")
    st.html(f"<div class='statement-preview' tabindex='0' role='region' aria-label='{html.escape(label)}'><table><thead><tr><th scope='col'>Historical measure</th>{headers}</tr></thead><tbody>{''.join(body)}</tbody></table></div>")


def explain(row, periods):
    d = row.definition
    st.write(d.purpose)
    st.code(d.formula,language=None)
    st.caption(d.limitation)
    period = st.selectbox("Fiscal period for the worked example",periods,index=len(periods)-1,key="example_period")
    item = row.cells[period]
    st.markdown(f"**{d.label} · {period}: {display_value(item)}**")
    if item.value is None:
        st.info(item.reason)
    elif item.inputs:
        st.write("Calculation inputs: " + "; ".join(f"{a.label} ({a.period}) = {display_value(a)}" for a in item.inputs))
        st.caption("Displayed inputs are rounded for readability; calculations use unrounded source values.")
    if item.sources:
        records = [{"Reported input":f.label,"Period":f.end,"Start":f.start or "Instant",
                    "Unscaled source value":f.value,"Unit":f.unit,"Tag":f.tag,
                    "Filed":f.filed,"Accession":f.accession,
                    "Filing":f.source_url if _safe_source_url(f.source_url) else ""} for f in item.sources]
        st.dataframe(records,hide_index=True,width="stretch",column_config={"Filing":st.column_config.LinkColumn("Filing",display_text="Open SEC filing")})
    st.caption(d.reference)


def render_analytics(bundle, render_statements):
    analysis = build_analysis(bundle)
    overview,statements,schedules,metrics,sources = st.tabs(
        ["Overview","Statements","Schedules","Metrics & learning","Sources & checks"],
        key="research_tabs", on_change="rerun")
    with overview:
        st.subheader("Understand the history")
        st.write("Explore what the company reported, how the figures relate, and where the evidence comes from.")
        if not analysis.periods:
            st.info("No annual periods are available for historical analysis.")
        else:
            latest = analysis.periods[-1]
            overview_metrics = {r.definition.key:r for r in analysis.rows}
            for column,key in zip(st.columns(3),("revenue_growth","operating_margin","ocf_capex")):
                with column:
                    row = overview_metrics[key]
                    item = row.cells[latest]
                    st.metric(row.definition.label,display_value(item))
                    st.caption(latest)
                    if item.value is None:
                        st.caption("Unavailable — see Metrics & learning for the input explanation.")
            row = overview_metrics[st.selectbox("Historical chart",["operating_margin","revenue_growth","ocf_margin","asset_turnover","ebitda_margin","roic_proxy","diluted_shares_growth"],format_func=lambda k:overview_metrics[k].definition.label,key="historical_chart")]
            chart_data = []
            segment = 0
            previous = None
            from datetime import date
            for p in analysis.periods:
                item = row.cells[p]
                if item.value is None or previous and (date.fromisoformat(p)-date.fromisoformat(previous)).days>400:
                    segment += 1
                if item.value is not None:
                    chart_data.append({"Fiscal period":p,"Value":float(item.value)*(100 if item.unit=="%" else 1),"Sequence":str(segment)})
                previous = p
            if chart_data:
                try:
                    chart = alt.Chart(alt.Data(values=chart_data)).mark_line(point=True,color="#087d80").encode(
                        x=alt.X("Fiscal period:O",sort=analysis.periods),y=alt.Y("Value:Q",title=row.definition.unit),
                        detail="Sequence:N",tooltip=["Fiscal period:O","Value:Q"]).properties(height=220)
                    st.altair_chart(chart,width="stretch")
                except Exception:
                    st.info("The chart is unavailable. Exact historical values remain in the table below.")
            else:
                st.info("There are no compatible observations for this chart. Review the metric explanation.")
            matrix([row],analysis.periods,"Chart values")
        st.caption("Historical observations only. A change in a ratio does not establish its cause or its future direction.")
    with statements:
        render_statements(bundle)
    with schedules:
        st.subheader("Historical supporting schedules")
        group = st.selectbox("Choose a schedule",list(analysis.schedules),key="schedule_group")
        st.caption("Reported observations grouped for research. Missing movements remain unavailable; balances are not forced to reconcile.")
        matrix(analysis.schedules[group],analysis.periods,group)
        st.info("Debt maturity buckets are contractual disclosures at the historical reporting date. Segment dimensions may overlap and must not be added automatically.")
    with metrics:
        st.subheader("Learn as you analyse")
        paths = {
            "Understand profitability":({"Profitability","Returns","Return bridge","Growth","Earnings bridge"},"Start with reported revenue and margins, then inspect the asset base. EBITDA is a defined reconciliation, not cash flow; return contributions are arithmetic, not causes."),
            "Compare earnings with cash":({"Cash generation","Earnings and cash","Capital investment"},"Compare earnings and operating cash flow over several periods. Timing and working-capital movements can explain differences; inspect the cash-flow statement."),
            "Examine working capital":({"Working capital","Liquidity"},"Review receivables, inventory and trade payables together. Day measures use annual flows and average year-end balances, which can hide seasonality."),
            "Examine debt and liquidity":({"Debt","Liquidity"},"Inspect debt definitions, cash restrictions and interest expense before interpreting ratios. Reported maturities are not realized cash payments."),
            "Examine capital efficiency":({"Capital efficiency","Earnings bridge"},"ROIC here is explicitly a proxy: reported effective tax, debt plus consolidated equity less all cash, and two-point average capital. Inspect its assumptions before comparing companies."),
            "Understand per-share results":({"Shareholder analysis"},"Compare earnings, EPS and weighted share counts. Same-filing comparisons limit split-vintage mismatches; the growth gap does not prove buyback causation. Cash dividends differ from declared dividends."),
            "Explore business drivers":({"Business drivers"},"Compare like-defined product, geographic and segment observations. Members can overlap. Operating KPIs require reviewed issuer-specific mappings; subscriptions are not unique customers."),
        }
        path = st.selectbox("Guided analysis",list(paths),key="learning_path")
        groups,guidance = paths[path]
        st.write(guidance)
        chosen = [r for r in analysis.rows if r.definition.group in groups]
        matrix(chosen,analysis.periods,"Historical metrics")
        if chosen and analysis.periods:
            by_key = {r.definition.key:r for r in chosen}
            key = st.selectbox("Explain a metric",list(by_key),format_func=lambda k:by_key[k].definition.label,key="explain_metric")
            explain(by_key[key],analysis.periods)
        with st.expander("Common-size statements"):
            st.caption("Income statement amounts / selected revenue; balance-sheet amounts / assets. Overlapping totals and components are not additive.")
            matrix(analysis.common_size,analysis.periods,"Common-size statements")
    with sources:
        st.subheader("Evidence and validation")
        st.caption("Passed arithmetic checks are not a financial audit. A check with missing evidence is marked insufficient information.")
        st.dataframe([{"Period":c.period,"Check":c.label,"Status":c.status,
                       "Difference":float(c.difference) if c.difference is not None else None,
                       "Tolerance":float(c.tolerance) if c.tolerance is not None else None,
                       "Explanation":c.reason} for c in analysis.checks],hide_index=True,width="stretch")
        for note in analysis.notes:
            st.write(note)
        if bundle.coverage:
            st.dataframe([{"Period":c.report_date,"Status":c.status,"Explanation":c.detail,
                           "Filing":c.source_url if _safe_source_url(c.source_url) else ""} for c in bundle.coverage],
                         hide_index=True,width="stretch",column_config={"Filing":st.column_config.LinkColumn("Filing",display_text="Open filing")})
        with st.expander("All retrieval and accounting notes"):
            for note in bundle.warnings:
                st.write(note)
