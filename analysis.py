"""
股票多方法分析模块 —— 输入 OHLC 日线数据，输出指标 + 结论 + 图表数据（纯量化模板文字）。
4 种方法：technical(技术分析) / momentum(动量&风险) / multifactor(多因子·横截面) / capm(CAPM)
所有结论均为模板文字，不依赖任何外部大模型。

相比初版的关键升级：
- 多因子改为"跨标横截面 z-score 因子画像"：在标的池(本 Demo 为 5 只美股)内对 4 个价格因子
  做标准化，得到所选股票相对同业的因子暴露，不再是单只股票硬凑得分。
- 每种方法额外返回 `extra` 图表数据（MACD 序列 / 动量柱 / 因子条 / CAPM 散点与回归线），供前端绘图。
"""
import numpy as np
import pandas as pd

RF_ANNUAL = 0.02  # 无风险利率（年化），用于夏普 / CAPM alpha

FACTOR_NAMES = ['动量因子(12M)', '低波因子(1/波动)', '短期反转因子(1M)', '趋势质量因子(60D)']


# ---------- 工具 ----------
def _ensure_df(df):
    df = df.copy()
    for c in ['open', 'high', 'low', 'close', 'volume']:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df = df.sort_values('date')
    return df.dropna(subset=['close']).reset_index(drop=True)


def _daily_returns(df):
    return df['close'].pct_change().dropna()


def _safe_div(a, b):
    return a / b if (b not in (0, None) and not np.isnan(b)) else 0.0


# ---------- 单只股票的 4 个价格因子原始值 ----------
def _stock_factors(df):
    df = _ensure_df(df)
    c = df['close']
    n = len(c)
    i = -1
    rets = _daily_returns(df)
    f_mom = (c.iloc[i] / c.iloc[i - 252] - 1) if n > 252 else (c.iloc[i] / c.iloc[0] - 1)
    f_invvol = _safe_div(1.0, float(rets.std() * np.sqrt(252)))
    f_shortrev = -(c.iloc[i] / c.iloc[i - 21] - 1) if n > 21 else 0.0
    f_trend = ((c.iloc[i] - c.iloc[i - 60]) / c.iloc[i - 60]) if n > 60 else 0.0
    return {
        '动量因子(12M)': float(f_mom),
        '低波因子(1/波动)': float(f_invvol),
        '短期反转因子(1M)': float(f_shortrev),
        '趋势质量因子(60D)': float(f_trend),
    }


def compute_universe_factors(dict_of_dfs):
    """对标的池逐只计算 4 因子原始值，返回 {ticker: {factor: raw}}。"""
    out = {}
    for tk, df in dict_of_dfs.items():
        try:
            out[tk] = _stock_factors(df)
        except Exception:
            continue
    return out


# ---------- 方法1：技术分析 ----------
def analyze_technical(df):
    df = _ensure_df(df)
    c = df['close']
    n = len(c)
    ma5 = c.rolling(5).mean()
    ma10 = c.rolling(10).mean()
    ma20 = c.rolling(20).mean()
    i = -1
    bull = bool((ma5.iloc[i] > ma10.iloc[i] > ma20.iloc[i]) and (c.iloc[i] >= ma5.iloc[i]))
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    macd = (dif - dea) * 2
    macd_up = bool(macd.iloc[i] > 0)
    trend = '上升' if c.iloc[i] > ma20.iloc[i] else '下降'
    if bull and macd_up:
        signal = '看多'
    elif (not bull) and (not macd_up):
        signal = '看空'
    else:
        signal = '中性'
    indicators = {
        '最新价': round(float(c.iloc[i]), 2),
        'MA5': round(float(ma5.iloc[i]), 2),
        'MA10': round(float(ma10.iloc[i]), 2),
        'MA20': round(float(ma20.iloc[i]), 2),
        'MACD': round(float(macd.iloc[i]), 3),
        '多头排列': '是' if bull else '否',
        '趋势(相对MA20)': trend,
    }
    conclusion = (f"最新价 {c.iloc[i]:.2f}，MA5/MA10/MA20"
                  f"{'呈多头排列' if bull else '未呈多头排列'}，MACD"
                  f"{'在零轴上方(动能为正)' if macd_up else '在零轴下方(动能为负)'}，"
                  f"技术面整体 {signal}。")
    # 图表数据：完整 MACD 序列（前 34 根为空）
    macd_list = [None if pd.isna(x) else round(float(x), 3) for x in macd]
    return {'method': 'technical', 'name': '技术分析', 'signal': signal,
            'indicators': indicators, 'conclusion': conclusion,
            'extra': {'macd': macd_list}}


