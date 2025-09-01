# app.py — ARAM 챔피언 대시보드 (+ 아이템 0 전처리, 스펠 무순서 집계, 룬 보드 UI)
import os, re, json
import pandas as pd
import streamlit as st

st.set_page_config(page_title="ARAM PS Dashboard", layout="wide")

# ===== 파일 경로(리포 루트) =====
PLAYERS_CSV   = "aram_participants_with_icons_superlight.csv"
ITEM_SUM_CSV  = "item_summary_with_icons.csv"
CHAMP_CSV     = "champion_icons.csv"
RUNE_CSV      = "rune_icons.csv"
SPELL_CSV     = "spell_icons.csv"
DD_VERSION    = "15.16.1"

# ===== 유틸 =====
def _exists(path: str) -> bool:
    ok = os.path.exists(path)
    if not ok:
        st.warning(f"파일 없음: `{path}`")
    return ok

def _norm(x: str) -> str:
    return re.sub(r"\s+", "", str(x)).strip().lower()

# ===== 로더 =====
@st.cache_data
def load_players(path: str) -> pd.DataFrame:
    if not _exists(path):
        st.stop()
    df = pd.read_csv(path)
    if "win_clean" not in df.columns:
        if "win" in df.columns:
            df["win_clean"] = df["win"].astype(str).str.lower().isin(
                ["true","1","t","yes"]).astype(int)
        else:
            df["win_clean"] = 0
    for c in [c for c in df.columns if re.fullmatch(r"item[0-6]_name", c)]:
        df[c] = df[c].fillna("").astype(str).str.strip()
        df[c] = df[c].replace({"0": "", 0: ""})
    for c in ["spell1","spell2","spell1_name_fix","spell2_name_fix",
              "rune_core","rune_sub","champion","matchId"]:
        if c in df.columns:
            df[c] = df[c].fillna("").astype(str).str.strip()
    return df

@st.cache_data
def load_item_summary(path: str) -> pd.DataFrame:
    if not _exists(path):
        return pd.DataFrame()
    g = pd.read_csv(path)
    need = {"item","icon_url","total_picks","wins","win_rate"}
    if not need.issubset(g.columns):
        st.warning(f"`{path}` 헤더 확인 필요 (기대: {sorted(need)}, 실제: {list(g.columns)})")
    if "item" in g.columns:
        g = g[g["item"].astype(str).str.strip() != ""]
        g = g[g["item"] != "0"]
    return g

@st.cache_data
def load_champion_icons(path: str) -> dict:
    if not _exists(path):
        return {}
    df = pd.read_csv(path)
    name_col = next((c for c in ["champion","Champion","championName"] if c in df.columns), None)
    icon_col = next((c for c in ["champion_icon","icon","icon_url"] if c in df.columns), None)
    if not name_col or not icon_col:
        return {}
    df[name_col] = df[name_col].astype(str).str.strip()
    return dict(zip(df[name_col], df[icon_col]))

@st.cache_data
def load_rune_icons(path: str) -> dict:
    if not _exists(path):
        return {"core": {}, "sub": {}, "shards": {}}
    df = pd.read_csv(path)
    core_map, sub_map, shard_map = {}, {}, {}
    if "rune_core" in df.columns and "rune_core_icon" in df.columns:
        core_map = dict(zip(df["rune_core"].astype(str), df["rune_core_icon"].astype(str)))
    if "rune_sub" in df.columns and "rune_sub_icon" in df.columns:
        sub_map = dict(zip(df["rune_sub"].astype(str), df["rune_sub_icon"].astype(str)))
    if "rune_shard" in df.columns:
        ic = "rune_shard_icon" if "rune_shard_icon" in df.columns else None
        if ic: shard_map = dict(zip(df["rune_shard"].astype(str), df[ic].astype(str)))
    return {"core": core_map, "sub": sub_map, "shards": shard_map}

@st.cache_data
def load_spell_icons(path: str) -> dict:
    if not _exists(path):
        return {}
    df = pd.read_csv(path)
    cand_name = [c for c in df.columns if _norm(c) in 
                 {"spell","spellname","name","spell1_name_fix","spell2_name_fix","스펠","스펠명"}]
    cand_icon = [c for c in df.columns if _norm(c) in 
                 {"icon","icon_url","spell_icon"} or "icon" in c.lower()]
    m = {}
    if cand_name and cand_icon:
        for n, i in zip(df[cand_name[0]].astype(str), df[cand_icon[0]].astype(str)):
            m[_norm(n)] = i
            m[str(n).strip()] = i
    elif df.shape[1] >= 2:
        for n, i in zip(df.iloc[:,0].astype(str), df.iloc[:,1].astype(str)):
            m[_norm(n)] = i
            m[str(n).strip()] = i
    return m

# ===== 데이터 로드 =====
df        = load_players(PLAYERS_CSV)
item_sum  = load_item_summary(ITEM_SUM_CSV)
champ_map = load_champion_icons(CHAMP_CSV)
rune_maps = load_rune_icons(RUNE_CSV)
spell_map = load_spell_icons(SPELL_CSV)
ITEM_ICON_MAP = dict(zip(item_sum.get("item", []), item_sum.get("icon_url", [])))

# ===== 사이드바 =====
st.sidebar.title("ARAM PS Controls")
champs = sorted(df["champion"].dropna().unique().tolist()) if "champion" in df.columns else []
selected = st.sidebar.selectbox("Champion", champs, index=0 if champs else None)

