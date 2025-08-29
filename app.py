# app.py — ARAM 챔피언 대시보드 (+ 한 패널: 5v5 평균 승률 & GPT 전략)
import os, re, json
import pandas as pd
import streamlit as st

st.set_page_config(page_title="ARAM PS Dashboard", layout="wide")

# ===== 파일 경로(리포 루트) =====
PLAYERS_CSV   = "aram_participants_with_icons_superlight.csv"  # 참가자 행 데이터
ITEM_SUM_CSV  = "item_summary_with_icons.csv"                  # item, icon_url, total_picks, wins, win_rate
CHAMP_CSV     = "champion_icons.csv"                           # champion, champion_icon (또는 icon/icon_url)
RUNE_CSV      = "rune_icons.csv"                               # rune_core, rune_core_icon, rune_sub, rune_sub_icon
SPELL_CSV     = "spell_icons.csv"                              # 스펠이름, 아이콘URL (헤더 자유)

DD_VERSION = "15.16.1"  # Data Dragon 폴백 버전 (필요시 최신으로 교체)

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
            df["win_clean"] = df["win"].astype(str).str.lower().isin(["true","1","t","yes"]).astype(int)
        else:
            df["win_clean"] = 0

    # 아이템 이름 정리
    for c in [c for c in df.columns if re.fullmatch(r"item[0-6]_name", c)]:
        df[c] = df[c].fillna("").astype(str).str.strip()

    # 기본 텍스트 컬럼
    for c in ["spell1","spell2","spell1_name_fix","spell2_name_fix","rune_core","rune_sub","champion","matchId"]:
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
    return g

@st.cache_data
def load_champion_icons(path: str) -> dict:
    if not _exists(path):
        return {}
    df = pd.read_csv(path)
    name_col = None
    for c in ["champion","Champion","championName"]:
        if c in df.columns:
            name_col = c; break
    icon_col = None
    for c in ["champion_icon","icon","icon_url"]:
        if c in df.columns:
            icon_col = c; break
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
    if "rune_core" in df.columns:
        ic = "rune_core_icon" if "rune_core_icon" in df.columns else None
        if ic: core_map = dict(zip(df["rune_core"].astype(str), df[ic].astype(str)))
    if "rune_sub" in df.columns:
        ic = "rune_sub_icon" if "rune_sub_icon" in df.columns else None
        if ic: sub_map = dict(zip(df["rune_sub"].astype(str), df[ic].astype(str)))
    if "rune_shard" in df.columns:
        ic = "rune_shard_icon" if "rune_shard_icon" in df.columns else ("rune_shards_icons" if "rune_shards_icons" in df.columns else None)
        if ic: shard_map = dict(zip(df["rune_shard"].astype(str), df[ic].astype(str)))
    return {"core": core_map, "sub": sub_map, "shards": shard_map}

@st.cache_data
def load_spell_icons(path: str) -> dict:
    """스펠명(여러 형태) -> 아이콘 URL"""
    if not _exists(path):
        return {}
    df = pd.read_csv(path)
    cand_name = [c for c in df.columns if _norm(c) in {"spell","spellname","name","spell1_name_fix","spell2_name_fix","스펠","스펠명"}]
    cand_icon = [c for c in df.columns if _norm(c) in {"icon","icon_url","spelli con","spell_icon"} or "icon" in c.lower()]
    m = {}
    if cand_name and cand_icon:
        name_col, icon_col = cand_name[0], cand_icon[0]
        for n, i in zip(df[name_col].astype(str), df[icon_col].astype(str)):
            m[_norm(n)] = i
            m[str(n).strip()] = i
    else:
        if df.shape[1] >= 2:
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
    if cicon:
        st.image(cicon, width=64)
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
    union = union[union["item"].astype(str).str.strip() != ""]
    top_items = (
        union.groupby("item")
        .agg(total_picks=("item","count"), wins=("win_clean","sum"))
        .reset_index()
    )
    top_items["win_rate"] = (top_items["wins"]/top_items["total_picks"]*100).round(2)
    top_items["icon_url"] = top_items["item"].map(ITEM_ICON_MAP)
    top_items = top_items.sort_values(["total_picks","win_rate"], ascending=[False, False]).head(20)

    st.dataframe(
        top_items[["icon_url","item","total_picks","wins","win_rate"]],
        use_container_width=True,
        column_config={
            "icon_url": st.column_config.ImageColumn("아이콘", width="small"),
            "item": "아이템", "total_picks": "픽수", "wins": "승수", "win_rate": "승률(%)"
        }
    )
else:
    st.info("아이템 이름 컬럼(item0_name~item6_name)이 없어 챔피언별 아이템 집계를 만들 수 없습니다.")

