import concurrent.futures
import itertools
import sys
from importlib import import_module, reload
from pathlib import Path

import numpy as np

current_dir = Path(__file__).resolve().parent

backtester_path = current_dir / "imc-prosperity-3-backtester-0.5.0"
sys.path.append(str(backtester_path))
from prosperity3bt.file_reader import PackageResourcesReader
from prosperity3bt.models import TradeMatchingMode
from prosperity3bt.runner import run_backtest


def load_trader_class(algo_path: Path):
    # Make sure we can import the file as a module.
    sys.path.append(str(algo_path.parent))
    module = import_module(algo_path.stem)
    if not hasattr(module, "Trader"):
        raise ValueError(f"{algo_path} does not define a Trader class")
    return module.Trader


def profit_of(result):
    # Assume the "profit" is computed as the sum of the last timestamp’s profit
    last_ts = result.activity_logs[-1].timestamp
    return sum(
        row.columns[-1] for row in result.activity_logs if row.timestamp == last_ts
    )


def evaluate(trader_cls, params, file_reader, rounds, days):
    # Instantiate a new trader with the given parameters.
    trader = trader_cls(**params)
    total = 0.0
    for r, d in itertools.product(rounds, days):
        result = run_backtest(
            trader,
            file_reader,
            r,
            d,
            False,  # print_output (this spams a lot!)
            TradeMatchingMode.all,  # match_trades mode
            True,  # enforce_limits
            False,  # show_progress
        )
        total += profit_of(result)
        reload(sys.modules[trader.__module__])
    return total


def worker(args):
    algo_path, params, rounds, days = args
    # Reload the Trader for each process.
    Trader = load_trader_class(Path(algo_path))
    file_reader = PackageResourcesReader()
    score = evaluate(Trader, params, file_reader, rounds, days)
    return params, score


def main():
    # Provide the path to the algorithm file you want to test (with your modified Trader.__init__).
    algo_path = "/Users/danieldixon/Documents/IMC Prosperity/GTSF-Quant-1-IMCProsperity3/my_test.py"

    # You should specify the parameters HERE
    alphas = np.linspace(0.01, 1, num=5)
    windows = np.linspace(1, 50, num=5, dtype=int)
    inv_skews = np.linspace(0.01, 0.25, num=5)

    rounds = [0]
    days = [-1]

    # Build a list of parameter combinations as a list of tuples for the worker function.
    tasks = []
    # make sure to UDPATE THIS WITH THE CORRECT PARAMETERS
    for alpha, window, inv in itertools.product(alphas, windows, inv_skews):
        params = {"alpha": alpha, "vol_window": window, "inv_skew": inv}
        tasks.append((algo_path, params, rounds, days))

    # run evaluations in parallel.
    best = {"score": -float("inf"), "params": None}
    with concurrent.futures.ProcessPoolExecutor() as executor:
        results = executor.map(worker, tasks)

    for params, score in results:
        print(f"Tested {params!r} => profit = {score:,.0f}")
        if score > best["score"]:
            best["score"] = score
            best["params"] = params

    print("\nBest params:", best["params"], "=> profit:", best["score"])


if __name__ == "__main__":
    main()
