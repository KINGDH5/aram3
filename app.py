# app.py — ARAM 챔피언 대시보드
# - 아이템 0/포로 간식 전처리
# - 스펠 조합 "순서 무시" 집계
# - 룬 보드(아이콘 나열형) : u.gg 스타일 간이 레이아웃

import os, re, json
import pandas as pd
import streamlit as st

st.set_page_config(page_title="ARAM PS Dashboard", layout="wide")

# ===== 파일 경로 =====
PLAYERS_CSV = "aram_participants_with_icons_superlight.csv"
ITEM_SUM_CSV = "item_summary_with_icons.csv"
CHAMP_CSV = "champion_icons.csv"
RUNE_CSV = "rune_icons.csv"        # (type,name,icon_url) 또는 구스키마도 지원
SPELL_CSV = "spell_icons.csv"
DD_VERSION = "15.16.1"

# ===== 유틸 =====
def _exists(path: str) -> bool:
    ok = os.path.exists(path)
    if not ok: st.warning(f"파일 없음: `{path}`")
    return ok

def _norm(x: str) -> str:
    return re.sub(r"\s+", "", str(x)).strip().lower()

# ===== 로더 =====
@st.cache_data
def load_players(path: str) -> pd.DataFrame:
    if not _exists(path): st.stop()
    df = pd.read_csv(path)

    # 승패 플래그
    if "win_clean" not in df.columns:
        df["win_clean"] = (
            df.get("win", pd.Series([0]*len(df)))
              .astype(str).str.lower().isin(["true","1","t","yes"])
              .astype(int)
        )

    # 아이템 전처리: 공백/0 제거
    for c in [c for c in df.columns if re.fullmatch(r"item[0-6]_name", c)]:
        df[c] = df[c].fillna("").astype(str).str.strip().replace({"0":"", 0:"", "포로 간식":""})

    # 문자열 정리
    for c in ["spell1","spell2","spell1_name_fix","spell2_name_fix",
              "rune_core","rune_sub","champion","matchId"]:
        if c in df.columns:
            df[c] = df[c].fillna("").astype(str).str.strip()
    return df

@st.cache_data
def load_item_summary(path: str) -> pd.DataFrame:
    if not _exists(path): return pd.DataFrame()
    g = pd.read_csv(path)
    if "item" in g.columns:
        g["item"] = g["item"].astype(str).str.strip()
        g = g[~g["item"].isin(["","0","포로 간식"])]
    return g

@st.cache_data
def load_champion_icons(path: str) -> dict:
    if not _exists(path): return {}
    df = pd.read_csv(path)
    name_col = next((c for c in ["champion","Champion","championName"] if c in df.columns), None)
    icon_col = next((c for c in ["champion_icon","icon","icon_url"] if c in df.columns), None)
    if not name_col or not icon_col: return {}
    return dict(zip(df[name_col].astype(str).str.strip(), df[icon_col]))

@st.cache_data
def load_rune_icons(path: str) -> dict:
    """지원 스키마:
       (A) type,name,icon_url  / (B) rune_core(_icon), rune_sub(_icon), rune_shard(_icon)
       return {"core":{}, "sub":{}, "shards":{}, "raw_df":DataFrame|None}
    """
    if not _exists(path): return {"core":{}, "sub":{}, "shards":{}, "raw_df":None}
    df = pd.read_csv(path)

    core_map, sub_map, shard_map = {}, {}, {}
    if {"type","name","icon_url"}.issubset(df.columns):
        core_map  = dict(df[df["type"]=="core"][["name","icon_url"]].values)
        sub_map   = dict(df[df["type"]=="sub"][["name","icon_url"]].values)
        shard_map = dict(df[df["type"]=="shard"][["name","icon_url"]].values)
        return {"core":core_map, "sub":sub_map, "shards":shard_map, "raw_df":df}

    if "rune_core" in df and "rune_core_icon" in df:
        core_map = dict(zip(df["rune_core"], df["rune_core_icon"]))
    if "rune_sub" in df and "rune_sub_icon" in df:
        sub_map = dict(zip(df["rune_sub"], df["rune_sub_icon"]))
    if "rune_shard" in df and ("rune_shard_icon" in df or "rune_shards_icons" in df):
        ic = "rune_shard_icon" if "rune_shard_icon" in df else "rune_shards_icons"
        shard_map = dict(zip(df["rune_shard"], df[ic]))
    return {"core":core_map, "sub":sub_map, "shards":shard_map, "raw_df":None}