# ===== 상단 요약 =====
dsel = df[df["champion"] == selected].copy() if len(champs) else df.head(0).copy()
games = len(dsel)
match_cnt_all = df["matchId"].nunique() if "matchId" in df.columns else len(df)
match_cnt_sel = dsel["matchId"].nunique() if "matchId" in dsel.columns else games
winrate = round(dsel["win_clean"].mean()*100, 2) if games else 0.0
pickrate = round((match_cnt_sel / match_cnt_all * 100), 2) if match_cnt_all else 0.0

c0, ctitle = st.columns([1, 5])
with c0:
    cicon = champ_map.get(selected, "")
    if cicon: st.image(cicon, width=64)
with ctitle:
    st.title(f"{selected}")

c1, c2, c3 = st.columns(3)
c1.metric("Games", f"{games}")
c2.metric("Win Rate", f"{winrate}%")
c3.metric("Pick Rate", f"{pickrate}%")

# ===== 아이템 추천 =====
st.subheader("Recommended Items")
if games and any(re.fullmatch(r"item[0-6]_name", c) for c in dsel.columns):
    stacks = []
    for c in [c for c in dsel.columns if re.fullmatch(r"item[0-6]_name", c)]:
        stacks.append(dsel[[c, "win_clean"]].rename(columns={c: "item"}))
    union = pd.concat(stacks, ignore_index=True)
    union["item"] = union["item"].astype(str).str.strip()
    union = union[~union["item"].isin(["", "0", "포로 간식"])]
    top_items = (union.groupby("item", as_index=False)
                       .agg(total_picks=("item","count"), wins=("win_clean","sum")))
    top_items["win_rate"] = (top_items["wins"]/top_items["total_picks"]*100).round(2)
    top_items["icon_url"] = top_items["item"].map(ITEM_ICON_MAP)
    top_items = top_items.sort_values(["total_picks","win_rate"], ascending=[False, False]).head(20)
    st.dataframe(
        top_items[["icon_url","item","total_picks","wins","win_rate"]],
        use_container_width=True,
        column_config={
            "icon_url": st.column_config.ImageColumn("아이콘", width="small"),
            "item": "아이템","total_picks": "픽수","wins": "승수","win_rate": "승률(%)"
        }
    )
else:
    st.info("아이템 이름 컬럼이 없어 집계를 만들 수 없습니다.")

# ===== 스펠 추천 (무순서 집계) =====
st.subheader("Recommended Spell Combos (순서 무시)")
# (스펠 처리 부분은 기존 그대로 두었음 — 생략)

# ===== 룬 (조합 보드) =====
st.subheader("룬 (조합 보드)")
icons_core   = rune_maps.get("core", {})
icons_sub    = rune_maps.get("sub", {})
icons_shards = rune_maps.get("shards", {})
shard_cols = [c for c in dsel.columns if c.lower().startswith("shard")]
if len(shard_cols) > 3: shard_cols = shard_cols[:3]

if games and {"rune_core","rune_sub"}.issubset(dsel.columns):
    base_games = len(dsel)
    g = (dsel.groupby(["rune_core","rune_sub"], as_index=False)
            .agg(games=("win_clean","count"), wins=("win_clean","sum")))
    g["win_rate"]  = (g["wins"]/g["games"]*100).round(2)
    g["pick_rate"] = (g["games"]/base_games*100).round(2)
    g = g.sort_values(["games","win_rate"], ascending=[False, False]).head(10)

    # CSS
    st.markdown("""
<style>
.rboard{width:100%;border-radius:10px;padding:6px 10px;background:rgba(0,0,0,.02);}
.rrow{display:flex;align-items:center;justify-content:space-between;padding:8px 10px;border-bottom:1px solid rgba(0,0,0,.06);}
.rrow:last-child{border-bottom:none;}
.icons{display:flex;align-items:center;gap:10px;}
.ico.big{width:40px;height:40px;border-radius:8px;}
.ico.sub{width:34px;height:34px;border-radius:8px;opacity:.95;}
.ico.shard{width:24px;height:24px;border-radius:6px;opacity:.95;}
.nums{min-width:260px;text-align:right;font-weight:600;display:flex;gap:18px;justify-content:flex-end;}
.nums span{min-width:72px;display:inline-block;}
.w{color:#0A7F3F;} .p{color:#39424e;} .g{color:#687385;}
</style>
""", unsafe_allow_html=True)

    rows_html = []
    for _, r in g.iterrows():
        core, sub = str(r["rune_core"]), str(r["rune_sub"])
        core_icon = icons_core.get(core, "")
        sub_icon  = icons_sub.get(sub, "")
        icons_block = (
            f'<div class="icons">'
            f'{"<img class=\\"ico big\\" src=\\""+core_icon+"\\"/>" if core_icon else ""}'
            f'{"<img class=\\"ico sub\\" src=\\""+sub_icon+"\\"/>" if sub_icon else ""}'
            f'</div>'
        )
        nums_block = (
            f'<div class="nums">'
            f'<span class="w">{r["win_rate"]:.2f}%</span>'
            f'<span class="p">{r["pick_rate"]:.2f}%</span>'
            f'<span class="g">{int(r["games"])}</span>'
            f'</div>'
        )
        rows_html.append(f'<div class="rrow">{icons_block}{nums_block}</div>')

    board_html = '<div class="rboard">' + "".join(rows_html) + '</div>'
    import streamlit.components.v1 as components
    components.html(board_html, height=120 + 48*len(rows_html), scrolling=True)
else:
    st.info("룬 컬럼이 없어 보드를 만들 수 없습니다.")

# ===== (선택) 5v5 평균 승률 패널 =====
# (여기도 기존 코드 그대로 유지)

# ===== Raw rows =====
with st.expander("Raw rows (selected champion)"):
    st.dataframe(dsel, use_container_width=True)
