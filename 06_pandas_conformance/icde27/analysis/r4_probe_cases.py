"""Probes for the single-rater behaviours (review round R4, 2026-11-10), on small synthetic inputs, outside the
capture harness (no capture, no AST instrumentation, no notebook runner).

Run: PCONF_REPRO_MODE=<pandas|modin|fireducks|bodo> <env python> r4_probe_cases.py
Every check prints one line "RESULT <name>: <value>". icde27/analysis/r4_probes.py runs this file in envs/ref and in
the engine environments (under tools/memory_guard.py, Bodo with one MPI worker as in the conformance runs) and
compares each engine line with the pandas line. Each check copies the pattern of notebook cells that the single
rater attributed (icde27/analysis/r1_hand_attribution.json, cause in parentheses):
  apply_*            shivavashishtha/zomato-eda-tutorial c33/c39 and yonelanuba/elo-merchant-by-yonela c75/c80
                     (apply_side_effects_lost; observed under Modin)
  stale_map_head     kwullum/when-do-traffic-related-deaths-occur c4 (stale_after_inplace_update; Bodo)
  stale_multiply_head  gmanish/help-ngo-country-clustering c9 (same; Bodo)
  stale_assign_head  artgor/eda-and-models c34 (same; Bodo)
  stale_at_*         danielresende/game-of-thrones-battles c5/c7/c8 (same; FireDucks)
  filter_index_drop  snanilim/video-games-sales-analysis-and-visualization c2 (index_not_preserved; Bodo)
  unique_* nunique_*  beratozmen/clash-of-clans-exploratory-data-analysis c7, jyotsananegi/melbourne-housing-snapshot-eda c4,
                     willkoehrsen/start-here-a-gentle-introduction c10 (unique_nunique_missing; FireDucks)
A line "<check>_if_stale" gives, computed with plain pandas in every mode, what the check would return if the engine
showed the data from before the update ("_if_stale_all": before every in-place update of the check).
"""
import os
import warnings

warnings.simplefilter("ignore")
MODE = os.environ.get("PCONF_REPRO_MODE", "pandas")   # pandas | modin | fireducks | bodo
if MODE == "modin":
    import ray
    ray.init(num_cpus=2, include_dashboard=False, log_to_driver=False, object_store_memory=2 * 10**9)
    import modin.pandas as pd
elif MODE == "fireducks":
    import fireducks.pandas as pd
elif MODE == "bodo":
    import bodo.pandas as pd
else:
    import pandas as pd
import numpy as np
import pandas as _pandas

TMP = os.path.join(os.environ.get("TMPDIR", "/tmp"), "pconf_r4_probe_%s_%d" % (MODE, os.getpid()))
os.makedirs(TMP, exist_ok=True)


def write(name, text):
    p = os.path.join(TMP, name + ".csv")
    with open(p, "w") as f:
        f.write(text)
    return p


def plain(o):
    """Engine object -> pandas object (or the object itself)."""
    if hasattr(o, "_to_pandas"):
        return o._to_pandas()
    if hasattr(o, "to_pandas") and not isinstance(o, (_pandas.DataFrame, _pandas.Series, np.ndarray)):
        try:
            return o.to_pandas()
        except Exception:
            return o
    return o


def miss(v):
    return v is None or v is _pandas.NA or (isinstance(v, float) and v != v)


def check(name, fn):
    try:
        print("RESULT %s: %s" % (name, fn()), flush=True)
    except Exception as e:
        print("RESULT %s: raised %s: %s" % (name, type(e).__name__, (str(e).splitlines() or [""])[0][:160]), flush=True)


print("RESULT env: mode=%s pandas=%s" % (MODE, _pandas.__version__), flush=True)

# --- functions passed to apply that change driver-side state (Modin) -------------------------------------------------
N = 30000
P_CUIS = write("cuisines", "cuisines\n" + "\n".join('"%s"' % ["a, b", "c, d, e", "f"][i % 3] for i in range(N)) + "\n")


def apply_extend_global_list():
    data = pd.read_csv(P_CUIS)
    cuisines = []
    data["cuisines"].apply(lambda x: cuisines.extend(x.split(", ")))
    return len(cuisines)


def apply_mutate_list_element():
    data = pd.read_csv(P_CUIS)
    counter = [0]

    def f(x):
        counter[0] += 1
        return x
    data["cuisines"] = data["cuisines"].apply(lambda x: f(x))
    return counter[0]


check("apply_extend_global_list", apply_extend_global_list)
check("apply_mutate_list_element", apply_mutate_list_element)

# --- updates that a later head() or operation may not see (Bodo, FireDucks) -------------------------------------------
P_TRAFFIC = write("traffic", "Day_of_Week,Time\n" + "\n".join(
    "%d,%02d:%02d" % (i % 7 + 1, (i * 5) % 24, (i * 7) % 60) if i % 13 else "%d," % (i % 7 + 1) for i in range(400)) + "\n")


def stale_map_head():
    df = pd.read_csv(P_TRAFFIC, usecols=["Day_of_Week", "Time"])
    df.dropna(inplace=True)
    df.head()
    df["Time"] = df["Time"].map(lambda x: str(x)[:-3])
    return ["MISSING" if miss(v) else str(v) for v in plain(df.head())["Time"]]


def stale_map_head_if_stale(dropna=True):
    df = _pandas.read_csv(P_TRAFFIC, usecols=["Day_of_Week", "Time"])
    df = df.dropna() if dropna else df
    return ["MISSING" if miss(v) else str(v) for v in df.head()["Time"]]


check("stale_map_head", stale_map_head)
check("stale_map_head_if_stale", stale_map_head_if_stale)
check("stale_map_head_if_stale_all", lambda: stale_map_head_if_stale(dropna=False))   # dropna(inplace=True) unseen too