@st.cache_data
def load_spell_icons(path: str) -> dict:
    if not _exists(path): return {}
    df = pd.read_csv(path)
    cand_name = [c for c in df.columns if _norm(c) in {"spell","spellname","name","spell1_name_fix","spell2_name_fix","스펠","스펠명"}]
    cand_icon = [c for c in df.columns if "icon" in c.lower()]
    m = {}
    if cand_name and cand_icon:
        for n,i in zip(df[cand_name[0]].astype(str), df[cand_icon[0]].astype(str)):
            m[_norm(n)] = i; m[n.strip()] = i
    elif df.shape[1] >= 2:
        for n,i in zip(df.iloc[:,0].astype(str), df.iloc[:,1].astype(str)):
            m[_norm(n)] = i; m[n.strip()] = i
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
dsel = df[df["champion"] == selected].copy() if champs else df.head(0).copy()
games = len(dsel)
match_cnt_all = df["matchId"].nunique() if "matchId" in df else len(df)
match_cnt_sel = dsel["matchId"].nunique() if "matchId" in dsel else games
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
    stacks = [dsel[[c,"win_clean"]].rename(columns={c:"item"})
              for c in dsel.columns if re.fullmatch(r"item[0-6]_name", c)]
    union = pd.concat(stacks, ignore_index=True)
    union["item"] = union["item"].astype(str).str.strip()
    union = union[~union["item"].isin(["","0","포로 간식"])]

    top_items = (union.groupby("item", as_index=False)
                      .agg(total_picks=("item","count"), wins=("win_clean","sum")))
    top_items["win_rate"] = (top_items["wins"]/top_items["total_picks"]*100).round(2)
    top_items["icon_url"] = top_items["item"].map(ITEM_ICON_MAP)
    top_items = top_items.sort_values(["total_picks","win_rate"],
                                      ascending=[False, False]).head(20)

    st.dataframe(
        top_items[["icon_url","item","total_picks","wins","win_rate"]],
        use_container_width=True,
        column_config={
            "icon_url": st.column_config.ImageColumn("아이콘", width="small"),
            "item":"아이템","total_picks":"픽수","wins":"승수","win_rate":"승률(%)"
        }
    )
else:
    st.info("아이템 이름 컬럼(item0_name~item6_name)이 없어 챔피언별 아이템 집계를 만들 수 없습니다.")

# ===== 스펠 추천 (순서 무시) =====
st.subheader("Recommended Spell Combos (순서 무시)")

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
    return SPELL_ALIASES.get(_norm(s), s)

def ddragon_spell_icon(s: str) -> str:
    key = {"점멸":"SummonerFlash","표식":"SummonerSnowball","유체화":"SummonerHaste","회복":"SummonerHeal",
           "점화":"SummonerDot","정화":"SummonerBoost","탈진":"SummonerExhaust","방어막":"SummonerBarrier",
           "총명":"SummonerMana","순간이동":"SummonerTeleport"}.get(standard_korean_spell(s))
    return f"https://ddragon.leagueoflegends.com/cdn/{DD_VERSION}/img/spell/{key}.png" if key else ""

def resolve_spell_icon(name: str) -> str:
    if not name: return ""
    raw = str(name).strip()
    for k in (raw, _norm(raw), standard_korean_spell(raw), _norm(standard_korean_spell(raw))):
        if k in spell_map: return spell_map[k]
    return ddragon_spell_icon(raw)

def pick_spell_cols(df_):
    if {"spell1_name_fix","spell2_name_fix"}.issubset(df_.columns): return "spell1_name_fix","spell2_name_fix"
    if {"spell1","spell2"}.issubset(df_.columns): return "spell1","spell2"
    cands = [c for c in df_.columns if "spell" in c.lower()]
    return (cands[0], cands[1]) if len(cands) >= 2 else (None,None)

def canonical_pair(a: str, b: str):
    a_std, b_std = standard_korean_spell(a or ""), standard_korean_spell(b or "")
    return (a_std, b_std) if (_norm(a_std),_norm(b_std)) <= (_norm(b_std),_norm(a_std)) else (b_std,a_std)

s1, s2 = pick_spell_cols(dsel)
if games and s1 and s2:
    tmp = dsel[[s1, s2, "win_clean"]].copy()
    tmp["s1_std"], tmp["s2_std"] = zip(*tmp.apply(lambda r: canonical_pair(r[s1], r[s2]), axis=1))
    sp = tmp.groupby(["s1_std","s2_std"], as_index=False).agg(games=("win_clean","count"), wins=("win_clean","sum"))
    sp["win_rate"] = (sp["wins"]/sp["games"]*100).round(2)
    sp = sp.sort_values(["games","win_rate"], ascending=[False,False]).head(10)
    sp["spell1_icon"] = sp["s1_std"].apply(resolve_spell_icon)
    sp["spell2_icon"] = sp["s2_std"].apply(resolve_spell_icon)
    st.dataframe(
        sp[["spell1_icon","s1_std","spell2_icon","s2_std","games","wins","win_rate"]],
        use_container_width=True,
        column_config={
            "spell1_icon": st.column_config.ImageColumn("스펠1", width="small"),
            "spell2_icon": st.column_config.ImageColumn("스펠2", width="small"),
            "s1_std":"스펠1 이름","s2_std":"스펠2 이름",
            "games":"게임수","wins":"승수","win_rate":"승률(%)"
        }
    )
else:
    st.info("스펠 컬럼을 찾지 못했습니다. (spell1_name_fix/spell2_name_fix 또는 spell1/spell2 필요)")

# ===== 룬 보드 (아이콘 나열형) =====
st.subheader("룬 (조합 보드)")