# ===== 스펠 추천 =====
st.subheader("Recommended Spell Combos")
SPELL_ALIASES = {
    "점멸":"점멸","표식":"표식","눈덩이":"표식","유체화":"유체화","회복":"회복","점화":"점화",
    "정화":"정화","탈진":"탈진","방어막":"방어막","총명":"총명","순간이동":"순간이동",
    "flash":"점멸","mark":"표식","snowball":"표식","ghost":"유체화","haste":"유체화",
    "heal":"회복","ignite":"점화","cleanse":"정화","exhaust":"탈진","barrier":"방어막",
    "clarity":"총명","teleport":"순간이동",
}
KOR_TO_DDRAGON = {
    "점멸":"SummonerFlash","표식":"SummonerSnowball","유체화":"SummonerHaste","회복":"SummonerHeal",
    "점화":"SummonerDot","정화":"SummonerBoost","탈진":"SummonerExhaust","방어막":"SummonerBarrier",
    "총명":"SummonerMana","순간이동":"SummonerTeleport",
}

def standard_korean_spell(s: str) -> str:
    n = _norm(s)
    return SPELL_ALIASES.get(n, s)

def ddragon_spell_icon(s: str) -> str:
    kor = standard_korean_spell(s)
    key = KOR_TO_DDRAGON.get(kor)
    if not key: return ""
    return f"https://ddragon.leagueoflegends.com/cdn/{DD_VERSION}/img/spell/{key}.png"

def resolve_spell_icon(name: str) -> str:
    if not name: return ""
    raw = str(name).strip()
    for k in (raw, _norm(raw), standard_korean_spell(raw), _norm(standard_korean_spell(raw))):
        if k in spell_map: return spell_map[k]
    return ddragon_spell_icon(raw)

def pick_spell_cols(df_):
    if {"spell1_name_fix","spell2_name_fix"}.issubset(df_.columns): return "spell1_name_fix", "spell2_name_fix"
    if {"spell1","spell2"}.issubset(df_.columns): return "spell1", "spell2"
    cands = [c for c in df_.columns if "spell" in c.lower()]
    return (cands[0], cands[1]) if len(cands) >= 2 else (None, None)

s1, s2 = pick_spell_cols(dsel)
if games and s1 and s2:
    sp = (
        dsel.groupby([s1, s2])
        .agg(games=("win_clean","count"), wins=("win_clean","sum"))
        .reset_index()
    )
    sp["win_rate"] = (sp["wins"]/sp["games"]*100).round(2)
    sp = sp.sort_values(["games","win_rate"], ascending=[False,False]).head(10)
    sp["spell1_icon"] = sp[s1].apply(resolve_spell_icon)
    sp["spell2_icon"] = sp[s2].apply(resolve_spell_icon)

    st.dataframe(
        sp[["spell1_icon", s1, "spell2_icon", s2, "games", "wins", "win_rate"]],
        use_container_width=True,
        column_config={
            "spell1_icon": st.column_config.ImageColumn("스펠1", width="small"),
            "spell2_icon": st.column_config.ImageColumn("스펠2", width="small"),
            s1: "스펠1 이름", s2: "스펠2 이름",
            "games":"게임수","wins":"승수","win_rate":"승률(%)"
        }
    )
else:
    st.info("스펠 컬럼을 찾지 못했습니다. (spell1_name_fix/spell2_name_fix 또는 spell1/spell2 필요)")

# ===== 룬 추천 =====
st.subheader("Recommended Rune Combos")
core_map = rune_maps.get("core", {})
sub_map  = rune_maps.get("sub", {})

def _rune_core_icon(name: str) -> str: return core_map.get(name, "")
def _rune_sub_icon(name: str)  -> str: return sub_map.get(name, "")

if games and {"rune_core","rune_sub"}.issubset(dsel.columns):
    ru = (
        dsel.groupby(["rune_core","rune_sub"])
        .agg(games=("win_clean","count"), wins=("win_clean","sum"))
        .reset_index()
    )
    ru["win_rate"] = (ru["wins"]/ru["games"]*100).round(2)
    ru = ru.sort_values(["games","win_rate"], ascending=[False,False]).head(10)
    ru["rune_core_icon"] = ru["rune_core"].apply(_rune_core_icon)
    ru["rune_sub_icon"]  = ru["rune_sub"].apply(_rune_sub_icon)

    st.dataframe(
        ru[["rune_core_icon","rune_core","rune_sub_icon","rune_sub","games","wins","win_rate"]],
        use_container_width=True,
        column_config={
            "rune_core_icon": st.column_config.ImageColumn("핵심룬", width="small"),
            "rune_sub_icon":  st.column_config.ImageColumn("보조트리", width="small"),
            "rune_core":"핵심룬 이름","rune_sub":"보조트리 이름",
            "games":"게임수","wins":"승수","win_rate":"승률(%)"
        }
    )