P_COUNTRIES = write("countries", "country,exports,health,imports,gdpp\n" + "\n".join(
    "c%d,%.1f,%.2f,%.1f,%d" % (i, 10 + i * 1.5, 4 + i * 0.25, 20 + i, 500 * (i + 1)) for i in range(60)) + "\n")


def stale_multiply_head():
    countries = pd.read_csv(P_COUNTRIES)
    countries.head()
    countries[["exports", "health", "imports"]] = \
        countries[["exports", "health", "imports"]].multiply(countries["gdpp"] / 100, axis="index")
    return [round(float(v), 6) for v in plain(countries.head())["exports"]]


def stale_multiply_head_if_stale():
    return [round(float(v), 6) for v in _pandas.read_csv(P_COUNTRIES).head()["exports"]]


check("stale_multiply_head", stale_multiply_head)
check("stale_multiply_head_if_stale", stale_multiply_head_if_stale)

P_SUB = write("sample_submission", "TransactionID,isFraud\n" + "\n".join("%d,0.5" % (3663549 + i) for i in range(200)) + "\n")


def stale_assign_head():
    sub = pd.read_csv(P_SUB)
    result = np.linspace(0.0, 1.0, 250)
    result = result[:min(len(sub), len(result))]
    sub["isFraud"] = result
    sub.to_csv(os.path.join(TMP, "submission.csv"), index=False)
    return [round(float(v), 6) for v in plain(sub.head())["isFraud"]]


def stale_assign_head_if_stale():
    return [round(float(v), 6) for v in _pandas.read_csv(P_SUB).head()["isFraud"]]


check("stale_assign_head", stale_assign_head)
check("stale_assign_head_if_stale", stale_assign_head_if_stale)

KINGS = ["Joffrey Baratheon", "Robb Stark", "Balon Greyjoy", "Stannis Baratheon"]
P_BATTLES = write("battles", "name,attacker_king,defender_king,attacker_outcome,battle_type\n" + "\n".join(
    "Battle %d,%s,%s,%s,%s" % (i, KINGS[i % 4], KINGS[(i + 1) % 4], ["win", "loss"][(i // 3) % 2],
                               ["pitched battle", "siege", "ambush"][i % 3]) for i in range(38)) + "\n")


def battles_after_at(mod):
    b = mod.read_csv(P_BATTLES)
    b.at[27, "attacker_king"] = "Mance Rayder"
    b.at[27, "defender_king"] = "Stannis Baratheon"
    b.head(5)
    return b


def table(o):
    o = plain(o)
    if isinstance(o, _pandas.DataFrame):
        return sorted((str(r), str(c), None if miss(v) else int(v)) for r, row in o.iterrows() for c, v in row.items())
    return sorted((str(k), int(v)) for k, v in o.items())


check("stale_at_groupby", lambda: table(battles_after_at(pd).groupby(["attacker_king", "defender_king"]).count()["name"]))
check("stale_at_groupby_unstack", lambda: table(
    battles_after_at(pd).groupby(["attacker_king", "attacker_outcome"]).count()["name"].unstack()))
def stale_at_filter(mod=None):
    b = battles_after_at(pd) if mod is None else mod.read_csv(P_BATTLES)
    return sorted(map(str, plain(b[b["attacker_outcome"] == "loss"])["attacker_king"]))   # c8's last expression


check("stale_at_filter", stale_at_filter)
check("stale_at_groupby_if_stale", lambda: table(_pandas.read_csv(P_BATTLES).groupby(["attacker_king", "defender_king"]).count()["name"]))
check("stale_at_groupby_unstack_if_stale", lambda: table(
    _pandas.read_csv(P_BATTLES).groupby(["attacker_king", "attacker_outcome"]).count()["name"].unstack()))
check("stale_at_filter_if_stale", lambda: stale_at_filter(_pandas))

# --- a Boolean filter's index used to drop rows (Bodo) ---------------------------------------------------------------
P_VG = write("vgsales", "Rank,Name,Year\n" + "\n".join("%d,game %d,%d" % (i + 1, i, 1996 + (i * 7) % 24) for i in range(120)) + "\n")


def filter_index_drop():
    data = pd.read_csv(P_VG)
    data.head()
    drop_row_index = data[data["Year"] > 2015].index
    data = data.drop(drop_row_index)
    p = plain(data)
    return "rows=%d max_year=%d first_ranks=%s" % (len(p), int(p["Year"].max()), list(map(int, p["Rank"][:6])))


check("filter_index_drop", filter_index_drop)

# --- unique() and nunique() with missing values (FireDucks) -----------------------------------------------------------
P_CLANS = write("clans", "clan_location,members,war_frequency\n" + "\n".join(
    "%s,%d,%s" % (["Spain", "", "India", "Spain", "", "Brazil"][i % 6], i % 9, ["always", "", "never"][i % 3])
    for i in range(60)) + "\n")


def clans():
    return pd.read_csv(P_CLANS)


check("unique_with_missing", lambda: sorted("MISSING" if miss(v) else str(v) for v in list(plain(clans()["clan_location"].unique()))))
check("nunique_column", lambda: int(clans()["clan_location"].nunique()))
check("nunique_loop_over_columns", lambda: [int(clans()[c].nunique()) for c in clans().columns])
check("nunique_select_dtypes_apply", lambda: sorted((str(k), int(v)) for k, v in plain(
    clans().select_dtypes("object").apply(pd.Series.nunique, axis=0)).items()))
check("value_counts_with_missing", lambda: sorted((str(k), int(v)) for k, v in plain(clans()["clan_location"].value_counts()).items()))
