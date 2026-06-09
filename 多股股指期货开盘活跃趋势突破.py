# -*- coding: utf-8 -*-
"""Multi-index futures opening activity trend breakout strategy for DQT."""

import numpy as np
import pandas as pd
from dqtrader import *


TARGET_LIST = [
    "CFFEX.IF0000",  # 沪深300股指期货主连
    "CFFEX.IC0000",  # 中证500股指期货主连
    "CFFEX.IH0000",  # 上证50股指期货主连
    "CFFEX.IM0000",  # 中证1000股指期货主连
]

INITIAL_CASH = 10_000_000
BEGIN_DATE = "2023-01-01"
END_DATE = "2026-06-07"

OPEN_BARS = 6
LOOKBACK_DAYS = 20
BARS_PER_DAY = 48
AMOUNT_RATIO_THRESHOLD = 1.1
RANGE_THRESHOLD = 0.002
STOP_LOSS_PCT = 0.01
MAX_TRADE_COUNT = 5

BASE_TARGET_WEIGHT = 1.0 / len(TARGET_LIST)


config = {
    "account": {
        "initial_cash": INITIAL_CASH,
        "future_cost_fee": 1,
        "stock_cost_fee": 2.5,
        "rate": 0.02,
        "margin_rate": 1,
        "slide_price": 1,
        "price_loc": 1,
        "deal_type": 0,
        "limit_type": 0,
    },
    "strategy": {
        "name": "多股指期货开盘活跃趋势突破_动态仓位止损",
        "target_list": TARGET_LIST,
        "frequency": "min",
        "fre_num": 5,
        "begin_date": BEGIN_DATE,
        "end_date": END_DATE,
        "fq": FQType.NA,
        "benchmark": "sse.000300",
    },
}


def init(context):
    reg_kdata("min", 5)

    context.open_bars = OPEN_BARS
    context.lookback_days = LOOKBACK_DAYS
    context.bars_per_day = BARS_PER_DAY
    context.amount_ratio_threshold = AMOUNT_RATIO_THRESHOLD
    context.range_threshold = RANGE_THRESHOLD
    context.stop_loss_pct = STOP_LOSS_PCT
    context.max_trade_count = MAX_TRADE_COUNT
    context.base_target_weight = BASE_TARGET_WEIGHT

    context.current_date = None
    context.state = {}

    for i, code in enumerate(TARGET_LIST):
        context.state[i] = {
            "code": code,
            "open_high": None,
            "open_low": None,
            "is_active_open": False,
            "today_position_pct": 0.0,
            "trade_count": 0,
            "position_side": 0,
        }


def _reset_daily_state(context, today):
    context.current_date = today
    for i, code in enumerate(TARGET_LIST):
        context.state[i] = {
            "code": code,
            "open_high": None,
            "open_low": None,
            "is_active_open": False,
            "today_position_pct": 0.0,
            "trade_count": 0,
            "position_side": 0,
        }


def _get_history_data(context):
    data = get_reg_kdata(
        reg_idx=0,
        target_list=[],
        length=(context.lookback_days + 2) * context.bars_per_day,
        fill_up=True,
        df=True,
    )

    if data is None or len(data) == 0:
        return None

    data = data.copy()
    data["time"] = pd.to_datetime(data["time"])
    data["date"] = data["time"].dt.strftime("%Y-%m-%d")
    return data.sort_values(["target_index", "time"])


