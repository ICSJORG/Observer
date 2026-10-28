"""Streamlit dashboard:  streamlit run app.py"""
import json

import folium
import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium

import config
import db

st.set_page_config(
    page_title="ICSJ - Observer",
    page_icon="assets/logoclean.png",
    layout="wide"
)
SOURCE_PRIORITY = {"CPJ": 0, "UNESCO": 1}   # which record survives when a killing is listed by both


@st.cache_data(ttl=300)
def load():
    return db.load_all()


@st.cache_data(show_spinner=False)
def world_geojson():
    r = requests.get(config.WORLD_GEOJSON_URL, timeout=30)
    r.raise_for_status()
    return r.json()


def merge_duplicates(f):
    """Collapse the same killing listed by several sources (same name + year) into one row."""
    keyed = f[f.match_key.notna()].copy()
    if keyed.empty:
        return f, 0
    keyed["_p"] = keyed.source.map(SOURCE_PRIORITY).fillna(9)
    keyed = keyed.sort_values("_p")
    srcs = keyed.groupby("match_key").source.agg(lambda s: " + ".join(sorted(set(s))))
    fill = keyed.groupby("match_key")[["gender", "media_type"]].first()   # coalesce what only one source has
    top = keyed.drop_duplicates("match_key").copy()
    for c in fill:
        top[c] = top[c].fillna(top.match_key.map(fill[c]))
    top["source"] = top.match_key.map(srcs)
    merged = pd.concat([f[f.match_key.isna()], top.drop(columns="_p")], ignore_index=True)
    return merged, len(f) - len(merged)


df = load()
st.title("Press Freedom Incident Monitor")
if df.empty:
    st.info("The database is empty. Run `python ingest_all.py` (see README), then refresh.")
    st.stop()

sb = st.sidebar
sb.header("Filters")
y0, y1 = int(df.year.min()), int(df.year.max())
years = sb.slider("Years", y0, y1, (y0, y1)) if y0 < y1 else (y0, y1)
countries = sb.multiselect("Country", sorted(df.country.dropna().unique()))
types = sb.multiselect("Attack type", sorted(df.type.dropna().unique()))
sources = sb.multiselect("Source", sorted(df.source.unique()))
kinds = sb.multiselect("Record kind", sorted(df.kind.unique()),
                       help="'incident' = a recorded event; 'article' = a news item from an RSS feed")
query = sb.text_input("Search text", placeholder="e.g. spyware, Belgrade, photographer, victim name")
with sb.expander("Killed-journalist details"):
    detail_filters = {
        "role": st.multiselect("Role (CPJ)", sorted(df.role.dropna().unique())),
        "circumstance": st.multiselect("Circumstance (CPJ type of death)", sorted(df.circumstance.dropna().unique())),
        "perpetrator": st.multiselect("Suspected source of fire (CPJ)", sorted(df.perpetrator.dropna().unique())),
        "case_status": st.multiselect("Impunity / enquiry status (source-specific)", sorted(df.case_status.dropna().unique())),
        "media_type": st.multiselect("Media type (UNESCO)", sorted(df.media_type.dropna().unique())),
        "gender": st.multiselect("Gender (UNESCO)", sorted(df.gender.dropna().unique())),
    }
merge = sb.checkbox("Count each killing once across sources", value=True,
                    help="CPJ and UNESCO list many of the same killings. Records with the same normalised "
                         "name and year are merged into one row (CPJ's fields win). Untick to see every source row.")

f = df[df.year.between(*years)]
for col, sel in (("country", countries), ("type", types), ("source", sources), ("kind", kinds), *detail_filters.items()):
    if sel:
        f = f[f[col].isin(sel)]
if query:
    blob = (f.title.fillna("") + " " + f.summary.fillna("") + " " + f.country.fillna("") + " "
            + f.victim.fillna("") + " " + f.organization.fillna(""))
    f = f[blob.str.contains(query, case=False, regex=False)]
merged_n = 0
if merge:
    f, merged_n = merge_duplicates(f)

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Records", f"{len(f):,}")
c2.metric("Countries", f.country.nunique())
c3.metric("Sources", f.source.str.split(" \\+ ").explode().nunique())
c4.metric("Not on map", int(f.iso3.isna().sum()),
          help="No single ISO country code (e.g. CPJ's combined 'Israel and the Occupied Palestinian Territory', "
               "'Yugoslavia', RSF regional feeds) or no country detected. Still counted everywhere else.")
c5.metric("Duplicates merged", merged_n)

tab_trend, tab_kill, tab_map, tab_table, tab_src = st.tabs(
    ["Trends", "Killed journalists", "Map", "Records", "Sources & method"])

with tab_trend:
    a, b = st.columns(2)
    by_year = f.groupby(["year", "type"]).size().reset_index(name="count")
    a.plotly_chart(px.bar(by_year, x="year", y="count", color="type", title="Records per year, by type"),
                   width="stretch")
    monthly = f.groupby("month").size().reset_index(name="count").sort_values("month")
    b.plotly_chart(px.line(monthly, x="month", y="count", title="Records per month"), width="stretch")
    a, b = st.columns(2)
    top = f.country.value_counts().head(20).rename_axis("country").reset_index(name="count")
    a.plotly_chart(px.bar(top, x="count", y="country", orientation="h", title="Top 20 countries")
                   .update_yaxes(autorange="reversed"), width="stretch")
    heat = f[f.country.isin(top.country.head(15))].groupby(["country", "year"]).size().reset_index(name="count")
    if not heat.empty:
        b.plotly_chart(px.density_heatmap(heat, x="year", y="country", z="count", histfunc="sum",
                                          title="Country × year (top 15)"), width="stretch")
    st.caption("RSS 'article' rows are news items, not verified incidents: filter Record kind = incident "
               "for counts you intend to cite.")