icons_core   = rune_maps.get("core", {})
icons_sub    = rune_maps.get("sub", {})
icons_shards = rune_maps.get("shards", {})

# 파편 컬럼 자동 감지 (있으면 3개까지 붙여줌)
SHARD_COLS = [c for c in dsel.columns if c.lower().startswith("shard")]
if len(SHARD_COLS) > 3:  # 많으면 앞의 3개만 사용
    SHARD_COLS = SHARD_COLS[:3]

# 통계 집계 (핵심룬+보조트리 기준)
if games and {"rune_core","rune_sub"}.issubset(dsel.columns):
    base_games = len(dsel)
    g = (dsel.groupby(["rune_core","rune_sub"], as_index=False)
               .agg(games=("win_clean","count"), wins=("win_clean","sum")))
    g["win_rate"]  = (g["wins"]/g["games"]*100).round(2)
    g["pick_rate"] = (g["games"]/base_games*100).round(2)
    g = g.sort_values(["games","win_rate"], ascending=[False,False]).head(10)

    # 파편 조합(있으면) 합치기: 가장 흔한 1개만 붙임
    if SHARD_COLS:
        shards_top = (dsel.groupby(SHARD_COLS).size().reset_index(name="cnt")
                          .sort_values("cnt", ascending=False).head(1))
        shard_tuple = tuple(shards_top.iloc[0][SHARD_COLS].astype(str)) if len(shards_top) else tuple()
    else:
        shard_tuple = tuple()

    # 보드 CSS
    st.markdown("""
    <style>
    .rboard { width:100%; border-radius:10px; padding:6px 10px; background:rgba(0,0,0,0.02);}
    .rrow { display:flex; align-items:center; justify-content:space-between; padding:8px 10px; border-bottom:1px solid rgba(0,0,0,0.05);}
    .rrow:last-child{ border-bottom:none; }
    .icons { display:flex; align-items:center; gap:8px; }
    .ico.big{ width:40px; height:40px; border-radius:8px; }
    .ico.sub{ width:34px; height:34px; border-radius:8px; opacity:.95;}
    .ico.shard{ width:24px; height:24px; border-radius:6px; opacity:.95;}
    .nums { min-width:260px; text-align:right; font-weight:600; display:flex; gap:16px; justify-content:flex-end; }
    .nums span { min-width:72px; display:inline-block; }
    .w { color:#0A7F3F; }   /* 승률 */
    .p { color:#444; }      /* 채택률 */
    .g { color:#666; }      /* 게임수 */
    </style>
    """, unsafe_allow_html=True)

    # 행 그리기
    html = ['<div class="rboard">']
    for _, row in g.iterrows():
        core_name = str(row["rune_core"])
        sub_name  = str(row["rune_sub"])
        core_icon = icons_core.get(core_name, "")
        sub_icon  = icons_sub.get(sub_name, "")

        # 파편 아이콘 렌더 (있으면 3개)
        shard_imgs = ""
        if shard_tuple and icons_shards:
            for s in shard_tuple:
                url = icons_shards.get(str(s), "")
                if url:
                    shard_imgs += f'<img class="ico shard" src="{url}"/>'
        shard_block = shard_imgs

        icons_block = f"""
          <div class="icons">
            {'<img class="ico big" src=\''+core_icon+'\'/>' if core_icon else ''}
            {'<img class="ico sub" src=\''+sub_icon+'\'/>' if sub_icon else ''}
            {shard_block}
          </div>
        """

        nums_block = f"""
          <div class="nums">
            <span class="w">{row['win_rate']:.2f}%</span>
            <span class="p">{row['pick_rate']:.2f}%</span>
            <span class="g">{int(row['games'])}</span>
          </div>
        """

        html.append(f'<div class="rrow">{icons_block}{nums_block}</div>')
    html.append('</div>')
    st.markdown("\n".join(html), unsafe_allow_html=True)
else:
    st.info("룬 컬럼(rune_core, rune_sub)이 없어 보드를 만들 수 없습니다.")

# ===== 5v5 평균 승률 패널 =====
st.header("5v5 평균 승률 비교 & 전략 (단일 패널)")
with st.container():
    st.markdown(
        "- **챔피언 10명**을 입력하세요: **앞 5명=팀 A(아군)**, **뒤 5명=팀 B(적군)**. (쉼표 또는 공백 구분)\n"
        "- 모델 학습 전이므로 **챔피언별 베이스라인 승률의 단순 평균**을 비교합니다."
    )

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

    raw = st.text_area(
        "챔피언 10명 입력 (예: Lux Ziggs Sona Seraphine Ashe, Darius Garen Katarina Yasuo Aatrox)",
        placeholder="Lux Ziggs Sona Seraphine Ashe, Darius Garen Katarina Yasuo Aatrox"
    )
    api_key = st.text_input("OpenAI API 키 (선택: 전략 생성용)", type="password", placeholder="sk-...")

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

# ===== 원본 표 =====
with st.expander("Raw rows (selected champion)"):
    st.dataframe(dsel, use_container_width=True)