# ---------- 方法2：动量 & 风险 ----------
def analyze_momentum_risk(df):
    df = _ensure_df(df)
    c = df['close']
    n = len(c)
    i = -1
    rets = _daily_returns(df)
    mom12 = (c.iloc[i] / c.iloc[i - 252] - 1) if n > 252 else (c.iloc[i] / c.iloc[0] - 1)
    mom3 = (c.iloc[i] / c.iloc[i - 63] - 1) if n > 63 else mom12
    mom1 = (c.iloc[i] / c.iloc[i - 21] - 1) if n > 21 else mom12
    vol_ann = float(rets.std() * np.sqrt(252))
    cummax = c.cummax()
    dd = (c - cummax) / cummax
    max_dd = float(dd.min())
    ann_ret = (c.iloc[i] / c.iloc[0]) ** (252.0 / n) - 1 if n > 1 else 0.0
    sharpe = _safe_div(ann_ret - RF_ANNUAL, vol_ann)
    if mom12 > 0.20 and vol_ann < 0.40:
        signal = '看多'
    elif mom12 < -0.20 or vol_ann > 0.60:
        signal = '看空'
    else:
        signal = '中性'
    indicators = {
        '近1年动量': f"{mom12*100:.1f}%",
        '近3月动量': f"{mom3*100:.1f}%",
        '近1月动量': f"{mom1*100:.1f}%",
        '年化波动率': f"{vol_ann*100:.1f}%",
        '最大回撤': f"{max_dd*100:.1f}%",
        '年化夏普': round(sharpe, 2),
    }
    conclusion = (f"近一年动量 {mom12*100:.1f}%，年化波动率 {vol_ann*100:.1f}%，"
                  f"期间最大回撤 {max_dd*100:.1f}%，夏普 {sharpe:.2f}。"
                  f"动量{'强劲' if mom12>0.2 else ('疲弱' if mom12<-0.2 else '中性')}，"
                  f"风险{'偏高' if vol_ann>0.5 else '可控'}，整体 {signal}。")
    return {'method': 'momentum', 'name': '动量&风险', 'signal': signal,
            'indicators': indicators, 'conclusion': conclusion,
            'extra': {'mom_bars': {'1月': round(mom1*100, 2), '3月': round(mom3*100, 2),
                                  '12月': round(mom12*100, 2)}}}