with tab_kill:
    k = f[(f.type == "Killing") & (f.kind == "incident")]
    if k.empty:
        st.info("No killing records match the current filters.")
    else:
        a, b = st.columns(2)
        a.plotly_chart(px.bar(k.groupby(["year", "source"]).size().reset_index(name="count"), x="year", y="count",
                              color="source", title="Killings per year"), width="stretch")
        circ = k.dropna(subset=["circumstance"]).groupby(["year", "circumstance"]).size().reset_index(name="count")
        if not circ.empty:
            b.plotly_chart(px.bar(circ, x="year", y="count", color="circumstance",
                                  title="Circumstances (CPJ classification)"), width="stretch")
        a, b = st.columns(2)
        cs = k.assign(case_status=k.case_status.fillna("Not recorded")).groupby("case_status").size() \
              .reset_index(name="count").sort_values("count")
        a.plotly_chart(px.bar(cs, x="count", y="case_status", orientation="h",
                              title="Impunity (CPJ) / enquiry status (UNESCO), as published"),
                       width="stretch")
        perp = k.perpetrator.dropna().value_counts().head(10).rename_axis("perpetrator").reset_index(name="count")
        if not perp.empty:
            b.plotly_chart(px.bar(perp, x="count", y="perpetrator", orientation="h",
                                  title="Suspected source of fire (CPJ)").update_yaxes(autorange="reversed"),
                           width="stretch")
        a, b = st.columns(2)
        for col, title, box in (("media_type", "Media type (UNESCO)", a), ("role", "Journalist vs media worker (CPJ)", b)):
            s = k[col].dropna().value_counts().rename_axis(col).reset_index(name="count")
            if not s.empty:
                box.plotly_chart(px.pie(s, names=col, values="count", title=title, hole=0.4), width="stretch")
        flags = k.details.dropna().map(json.loads)
        cpj_n = int((k.source.str.contains("CPJ")).sum())
        if cpj_n and len(flags):
            fl = pd.Series({lbl: sum(1 for d in flags if d.get(key)) for lbl, key in
                            (("Taken captive", "taken_captive"), ("Threatened", "threatened"), ("Tortured", "tortured"))})
            st.markdown("**Before being killed (CPJ flags, share of CPJ records shown):** " +
                        ", ".join(f"{i.lower()} {v / cpj_n:.0%}" for i, v in fl.items()))
        st.caption("Impunity (CPJ) and enquiry status (UNESCO) use different vocabularies and are shown unharmonised; "
                   "CPJ leaves impunity blank for many non-murder cases.")

with tab_map:
    counts = f.dropna(subset=["iso3"]).groupby("iso3").size().reset_index(name="count")
    m = folium.Map(location=[30, 15], zoom_start=2, tiles="OpenStreetMap")
    if not counts.empty:
        try:
            folium.Choropleth(geo_data=world_geojson(), data=counts, columns=["iso3", "count"],
                              key_on="feature.id", fill_color="YlOrRd", nan_fill_opacity=0,
                              legend_name="Records").add_to(m)
        except Exception as exc:
            st.warning(f"Could not load country polygons: {exc}")
    pts = f.dropna(subset=["lat", "lon"]).head(3000)
    cluster = MarkerCluster(name="Geolocated records").add_to(m)
    for r in pts.itertuples():
        folium.Marker([r.lat, r.lon], popup=folium.Popup(
            f"<b>{r.title}</b><br>{r.event_date:%Y-%m-%d} · {r.type}<br>{r.source}"
            + (f"<br><a href='{r.url}' target='_blank'>source</a>" if r.url else ""), max_width=300)
        ).add_to(cluster)
    st_folium(m, height=560, use_container_width=True, returned_objects=[])
    st.caption(f"Colour = records per country. {len(pts):,} geolocated markers (only some sources give event "
               "coordinates; CPJ and UNESCO killings are country-level only). Hong Kong and Kosovo have no "
               "separate polygon in the base map.")

with tab_table:
    cols = ["event_date", "country", "type", "title", "victim", "role", "circumstance", "perpetrator",
            "case_status", "gender", "media_type", "source", "kind", "url", "summary"]
    show = f.sort_values("event_date", ascending=False)[cols]
    st.dataframe(show, width="stretch", hide_index=True,
                 column_config={"url": st.column_config.LinkColumn("url")})
    st.download_button("Download filtered CSV", show.to_csv(index=False).encode("utf-8"),
                       "incidents_filtered.csv", "text/csv")

with tab_src:
    st.dataframe(df.groupby(["source", "kind"]).agg(records=("id", "count"), first=("event_date", "min"),
                                                    last=("event_date", "max"), last_fetched=("fetched_at", "max")))
    both = df[df.match_key.notna()].groupby("match_key").source.agg(lambda s: set(s))
    st.write(f"Killings listed by both CPJ and UNESCO (exact normalised name + year): "
             f"**{int(both.map(lambda s: {'CPJ', 'UNESCO'} <= s).sum()):,}**")
    st.markdown("""
**Read before citing.** Attack *type* and *country* for RSS items are keyword heuristics (RSF feeds take
their country from the feed). CPJ/UNESCO rows come from structured datasets. RSS items are news articles,
not verified incident records, and a feed only exposes its latest items. Cross-source merging matches
exact normalised names plus year, so it is conservative: spelling variants will not merge, and
single-name or "Unidentified" victims are never merged. Sources define scope differently (e.g. CPJ's
"confirmed"/"suspected work-related" vs UNESCO's Director-General condemnations), so compare counts across
sources with care. Always cite the originating organisation and check its licence.
""")
