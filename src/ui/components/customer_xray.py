from __future__ import annotations

import pandas as pd
import streamlit as st

from src.ui.formatting import format_brl


def render_customer_xray_card(
    selected_row: pd.Series,
    white_space_deals_df: pd.DataFrame,
    customer_label: str,
) -> None:
    """Renderiza Ficha Raio-X 360° da conta selecionada com ciclo, White Space e WhatsApp."""
    cust_id = str(selected_row.get("customer_id", ""))
    cust_name = str(selected_row.get("customer_name", "—"))
    uf = str(selected_row.get("state", "—"))
    rep_name = str(selected_row.get("sales_rep_name", "Sem RCA"))
    rfm_seg = str(selected_row.get("rfm_segment", "—"))
    risk_status = str(selected_row.get("risk_status", "—"))
    delay_ratio = float(selected_row.get("delay_ratio", 0.0) or 0.0)
    rev_risk = float(selected_row.get("annual_revenue_at_risk", 0.0) or 0.0)
    wa_url = str(selected_row.get("whatsapp_link", "") or "")

    delay_pct = min(100, max(6, int((delay_ratio / 2.5) * 100)))
    delay_color = (
        "var(--kyb-neg)"
        if delay_ratio >= 1.5
        else "var(--kyb-warn)"
        if delay_ratio >= 1.1
        else "var(--kyb-pos)"
    )

    offers_html = "<span style='color:var(--kyb-text-muted);'>Sem ofertas White Space mapeadas.</span>"
    if not white_space_deals_df.empty and cust_id and "customer_id" in white_space_deals_df.columns:
        cust_deals = white_space_deals_df[white_space_deals_df["customer_id"].astype(str) == cust_id].copy()
        if not cust_deals.empty:
            if "potential_revenue_brl" in cust_deals.columns:
                cust_deals = cust_deals.sort_values("potential_revenue_brl", ascending=False)
            top3 = cust_deals.head(3)
            items: list[str] = []
            fams = top3["recommended_family"].astype(str).tolist()
            revs = (
                top3["potential_revenue_brl"].astype(float).tolist()
                if "potential_revenue_brl" in top3.columns
                else [0.0] * len(top3)
            )
            lifts = (
                top3["apriori_lift"].astype(float).tolist()
                if "apriori_lift" in top3.columns
                else [1.0] * len(top3)
            )
            for fam, rev, lift in zip(fams, revs, lifts, strict=False):
                items.append(
                    f"<li><strong>{fam}</strong> · Potencial "
                    f"<strong>{format_brl(rev, compact=True)}</strong> "
                    f"(Lift {lift:.2f}x)</li>"
                )
            offers_html = (
                "<ul style='margin:0.2rem 0 0 1.1rem; padding:0; font-size:0.78rem;'>"
                + "".join(items)
                + "</ul>"
            )

    card_html = (
        "<div style='background:var(--kyb-card-bg); border:1px solid var(--kyb-border); "
        "border-left:4px solid var(--kyb-teal); border-radius:8px; padding:0.7rem 0.9rem; "
        "margin:0.45rem 0 0.55rem 0;'>"
        "<div style='display:flex; justify-content:space-between; align-items:center; "
        "flex-wrap:wrap; gap:0.5rem;'>"
        "<div>"
        f"<div style='font-size:0.7rem; text-transform:uppercase; font-weight:700; "
        f"color:var(--kyb-teal); letter-spacing:0.04em;'>Raio-X 360° · {customer_label}</div>"
        f"<div style='font-size:0.98rem; font-weight:700; color:var(--kyb-text);'>"
        f"{cust_name} ({uf})</div>"
        f"<div style='font-size:0.76rem; color:var(--kyb-text-muted);'>"
        f"RCA: <strong>{rep_name}</strong> · RFM: <strong>{rfm_seg}</strong> · "
        f"Status: <strong>{risk_status}</strong></div>"
        "</div>"
        "<div style='text-align:right;'>"
        "<div style='font-size:0.7rem; color:var(--kyb-text-muted); text-transform:uppercase;'>"
        "Receita Anual em Risco</div>"
        f"<div style='font-size:1.05rem; font-weight:700; color:{delay_color};'>"
        f"{format_brl(rev_risk, compact=True)}</div>"
        "</div>"
        "</div>"
        "<div style='margin-top:0.5rem;'>"
        "<div style='display:flex; justify-content:space-between; font-size:0.74rem; "
        "color:var(--kyb-text-muted); margin-bottom:0.2rem;'>"
        "<span>Atraso no Ciclo de Recompra</span>"
        f"<strong style='color:{delay_color};'>{delay_ratio:.2f}x do ciclo habitual</strong>"
        "</div>"
        "<div style='width:100%; height:7px; background:var(--kyb-border); border-radius:4px; "
        "overflow:hidden;'>"
        f"<div style='width:{delay_pct}%; height:100%; background:{delay_color};'></div>"
        "</div>"
        "</div>"
        "<div style='margin-top:0.55rem; padding-top:0.45rem; border-top:1px dashed var(--kyb-border);'>"
        "<div style='font-size:0.74rem; font-weight:700; color:var(--kyb-text);'>"
        "Top 3 Ofertas White Space (Cross-Sell):</div>"
        f"{offers_html}"
        "</div>"
        "</div>"
    )
    st.markdown(card_html, unsafe_allow_html=True)
    if wa_url:
        st.link_button(
            f"Acionar {cust_name[:28]} no WhatsApp",
            url=wa_url,
            use_container_width=False,
        )