def _calculate_open_state(context, target_index, target_data, today):
    state = context.state[target_index]

    today_data = target_data[target_data["date"] == today]
    if len(today_data) < context.open_bars:
        return False

    open_data = today_data.iloc[:context.open_bars]
    required_columns = ["high", "low", "close", "total_turnover"]

    if open_data[required_columns].isna().any().any():
        return False

    hist = target_data[target_data["date"] < today]
    hist_open_amounts = []

    for _, group in hist.groupby("date"):
        group = group.sort_values("time")
        if len(group) >= context.open_bars:
            hist_open_amounts.append(
                group.iloc[:context.open_bars]["total_turnover"].sum()
            )

    if len(hist_open_amounts) < 5:
        return False

    today_open_amount = open_data["total_turnover"].sum()
    avg_open_amount = np.mean(hist_open_amounts[-context.lookback_days:])
    amount_ratio = today_open_amount / avg_open_amount if avg_open_amount > 0 else 0.0

    state["open_high"] = open_data["high"].max()
    state["open_low"] = open_data["low"].min()
    open_range = state["open_high"] / state["open_low"] - 1

    state["is_active_open"] = (
        amount_ratio >= context.amount_ratio_threshold
        and open_range >= context.range_threshold
    )

    if amount_ratio >= 1.8 and open_range >= 0.004:
        raw_position_pct = 1.0
    elif amount_ratio >= 1.3 and open_range >= 0.003:
        raw_position_pct = 0.8
    else:
        raw_position_pct = 0.5

    state["today_position_pct"] = raw_position_pct * context.base_target_weight

    print(
        today,
        state["code"],
        "开盘活跃:",
        state["is_active_open"],
        "成交额倍数:",
        round(amount_ratio, 2),
        "开盘振幅:",
        round(open_range, 4),
        "动态仓位:",
        round(state["today_position_pct"], 4),
        "区间高点:",
        state["open_high"],
        "区间低点:",
        state["open_low"],
    )

    return True


def _close_position(context, target_index, today, side, reason, price):
    state = context.state[target_index]

    order_target_percent(
        target_index=target_index,
        target_percent=0,
        side=side,
        order_type=OrderType.MARKET,
        price=0,
    )

    state["position_side"] = 0
    print(today, state["code"], reason, "价格:", price)


def _process_target(context, target_index, target_data, today, current_time):
    state = context.state[target_index]

    today_data = target_data[target_data["date"] == today]
    if len(today_data) < context.open_bars:
        return

    if state["open_high"] is None:
        _calculate_open_state(context, target_index, target_data, today)
        return

    price = float(today_data.iloc[-1]["close"])

    if state["position_side"] == 1 and price < state["open_high"] * (1 - context.stop_loss_pct):
        _close_position(context, target_index, today, PositionSide.LONG, "多头止损", price)
        return

    if state["position_side"] == -1 and price > state["open_low"] * (1 + context.stop_loss_pct):
        _close_position(context, target_index, today, PositionSide.SHORT, "空头止损", price)
        return

    if current_time >= "14:55":
        if state["position_side"] == 1:
            _close_position(context, target_index, today, PositionSide.LONG, "收盘前平多", price)
        elif state["position_side"] == -1:
            _close_position(context, target_index, today, PositionSide.SHORT, "收盘前平空", price)
        return

    if (
        not state["is_active_open"]
        or state["trade_count"] >= context.max_trade_count
        or state["position_side"] != 0
    ):
        return

    if price > state["open_high"]:
        order_target_percent(
            target_index=target_index,
            target_percent=state["today_position_pct"],
            side=PositionSide.LONG,
            order_type=OrderType.MARKET,
            price=0,
        )

        state["position_side"] = 1
        state["trade_count"] += 1

        print(
            today,
            state["code"],
            "向上突破，做多，价格:",
            price,
            "仓位:",
            round(state["today_position_pct"], 4),
        )

    elif price < state["open_low"]:
        order_target_percent(
            target_index=target_index,
            target_percent=state["today_position_pct"],
            side=PositionSide.SHORT,
            order_type=OrderType.MARKET,
            price=0,
        )

        state["position_side"] = -1
        state["trade_count"] += 1

        print(
            today,
            state["code"],
            "向下突破，做空，价格:",
            price,
            "仓位:",
            round(state["today_position_pct"], 4),
        )


def on_bar(context):
    now = context.now
    today = now.strftime("%Y-%m-%d")
    current_time = now.strftime("%H:%M")

    if context.current_date != today:
        _reset_daily_state(context, today)

    data = _get_history_data(context)
    if data is None:
        return

    for target_index in range(len(TARGET_LIST)):
        target_data = data[data["target_index"] == target_index].copy()
        if len(target_data) == 0:
            continue

        _process_target(context, target_index, target_data, today, current_time)


if __name__ == "__main__":
    run_backtest(config=config, init=init, on_bar=on_bar)
