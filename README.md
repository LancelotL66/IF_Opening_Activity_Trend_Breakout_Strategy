# IF 开盘活跃趋势突破策略

这是一个基于 DQT Python Toolbox (`dqtrader`) 的股指期货日内趋势突破策略。

策略交易标的是中金所沪深 300 股指期货主力连续合约 `CFFEX.IF0000`。策略在每日开盘后的前 6 根 5 分钟 K 线内判断市场活跃度，如果开盘成交额和开盘振幅均达到阈值，则将当天标记为“活跃开盘日”。随后价格向上突破开盘区间高点时做多，向下跌破开盘区间低点时做空，并根据开盘活跃程度动态调整仓位。策略包含固定止损和尾盘平仓逻辑。

最终实现了：**16.82%** 的年化收益率，**2.57** 的夏普比率，**2.5%** 的最大回撤，**589.09%** 的换手率， $\alpha$ 值为 **0.13**， $\beta$ 值为 **0.06**。

## 文件说明

| 文件 | 说明 |
| --- | --- |
| `IF开盘活跃趋势突破.py` | DQT 策略源码 |
| `策略绩效报告-IF开盘活跃趋势突破_动态仓位止损.pdf` | DQT 导出的策略绩效报告 |

## 运行环境

- Windows x64
- Python 3.9+
- DQT 客户端已打开并正常登录
- Python 包：
  - `dqtrader`
  - `numpy`
  - `pandas`

安装依赖示例：

```powershell
pip install dqtrader numpy pandas
```

如果使用 Conda，建议创建专用环境：

```powershell
conda create -n dqt python=3.12 pip -y
conda activate dqt
pip install dqtrader numpy pandas
```

## 策略参数

主要参数位于脚本顶部：

```python
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
```

| 参数 | 说明 |
| --- | --- |
| `TARGET_LIST` | 交易标的，默认 IF 主力连续 |
| `OPEN_BARS` | 开盘区间 K 线数量，5 分钟频率下 6 根约为 30 分钟 |
| `LOOKBACK_DAYS` | 计算历史开盘成交额均值的回看天数 |
| `BARS_PER_DAY` | 每日 5 分钟 K 线数量估计值 |
| `AMOUNT_RATIO_THRESHOLD` | 当日开盘成交额相对历史均值的活跃阈值 |
| `RANGE_THRESHOLD` | 开盘区间振幅阈值 |
| `STOP_LOSS_PCT` | 固定止损比例 |
| `MAX_TRADE_COUNT` | 单日最大开仓次数 |

## 策略逻辑

1. 注册 IF 主力连续合约的 5 分钟 K 线。
2. 每个交易日重置日内状态。
3. 取当天开盘后的前 `OPEN_BARS` 根 K 线，计算：
   - 开盘区间高点
   - 开盘区间低点
   - 开盘区间振幅
   - 开盘成交额
4. 用过去 `LOOKBACK_DAYS` 个交易日的开盘成交额均值作为基准。
5. 当以下条件同时满足时，认定为活跃开盘：

```text
开盘成交额 / 历史开盘成交额均值 >= AMOUNT_RATIO_THRESHOLD
开盘区间振幅 >= RANGE_THRESHOLD
```

6. 根据活跃强度动态设定仓位：

| 条件 | 仓位 |
| --- | --- |
| 成交额倍数 >= 1.8 且振幅 >= 0.004 | 100% |
| 成交额倍数 >= 1.3 且振幅 >= 0.003 | 80% |
| 其他活跃开盘 | 50% |

7. 入场规则：
   - 当前价格突破开盘区间高点：做多
   - 当前价格跌破开盘区间低点：做空
8. 风控规则：
   - 多头价格跌破 `开盘高点 * (1 - STOP_LOSS_PCT)` 止损
   - 空头价格突破 `开盘低点 * (1 + STOP_LOSS_PCT)` 止损
   - 14:55 之后尾盘平仓

## 运行方式

确保 DQT 客户端已打开并登录，然后在策略目录运行：

```powershell
python .\IF开盘活跃趋势突破.py
```

或使用指定解释器：

```powershell
D:\anaconda\envs\dqt\python.exe .\IF开盘活跃趋势突破.py
```

## 注意事项

- 本策略依赖 DQT 客户端权限，离线状态下无法正常获取行情或运行回测。
- 交易标的是 `CFFEX.IF0000` 主力连续合约，实盘前需要确认合约映射、保证金和交易权限。
- 当前使用 5 分钟 K 线，`BARS_PER_DAY = 48` 是按日内可用 K 线数量估算，用于控制历史数据窗口长度。
- 该策略为日内策略，尾盘会尝试平仓，不设计隔夜持仓。
- 策略没有额外处理涨跌停、滑点扩张、成交失败、盘口流动性等实盘细节。
- 代码文件包含中文，建议使用 UTF-8 编码打开和提交。

## 免责声明

本项目仅用于量化策略研究和教学示例，不构成任何投资建议。历史回测结果不代表未来收益，期货交易具有高杠杆风险。
