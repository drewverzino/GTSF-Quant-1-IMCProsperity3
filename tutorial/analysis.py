import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# ------------------------------------------------------------------
# 1.  Load the CSV
# ------------------------------------------------------------------
df = pd.read_csv("08bc5cea-bcf7-47e5-a230-d0d9b24bb372.csv", sep=";")

# quick peek
print(df.head())

# parse timestamps to minutes for nicer x‑axis (if timestamp is ms)
df["minute"] = df["timestamp"] // 60000

# ------------------------------------------------------------------
# 2.  Mid‑price time‑series
# ------------------------------------------------------------------
plt.figure(figsize=(12, 4))
for prod, color in zip(["RAINFOREST_RESIN", "KELP"], ["tab:blue", "tab:green"]):
    subset = df[df["product"] == prod]
    plt.plot(subset["minute"], subset["mid_price"], label=prod, color=color)
plt.title("Mid‑price evolution")
plt.xlabel("Minute")
plt.ylabel("Mid price (SeaShells)")
plt.legend()
plt.tight_layout()
plt.show()

# ------------------------------------------------------------------
# 3.  Cumulative PnL
# ------------------------------------------------------------------
if "profit_and_loss" in df.columns:
    pnl = df.groupby("minute")["profit_and_loss"].first()
    plt.figure(figsize=(10, 3))
    pnl.plot()
    plt.title("Cumulative PnL")
    plt.xlabel("Minute")
    plt.ylabel("SeaShells")
    plt.tight_layout()
    plt.show()
else:
    print("PnL column not present – skip plot.")

# ------------------------------------------------------------------
# 4.  Kelp distribution
# ------------------------------------------------------------------
kelp_mid = df[df["product"] == "KELP"]["mid_price"]
plt.figure(figsize=(6, 4))
sns.histplot(kelp_mid, kde=True, bins=50, color="tab:green")
plt.title("KELP mid‑price distribution")
plt.xlabel("Mid price (SeaShells)")
plt.tight_layout()
plt.show()

# ------------------------------------------------------------------
# 5.  Order‑book depth histograms
# ------------------------------------------------------------------

# helper to collect all price / volume columns into long form
price_cols = [c for c in df.columns if "price_" in c]
volume_cols = [c for c in df.columns if "volume_" in c]

long = pd.DataFrame({
    "product":   np.repeat(df["product"].values, len(price_cols)),
    "side":      ["bid" if "bid" in c else "ask" for c in price_cols] * len(df),
    "level":     [c.split("_")[-1] for c in price_cols] * len(df),
    "price":     df[price_cols].values.ravel(),
    "volume":    df[volume_cols].values.ravel()
})

# drop empty rows (NaNs)
long = long.dropna(subset=["price", "volume"])

# ------- A) price distribution by side ---------------------------
plt.figure(figsize=(10, 4))
sns.histplot(data=long, x="price", hue="side", element="step", stat="count",
             bins=60, palette={"bid": "tab:blue", "ask": "tab:orange"})
plt.title("Histogram of quoted prices (all levels, all ticks)")
plt.xlabel("Price (SeaShells)")
plt.tight_layout()
plt.show()

# ------- B) volume distribution by level -------------------------
plt.figure(figsize=(10, 4))
sns.histplot(data=long, x="volume", hue="level", element="step", stat="count",
             bins=40, palette="Set2")
plt.title("Histogram of quoted volumes by level")
plt.xlabel("Absolute volume at that level")
plt.tight_layout()
plt.show()