else:
    st.info("룬 컬럼(rune_core, rune_sub)이 없습니다.")

# ===== (신규) 한 패널: 5v5 평균 승률 vs 평균 승률 + GPT 전략 =====
st.header("5v5 평균 승률 비교 & 전략 (단일 패널)")
with st.container():
    st.markdown(
        "- **챔피언 10명**을 입력하세요: **앞 5명=팀 A(아군)**, **뒤 5명=팀 B(적군)**. (쉼표 또는 공백 구분)\n"
        "- 모델 학습 전이므로 **챔피언별 베이스라인 승률의 단순 평균**을 비교합니다."
    )

    # 1) 챔피언별 베이스라인 승률
    @st.cache_data
    def champion_baseline(df_all: pd.DataFrame) -> pd.DataFrame:
        if "champion" not in df_all.columns: 
            return pd.DataFrame(columns=["champion","games","wins","winrate"])
        g = (df_all.groupby("champion", as_index=False)
                    .agg(games=("win_clean","count"), wins=("win_clean","sum")))
        g["winrate"] = (g["wins"] / g["games"] * 100).round(2)
        return g.sort_values("champion")

    base_tbl = champion_baseline(df)
    base_map = dict(zip(base_tbl["champion"], base_tbl["winrate"]))

    # 2) 입력 — 텍스트 박스 & API 키(직접 입력)
    raw = st.text_area(
        "챔피언 10명 입력 (예: Lux Ziggs Sona Seraphine Ashe, Darius Garen Katarina Yasuo Aatrox)",
        placeholder="Lux Ziggs Sona Seraphine Ashe, Darius Garen Katarina Yasuo Aatrox"
    )
    api_key = st.text_input("OpenAI API 키 (선택: 전략 생성용)", type="password", placeholder="sk-...")

    # 3) 계산 & 출력 (같은 패널)
    def avg_winrate(lst):
        vals = [base_map.get(x, None) for x in lst]
        known = [v for v in vals if v is not None]
        return round(sum(known)/len(known), 2) if known else None, [x for x,v in zip(lst, vals) if v is None]

    if raw.strip():
        toks = re.split(r"[,\s]+", raw.strip())
        toks = [t for t in toks if t]
        if len(toks) >= 10:
            ally, enemy = toks[:5], toks[5:10]
            a_avg, a_missing = avg_winrate(ally)
            b_avg, b_missing = avg_winrate(enemy)

            c1, c2 = st.columns(2)
            with c1:
                st.metric("Team A 평균 승률", f"{a_avg if a_avg is not None else 'N/A'}%")
                st.caption("A: " + ", ".join(ally))
                if a_missing: st.error("A 데이터 없음: " + ", ".join(a_missing))
            with c2:
                st.metric("Team B 평균 승률", f"{b_avg if b_avg is not None else 'N/A'}%")
                st.caption("B: " + ", ".join(enemy))
                if b_missing: st.error("B 데이터 없음: " + ", ".join(b_missing))

            st.divider()
            st.subheader("전략 코멘트 (선택)")
            if api_key:
                try:
                    import openai
                    openai.api_key = api_key
                    a_show = f"{a_avg}%" if a_avg is not None else "N/A"
                    b_show = f"{b_avg}%" if b_avg is not None else "N/A"
                    prompt = f"""
너는 LoL ARAM 코치다. 아래 정보를 바탕으로 3~5줄 전략을 제시하라.

Team A: {', '.join(ally)} (avg {a_show})
Team B: {', '.join(enemy)} (avg {b_show})

조건:
- 단순 평균 승률 기반임을 전제(시너지/상성 미반영)
- 초반/중반/후반 전략 중 핵심 1~2개
- 과도한 확신/허풍 금지, 간결하게
""".strip()
                    resp = openai.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role":"user","content":prompt}],
                        temperature=0.6,
                        max_tokens=220,
                    )
                    st.write(resp.choices[0].message.content.strip())
                except Exception as e:
                    st.error(f"전략 생성 실패: {e}")
            else:
                st.info("전략 코멘트를 보려면 OpenAI API 키를 입력하세요.")
        else:
            st.warning("챔피언 10명을 입력해야 합니다 (앞5=팀 A, 뒤5=팀 B).")

# ===== 원본(선택 챔피언) =====
with st.expander("Raw rows (selected champion)"):
    st.dataframe(dsel, use_container_width=True)
