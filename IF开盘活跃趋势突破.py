# -*- coding: utf-8 -*-
"""IF opening activity trend breakout strategy for DQT."""

import datetime

import numpy as np
import pandas as pd
from dqtrader import *


TARGET_LIST = ["CFFEX.IF0000"]

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
        "name": "IF开盘活跃趋势突破_动态仓位止损",
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

    context.current_date = None
    context.open_high = None
    context.open_low = None
    context.is_active_open = False
    context.today_position_pct = 0.0
    context.trade_count = 0
    context.position_side = 0


def _reset_daily_state(context, today):
    context.current_date = today
    context.open_high = None
    context.open_low = None
    context.is_active_open = False
    context.today_position_pct = 0.0
    context.trade_count = 0
    context.position_side = 0


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

    data = data[data["target_index"] == 0].copy()
    if len(data) == 0:
        return None

    data["time"] = pd.to_datetime(data["time"])
    data["date"] = data["time"].dt.strftime("%Y-%m-%d")
    return data.sort_values("time")


def _calculate_open_state(context, data, today):
    today_data = data[data["date"] == today]
    if len(today_data) < context.open_bars:
        return False

    open_data = today_data.iloc[:context.open_bars]
    required_columns = ["high", "low", "close", "total_turnover"]
    if open_data[required_columns].isna().any().any():
        return False

    hist = data[data["date"] < today]
    hist_open_amounts = []
    for _, group in hist.groupby("date"):
        group = group.sort_values("time")
        if len(group) >= context.open_bars:
            hist_open_amounts.append(group.iloc[:context.open_bars]["total_turnover"].sum())

    if len(hist_open_amounts) < 5:
        return False

    today_open_amount = open_data["total_turnover"].sum()
    avg_open_amount = np.mean(hist_open_amounts[-context.lookback_days:])
    amount_ratio = today_open_amount / avg_open_amount if avg_open_amount > 0 else 0.0

    context.open_high = open_data["high"].max()
    context.open_low = open_data["low"].min()
    open_range = context.open_high / context.open_low - 1

    context.is_active_open = (
        amount_ratio >= context.amount_ratio_threshold
        and open_range >= context.range_threshold
    )

    if amount_ratio >= 1.8 and open_range >= 0.004:
        context.today_position_pct = 1.0
    elif amount_ratio >= 1.3 and open_range >= 0.003:
        context.today_position_pct = 0.8
    else:
        context.today_position_pct = 0.5

    print(
        today,
        "开盘活跃:",
        context.is_active_open,
        "成交额倍数:",
        round(amount_ratio, 2),
        "开盘振幅:",
        round(open_range, 4),
        "动态仓位:",
        context.today_position_pct,
        "区间高点:",
        context.open_high,
        "区间低点:",
        context.open_low,
    )
    return True


def _close_position(context, today, side, reason, price):
    order_target_percent(
        target_index=0,
        target_percent=0,
        side=side,
        order_type=OrderType.MARKET,
        price=0,
    )
    context.position_side = 0
    print(today, reason, "价格:", price)


def on_bar(context):
    now = context.now
    today = now.strftime("%Y-%m-%d")
    current_time = now.strftime("%H:%M")

    if context.current_date != today:
        _reset_daily_state(context, today)

    data = _get_history_data(context)
    if data is None:
        return

    today_data = data[data["date"] == today]
    if len(today_data) < context.open_bars:
        return

    if context.open_high is None:
        _calculate_open_state(context, data, today)
        return

    price = float(today_data.iloc[-1]["close"])

    if context.position_side == 1 and price < context.open_high * (1 - context.stop_loss_pct):
        _close_position(context, today, PositionSide.LONG, "多头止损", price)
        return

    if context.position_side == -1 and price > context.open_low * (1 + context.stop_loss_pct):
        _close_position(context, today, PositionSide.SHORT, "空头止损", price)
        return

    if current_time >= "14:55":
        if context.position_side == 1:
            _close_position(context, today, PositionSide.LONG, "收盘前平多", price)
        elif context.position_side == -1:
            _close_position(context, today, PositionSide.SHORT, "收盘前平空", price)
        return

    if (
        not context.is_active_open
        or context.trade_count >= context.max_trade_count
        or context.position_side != 0
    ):
        return

    if price > context.open_high:
        order_target_percent(
            target_index=0,
            target_percent=context.today_position_pct,
            side=PositionSide.LONG,
            order_type=OrderType.MARKET,
            price=0,
        )
        context.position_side = 1
        context.trade_count += 1
        print(today, "向上突破，做多 IF，价格:", price, "仓位:", context.today_position_pct)

    elif price < context.open_low:
        order_target_percent(
            target_index=0,
            target_percent=context.today_position_pct,
            side=PositionSide.SHORT,
            order_type=OrderType.MARKET,
            price=0,
        )
        context.position_side = -1
        context.trade_count += 1
        print(today, "向下突破，做空 IF，价格:", price, "仓位:", context.today_position_pct)


if __name__ == "__main__":
    run_backtest(config=config, init=init, on_bar=on_bar)