# ---------- 方法3：多因子（横截面 z-score 因子画像） ----------
def analyze_multifactor(df, ticker=None, universe_factors=None):
    df = _ensure_df(df)
    raw = _stock_factors(df)
    if universe_factors and len(universe_factors) >= 2 and ticker in universe_factors:
        # 逐因子在标的池内标准化
        mu = {}; sd = {}
        for f in FACTOR_NAMES:
            arr = np.array([universe_factors[t][f] for t in universe_factors], dtype=float)
            mu[f] = float(arr.mean()); sd[f] = float(arr.std())
        z = {}
        for f in FACTOR_NAMES:
            z[f] = (raw[f] - mu[f]) / sd[f] if sd[f] > 0 else 0.0
        # 各标的综合 z（用于排名）
        comp = {}
        for t in universe_factors:
            zs = [(universe_factors[t][f] - mu[f]) / sd[f] if sd[f] > 0 else 0.0 for f in FACTOR_NAMES]
            comp[t] = float(np.mean(zs))
        ranked = sorted(comp.keys(), key=lambda x: -comp[x])
        rank = ranked.index(ticker) + 1
        score_raw = float(np.mean([z[f] for f in FACTOR_NAMES]))
        score = max(0.0, min(100.0, 50.0 + 20.0 * score_raw))
        signal = '看多' if score >= 60 else ('看空' if score <= 40 else '中性')
        indicators = {
            '动量因子暴露(z)': round(z['动量因子(12M)'], 2),
            '低波因子暴露(z)': round(z['低波因子(1/波动)'], 2),
            '反转因子暴露(z)': round(z['短期反转因子(1M)'], 2),
            '趋势因子暴露(z)': round(z['趋势质量因子(60D)'], 2),
            '综合因子得分(0-100)': round(score, 1),
            f'同业排名': f"{rank} / {len(universe_factors)}",
        }
        conclusion = (f"在 {len(universe_factors)} 只标的池中，{ticker} 的四因子综合 z 得分为 "
                      f"{score_raw:.2f}，综合因子得分 {score:.1f}/100，同业排名第 {rank}。"
                      f"因子暴露以{'正向(优于同业)' if score_raw>0 else '负向(弱于同业)'}为主，整体 {signal}。")
        return {'method': 'multifactor', 'name': '多因子模型', 'signal': signal,
                'indicators': indicators, 'conclusion': conclusion,
                'extra': {'factors_z': {f: round(z[f], 2) for f in FACTOR_NAMES},
                          'score': round(score, 1), 'rank': rank,
                          'universe_size': len(universe_factors)}}
    # 兜底：单只股票无法横截面时，回到保守的相对0轴映射
    score = 50.0
    for v in raw.values():
        score += float(np.sign(v)) * min(abs(v) * 100, 50) / 4.0
    score = max(0.0, min(100.0, score))
    signal = '看多' if score >= 60 else ('看空' if score <= 40 else '中性')
    indicators = {k: round(float(v), 4) for k, v in raw.items()}
    indicators['综合因子得分(0-100)'] = round(score, 1)
    conclusion = (f"四个价格因子(动量、低波、短期反转、趋势质量)等权合成，"
                  f"综合得分 {score:.1f}/100，信号 {signal}（单只模式，仅供参考）。")
    return {'method': 'multifactor', 'name': '多因子模型', 'signal': signal,
            'indicators': indicators, 'conclusion': conclusion,
            'extra': {'factors_z': {k: 0.0 for k in FACTOR_NAMES}, 'score': round(score, 1),
                      'rank': 1, 'universe_size': 1}}


