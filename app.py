# app.py — ARAM 챔피언 대시보드 (+ 아이템 0/포로간식 제외, 스펠 무순서 집계, 패치버전 선택 UI)
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

    # 승패 정리
    if "win_clean" not in df.columns:
        if "win" in df.columns:
            df["win_clean"] = df["win"].astype(str).str.lower().isin(
                ["true","1","t","yes"]
            ).astype(int)
        else:
            df["win_clean"] = 0

    # 아이템 이름 정리 + "0", 포로 간식 전처리
    for c in [c for c in df.columns if re.fullmatch(r"item[0-6]_name", c)]:
        df[c] = df[c].fillna("").astype(str).str.strip()
        df[c] = df[c].replace({"0": "", 0: "", "포로 간식": ""})

    # 기본 텍스트 컬럼
    for c in ["spell1","spell2","spell1_name_fix","spell2_name_fix",
              "rune_core","rune_sub","champion","matchId","gameVersion"]:
        if c in df.columns:
            df[c] = df[c].fillna("").astype(str).str.strip()

    # 패치 버전 추출
    if "patch" not in df.columns:
        if "gameVersion" in df.columns:
            df["patch"] = df["gameVersion"].str.extract(r"(\d{1,2}\.\d{1,2})")
        else:
            df["patch"] = None
    return df

@st.cache_data
def load_item_summary(path: str) -> pd.DataFrame:
    if not _exists(path): return pd.DataFrame()
    g = pd.read_csv(path)
    if "item" in g.columns:
        g = g[~g["item"].isin(["","0","포로 간식"])]
    return g

@st.cache_data
def load_champion_icons(path: str) -> dict:
    if not _exists(path): return {}
    df = pd.read_csv(path)
    name_col = next((c for c in ["champion","Champion","championName"] if c in df.columns), None)
    icon_col = next((c for c in ["champion_icon","icon","icon_url"] if c in df.columns), None)
    if not name_col or not icon_col: return {}
    df[name_col] = df[name_col].astype(str).str.strip()
    return dict(zip(df[name_col], df[icon_col]))

@st.cache_data
def load_rune_icons(path: str) -> dict:
    if not _exists(path): return {"core": {}, "sub": {}, "shards": {}}
    df = pd.read_csv(path)
    core_map, sub_map = {}, {}
    if "rune_core" in df.columns:
        if "rune_core_icon" in df.columns:
            core_map = dict(zip(df["rune_core"], df["rune_core_icon"]))
    if "rune_sub" in df.columns:
        if "rune_sub_icon" in df.columns:
            sub_map = dict(zip(df["rune_sub"], df["rune_sub_icon"]))
    return {"core": core_map, "sub": sub_map}

@st.cache_data
def load_spell_icons(path: str) -> dict:
    if not _exists(path): return {}
    df = pd.read_csv(path)
    cand_name = [c for c in df.columns if _norm(c) in {"spell","spellname","name","스펠","스펠명"}]
    cand_icon = [c for c in df.columns if "icon" in c.lower()]
    m = {}
    if cand_name and cand_icon:
        for n, i in zip(df[cand_name[0]].astype(str), df[cand_icon[0]].astype(str)):
            m[_norm(n)] = i; m[str(n).strip()] = i
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
champs = sorted(df["champion"].dropna().unique().tolist())
selected = st.sidebar.selectbox("Champion", champs, index=0 if champs else None)

# ===== 상단 요약 + 패치버전 선택 버튼 =====
patches = sorted([p for p in df["patch"].dropna().unique().tolist() if p])
latest = patches[-1] if patches else None

c0, ctitle, cpatch = st.columns([1,4,2])
with c0:
    cicon = champ_map.get(selected, "")
    if cicon: st.image(cicon, width=64)
with ctitle:
    st.title(f"{selected}")
with cpatch:
    sel_patch = st.selectbox("Patch", patches, index=(patches.index(latest) if latest in patches else 0))

# 선택된 패치로 필터링
if sel_patch:
    df = df[df["patch"] == sel_patch].copy()

dsel = df[df["champion"] == selected].copy()
games = len(dsel)
winrate = round(dsel["win_clean"].mean()*100, 2) if games else 0
pickrate = round((dsel["matchId"].nunique()/df["matchId"].nunique()*100),2) if games else 0

c1,c2,c3 = st.columns(3)
c1.metric("Games", f"{games}")
c2.metric("Win Rate", f"{winrate}%")
c3.metric("Pick Rate", f"{pickrate}%")

# ===== 아이템 추천 =====
st.subheader("Recommended Items")
if games:
    stacks = [dsel[[c,"win_clean"]].rename(columns={c:"item"}) 
              for c in dsel.columns if re.fullmatch(r"item[0-6]_name", c)]
    union = pd.concat(stacks, ignore_index=True)
    union = union[~union["item"].isin(["","0","포로 간식"])]

    top_items = (union.groupby("item")
                       .agg(total_picks=("item","count"), wins=("win_clean","sum"))
                       .reset_index())
    top_items["win_rate"] = (top_items["wins"]/top_items["total_picks"]*100).round(2)
    top_items["icon_url"] = top_items["item"].map(ITEM_ICON_MAP)
    top_items = top_items.sort_values(["total_picks","win_rate"], ascending=[False,False]).head(20)

    st.dataframe(top_items[["icon_url","item","total_picks","wins","win_rate"]],
                 use_container_width=True,
                 column_config={"icon_url": st.column_config.ImageColumn("아이콘", width="small"),
                                "item":"아이템","total_picks":"픽수","wins":"승수","win_rate":"승률(%)"})
else:
    st.info("해당 챔피언 데이터가 없습니다.")

# ===== 스펠 추천 (순서 무시) =====
st.subheader("Recommended Spell Combos (순서 무시)")

def canonical_pair(a,b):
    return tuple(sorted([a or "", b or ""], key=_norm))

s1,s2 = ("spell1_name_fix","spell2_name_fix") if {"spell1_name_fix","spell2_name_fix"}.issubset(dsel.columns) else ("spell1","spell2")
if games and s1 in dsel and s2 in dsel:
    tmp = dsel[[s1,s2,"win_clean"]].copy()
    tmp["s1"],tmp["s2"] = zip(*tmp.apply(lambda r: canonical_pair(r[s1],r[s2]), axis=1))
    sp = tmp.groupby(["s1","s2"],as_index=False).agg(games=("win_clean","count"), wins=("win_clean","sum"))
    sp["win_rate"] = (sp["wins"]/sp["games"]*100).round(2)
    st.dataframe(sp[["s1","s2","games","wins","win_rate"]], use_container_width=True)
else:
    st.info("스펠 데이터 없음")

# ===== 룬 추천 =====
st.subheader("Recommended Rune Combos")
if games and {"rune_core","rune_sub"}.issubset(dsel.columns):
    ru = dsel.groupby(["rune_core","rune_sub"]).agg(games=("win_clean","count"), wins=("win_clean","sum")).reset_index()
    ru["win_rate"] = (ru["wins"]/ru["games"]*100).round(2)
    st.dataframe(ru, use_container_width=True)