# ---------- 方法4：CAPM ----------
def analyze_capm(df, market_df=None):
    df = _ensure_df(df)
    c = df['close']
    stock_ret = _daily_returns(df)
    if market_df is not None and len(market_df) > 1:
        m = _ensure_df(market_df)
        if 'date' in df.columns and 'date' in m.columns:
            s = df[['date', 'close']].rename(columns={'close': 's'})
            mm = m[['date', 'close']].rename(columns={'close': 'm'})
            j = pd.merge(s, mm, on='date').dropna()
            stock_ret = j['s'].pct_change().dropna()
            market_ret = j['m'].pct_change().dropna()
        else:
            market_ret = _daily_returns(m)
            k = min(len(stock_ret), len(market_ret))
            stock_ret = stock_ret.iloc[-k:]
            market_ret = market_ret.iloc[-k:]
    else:
        market_ret = stock_ret * 0.0
    stock_ret = stock_ret.astype(float)
    market_ret = market_ret.astype(float).reindex(stock_ret.index).fillna(0.0)
    k = min(len(stock_ret), len(market_ret))
    if k < 30:
        return {'method': 'capm', 'name': 'CAPM', 'signal': '中性',
                'indicators': {'备注': '数据不足，无法回归'},
                'conclusion': '样本不足，CAPM 暂不可用（需更长历史或市场基准数据）。',
                'extra': {}}
    sr = stock_ret.iloc[-k:]
    mr = market_ret.iloc[-k:]
    cov = np.cov(sr, mr)
    beta = _safe_div(cov[0, 1], cov[1, 1])
    ann_stock = sr.mean() * 252
    ann_mkt = mr.mean() * 252
    alpha = ann_stock - (RF_ANNUAL + beta * (ann_mkt - RF_ANNUAL))
    signal = '看多' if alpha > 0 and beta > 0 else ('看空' if alpha < 0 else '中性')
    indicators = {
        'Beta(β)': round(float(beta), 2),
        'Alpha(α,年化)': f"{alpha*100:.2f}%",
        '个股年化收益': f"{ann_stock*100:.2f}%",
        '市场年化收益': f"{ann_mkt*100:.2f}%",
    }
    conclusion = (f"β={beta:.2f}（{'进攻型>1' if beta>1 else ('防御型<1' if beta<1 else '中性')}），"
                  f"α={alpha*100:.2f}%（{'跑赢' if alpha>0 else '跑输'}大盘），"
                  f"CAPM 视角 {signal}。")
    # 图表数据：散点(市场收益,个股收益) + 回归线端点；下采样以控制体积
    step = max(1, k // 600)
    scatter = [[round(float(mr.iloc[j]), 5), round(float(sr.iloc[j]), 5)]
               for j in range(0, k, step)]
    m_min, m_max = float(mr.min()), float(mr.max())
    line = [[m_min, RF_ANNUAL + beta * (m_min - RF_ANNUAL)],
            [m_max, RF_ANNUAL + beta * (m_max - RF_ANNUAL)]]
    return {'method': 'capm', 'name': 'CAPM', 'signal': signal,
            'indicators': indicators, 'conclusion': conclusion,
            'extra': {'scatter': scatter, 'line': line, 'alpha': round(float(alpha), 4),
                      'beta': round(float(beta), 2)}}


# ---------- 调度 ----------
METHODS = {
    'technical': analyze_technical,
    'momentum': analyze_momentum_risk,
    'multifactor': analyze_multifactor,
    'capm': analyze_capm,
}


def run_analysis(method, stock_df, market_df=None, ticker=None, universe=None):
    fn = METHODS.get(method)
    if not fn:
        raise ValueError(f"未知方法: {method}")
    if method == 'capm':
        return fn(stock_df, market_df)
    if method == 'multifactor':
        return fn(stock_df, ticker=ticker, universe_factors=universe)
    return fn(stock_df)


def run_all(stock_df, market_df=None, ticker=None, universe=None):
    out = {}
    for m in ['technical', 'momentum', 'multifactor', 'capm']:
        try:
            out[m] = run_analysis(m, stock_df, market_df, ticker, universe)
        except Exception as e:
            out[m] = {'method': m, 'name': METHODS[m].__name__, 'signal': '中性',
                      'indicators': {}, 'conclusion': f'计算失败: {e}', 'extra': {}}
    return out


# ---------- 供 LLM / 前端复用的「事实」结构体 ----------
def build_facts(ticker, all_d, market=None, universe=None):
    """把一只股票的四方法分析结果整理成结构化事实，供大模型或离线模板使用。
    返回：{ticker, verdict, methods:[{name,signal,conclusion,indicators}]}"""
    if ticker not in all_d:
        return {'error': f'未知标的: {ticker}'}
    df = all_d[ticker]
    res = run_all(df, market, ticker, universe)
    methods = []
    for m in ['technical', 'momentum', 'multifactor', 'capm']:
        a = res[m]
        methods.append({
            'method': m,
            'name': a['name'],
            'signal': a['signal'],
            'conclusion': a['conclusion'],
            'indicators': {k: (str(v) if not isinstance(v, (int, float)) else v)
                           for k, v in a.get('indicators', {}).items()},
        })
    score = sum({'看多': 1, '看空': -1, '中性': 0}.get(m['signal'], 0) for m in methods)
    verdict = '偏多' if score > 0 else ('偏空' if score < 0 else '分歧/中性')
    return {'ticker': ticker, 'verdict': verdict, 'methods': methods}


# ---------- 供 function-calling 使用的工具封装 ----------
def call_tool(name, ticker, all_d, market=None, universe=None):
    """大模型工具调用入口：name ∈ {technical_analysis, momentum_risk,
    multifactor_analysis, capm_analysis}。返回精简、可序列化的事实。"""
    if ticker not in all_d:
        return {'error': f'未知标的: {ticker}'}
    df = all_d[ticker]
    if name == 'technical_analysis':
        a = analyze_technical(df)
    elif name == 'momentum_risk':
        a = analyze_momentum_risk(df)
    elif name == 'multifactor_analysis':
        a = analyze_multifactor(df, ticker=ticker, universe_factors=universe)
    elif name == 'capm_analysis':
        a = analyze_capm(df, market_df=market)
    else:
        return {'error': f'未知工具: {name}'}
    return {
        'name': a['name'],
        'signal': a['signal'],
        'conclusion': a['conclusion'],
        'indicators': {k: (str(v) if not isinstance(v, (int, float)) else v)
                       for k, v in a.get('indicators', {}).items()},
    }


# ---------- 组合 / 压力测试（模块二：组合管理与情景压测） ----------
def compute_beta_series(stock_df, market_df):
    """用日收益回归求 Beta；无市场基准时返回 1.0。"""
    sr = _daily_returns(_ensure_df(stock_df))
    if market_df is not None and len(market_df) > 1:
        m = _ensure_df(market_df)
        s = _ensure_df(stock_df)[['date', 'close']].rename(columns={'close': 's'})
        mm = m[['date', 'close']].rename(columns={'close': 'm'})
        j = pd.merge(s, mm, on='date').dropna()
        sr = j['s'].pct_change().dropna()
        mr = j['m'].pct_change().dropna()
    else:
        mr = sr * 0
    sr = sr.astype(float)
    mr = mr.astype(float).reindex(sr.index).fillna(0.0)
    k = min(len(sr), len(mr))
    if k < 30:
        return 1.0
    cov = np.cov(sr.iloc[-k:], mr.iloc[-k:])
    return float(_safe_div(cov[0, 1], cov[1, 1]) or 1.0)


def portfolio_daily_returns(holdings, all_d, market=None):
    """holdings: {ticker: weight}；返回 (组合日收益Series, 归一化权重dict)。"""
    w = {t: max(0.0, float(v)) for t, v in holdings.items() if t in all_d and v > 0}
    total = sum(w.values())
    if total <= 0:
        return None, {}
    w = {t: v / total for t, v in w.items()}
    common = None
    for t in w:
        r = _daily_returns(_ensure_df(all_d[t]))
        common = r.index if common is None else common.intersection(r.index)
    if common is None or len(common) < 30:
        return None, {}
    port = pd.Series(0.0, index=common)
    for t in w:
        r = _daily_returns(_ensure_df(all_d[t])).reindex(common).fillna(0.0)
        port = port + w[t] * r
    return port, w


def var_historical(returns, alpha=0.05):
    r = np.sort(pd.Series(returns).dropna().values)
    if len(r) == 0:
        return 0.0
    idx = max(0, min(len(r) - 1, int(alpha * len(r))))
    return float(r[idx])  # 负数（单日亏损分位）


def portfolio_summary(holdings, all_d, market=None):
    port, w = portfolio_daily_returns(holdings, all_d, market)
    if port is None:
        return {'error': '无法计算组合（标的不存在或数据不足）'}
    ann_ret = float(port.mean() * 252)
    ann_vol = float(port.std() * np.sqrt(252))
    cum = (1 + port).cumprod()
    dd = (cum / cum.cummax() - 1)
    max_dd = float(dd.min())
    sharpe = _safe_div(ann_ret - RF_ANNUAL, ann_vol)
    var95 = var_historical(port, 0.05)
    per_beta = {t: round(compute_beta_series(all_d[t], market), 2) for t in w}
    return {
        'weights': {t: round(v, 4) for t, v in w.items()},
        'ann_return': round(ann_ret * 100, 2),
        'ann_vol': round(ann_vol * 100, 2),
        'max_drawdown': round(max_dd * 100, 2),
        'sharpe': round(float(sharpe), 2),
        'var95_1d': round(var95 * 100, 2),
        'per_beta': per_beta,
        'n_assets': len(w),
    }


def monte_carlo_portfolio(holdings, all_d, market=None, horizon=60, paths=2000, seed=42,
                          keep_paths=120):
    """参数化蒙特卡洛：用历史日均收益/波动模拟组合未来 horizon 日的路径。
    keep_paths: 返回抽样路径数（供前端绘制扇形图）。"""
    port, w = portfolio_daily_returns(holdings, all_d, market)
    if port is None:
        return {'error': '无法模拟（标的不存在或数据不足）'}
    mu = float(port.mean())
    sigma = float(port.std())
    rng = np.random.default_rng(seed)
    sim = rng.normal(mu, sigma, size=(paths, horizon))
    cum = np.cumprod(1 + sim, axis=1)
    terminal = cum[:, -1] - 1
    running_max = np.maximum.accumulate(cum, axis=1)
    maxdd = (cum / running_max - 1).min(axis=1)
    # 抽样路径（等间隔取样，避免前端一次画太多）用于扇形图
    n_keep = min(keep_paths, paths)
    idx = np.linspace(0, paths - 1, n_keep).astype(int)
    sample = (cum[idx] - 1.0)  # 相对起点的累计收益率
    # 分位数带（P5/P25/P50/P75/P95），前端画扇形带
    qs = np.percentile(cum, [5, 25, 50, 75, 95], axis=0) - 1.0
    return {
        'horizon': horizon, 'paths': paths,
        'terminal_mean': round(float(terminal.mean()) * 100, 2),
        'terminal_p5': round(float(np.percentile(terminal, 5)) * 100, 2),
        'terminal_p95': round(float(np.percentile(terminal, 95)) * 100, 2),
        'maxdd_mean': round(float(-maxdd.mean()) * 100, 2),
        'maxdd_p95': round(float(-np.percentile(maxdd, 95)) * 100, 2),
        'maxdd_worst': round(float(-maxdd.min()) * 100, 2),
        # 扇形图数据（单位：%）
        'fan_quantiles': [[round(float(x) * 100, 3) for x in row] for row in qs],
        'sample_paths': [[round(float(x) * 100, 3) for x in row] for row in sample],
        'var95_path': [round(float(x) * 100, 3) for x in qs[0]],  # 95% VaR 路径（P5）
    }


def scenario_impact(holdings, all_d, market=None, market_shock_pct=-2.0, label=''):
    """情景冲击：以 CAPM Beta 的线性近似估计风险事件对各持仓的影响（教学演示口径）。
    market_shock_pct：该情景下「市场基准」的预期涨跌幅（%）。
    例如美联储加息 25bp 的经验冲击约 -2%，则 market_shock_pct=-2.0。"""
    port, w = portfolio_daily_returns(holdings, all_d, market)
    if port is None:
        return {'error': '无法计算（标的不存在或数据不足）'}
    lines = []
    total = 0.0
    for t, wx in w.items():
        b = compute_beta_series(all_d[t], market)
        move = b * float(market_shock_pct)  # β × 市场冲击 = 个股预期变动(%)
        lines.append({'ticker': t, 'weight': round(wx, 4),
                      'beta': round(float(b), 2), 'est_change_pct': round(float(move), 2)})
        total += wx * move
    total_pct = round(float(total), 2)
    # 基准最大回撤 + 情景冲击 = 压力情形下的回撤估计
    cum = (1 + port).cumprod()
    base_dd = round(float((cum / cum.cummax() - 1).min()) * 100, 2)
    stressed_dd = round(min(0.0, base_dd + min(0.0, total_pct)), 2)
    high = max(lines, key=lambda x: x['beta'])
    low = min(lines, key=lambda x: x['beta'])
    suggestion = (f"在「{label or '该情景'}」下（市场冲击 {market_shock_pct:+}%），"
                  f"预计组合净值变动 {total_pct:+}%；叠加历史最大回撤 {base_dd}%，"
                  f"压力情形下组合回撤可能扩大至约 {stressed_dd}%。"
                  f"建议：减持高 Beta 标的 {high['ticker']}（β={high['beta']}），"
                  f"适度增配低 Beta 标的 {low['ticker']}（β={low['beta']}）或防御/避险资产对冲。")
    return {'label': label, 'market_shock_pct': market_shock_pct,
            'total_impact_pct': total_pct, 'base_drawdown_pct': base_dd,
            'stressed_drawdown_pct': stressed_dd,
            'assets': lines, 'suggestion': suggestion}


if __name__ == '__main__':
    import json
    np.random.seed(42)
    dates = pd.date_range('2015-01-01', periods=3000, freq='D')
    price = 100 * np.cumprod(1 + np.random.normal(0.0003, 0.015, 3000))
    sdf = pd.DataFrame({'date': dates, 'close': price,
                        'open': price * 0.99, 'high': price * 1.01,
                        'low': price * 0.98, 'volume': 1e6})
    mdf = pd.DataFrame({'date': dates, 'close': price * 1.05})
    uf = compute_universe_factors({'KO': sdf, 'GE': sdf, 'IBM': sdf})
    print(json.dumps(run_all(sdf, mdf, 'KO', uf), ensure_ascii=False, indent=2, default=str))
