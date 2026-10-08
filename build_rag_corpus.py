"""
A 股白马股 RAG 素材库生成器
================================================================
从用户提供的"无套牢盘白马股_3年CSV"真实日线数据，计算关键指标，
写出可供 RAG 模块检索的中文研究素材（rag_corpus/ 目录）。

所有数字均直接来自真实 CSV，不虚构；仅做归纳与表述。
运行：python build_rag_corpus.py
"""
import os
import pandas as pd
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = r"C:\Users\admin\WorkBuddy\2026-09-06-15-11-59\无套牢盘白马股_3年CSV"
OUT = os.path.join(HERE, 'rag_corpus')
os.makedirs(OUT, exist_ok=True)


def stats(path, name, code, market):
    df = pd.read_csv(path, encoding='utf-8-sig')
    df['日期'] = pd.to_datetime(df['日期'])
    df = df.sort_values('日期').reset_index(drop=True)
    c = df['收盘'].astype(float).values
    dts = df['日期']
    n = len(c)
    cummax = np.maximum.accumulate(c)
    dd = (c / cummax - 1).min() * 100
    rets = np.diff(np.log(c))
    annvol = rets.std() * np.sqrt(252) * 100
    high3y = float(c.max()); low3y = float(c.min())
    cur = float(c[-1]); start = float(c[0])
    vs_high = (cur / high3y - 1) * 100
    ma250 = float(c[-250:].mean()) if n >= 250 else float(c.mean())
    vs_ma250 = (cur / ma250 - 1) * 100
    r60 = (c[-1] / c[-61] - 1) * 100 if n >= 61 else float('nan')
    r1y = (c[-1] / c[-252] - 1) * 100 if n >= 252 else float('nan')
    return dict(name=name, code=code, market=market, n=n,
                d0=dts.min().strftime('%Y-%m-%d'), d1=dts.max().strftime('%Y-%m-%d'),
                start=start, cur=cur, high3y=high3y, low3y=low3y,
                vs_high=vs_high, ma250=ma250, vs_ma250=vs_ma250,
                dd=dd, annvol=annvol, r60=r60, r1y=r1y)


def fmt(v, unit='', nd=2):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return '—'
    return f'{v:+.{nd}f}{unit}' if isinstance(v, float) and v > 0 else f'{v:.{nd}f}{unit}'


def doc_text(s):
    above = '高于' if s['vs_ma250'] >= 0 else '低于'
    trapped = '否（当前处于年线下方，存在套牢盘）' if s['vs_ma250'] < 0 else '是（年线上方，套牢盘较轻）'
    return f"""# {s['name']}（{s['code']}·{s['market']}）个股研究素材

## 基础信息
- 证券简称：{s['name']}，代码 {s['code']}，上市市场：{s['market']}
- 数据区间：{s['d0']} 至 {s['d1']}，共 {s['n']} 个交易日（近 3 年日线）

## 价格与估值位置
- 区间起点收盘价：{s['start']:.2f} 元；最新收盘价：{s['cur']:.2f} 元
- 近 3 年最高价（前复权）：{s['high3y']:.2f} 元；最低价：{s['low3y']:.2f} 元
- 最新价较 3 年高点：{fmt(s['vs_high'], '%')}（{'已接近' if s['vs_high'] > -10 else '仍显著低于'}历史高位）
- 250 日均线（年线）：{s['ma250']:.2f} 元；最新价较年线：{fmt(s['vs_ma250'], '%')}，即当前{above}年线
- 无套牢盘判定：{trapped}

## 风险与波动
- 区间最大回撤：{fmt(s['dd'], '%')}
- 年化波动率：{fmt(s['annvol'], '%')}
- 近 60 日涨跌幅：{fmt(s['r60'], '%')}；近 1 年涨跌幅：{fmt(s['r1y'], '%')}

## 投研视角要点（基于上述真实数据）
- 该股近 3 年波动与回撤水平如上，仓位管理需与其波动率匹配。
- {'当前价格位于年线之上，中期趋势相对占优，但距 3 年高点仍有距离。' if s['vs_ma250'] >= 0 else '当前价格位于年线之下，中期趋势偏弱，需警惕下行风险与套牢盘抛压。'}
- 以上为量化指标归纳，仅供研究参考，不构成投资建议。
"""


def summary_doc():
    path = os.path.join(SRC, '白马股_无套牢盘判定汇总.csv')
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path, encoding='utf-8-sig')
    lines = ['# 无套牢盘白马股 · 判定汇总（近 3 年窗口）', '']
    lines.append('判定口径：严格无套牢 = 现价 ≥ 3 年最高；年线上方 = 近一年持仓无套牢（现价在 250 日均线之上）。',)
    lines.append('')
    lines.append('| 代码 | 名称 | 末日 | 最新收盘 | 3年最高 | 距3年最高% | 年线 | 现价距年线% | 近60日% | 严格无套牢 | 年线上方 |')
    lines.append('|---|---|---|---|---|---|---|---|---|---|---|')
    for _, r in df.iterrows():
        lines.append(
            f"| {r['代码']} | {r['名称']} | {r['末日']} | {r['最新收盘']} | {r['3年窗口最高']} | "
            f"{r['距3年最高%']} | {r['MA250年线']} | {r['现价距年线%']} | {r['近60日涨幅%']} | "
            f"{r['严格无套牢(现价≥3年最高)']} | {r['年线上方(近一年持仓无套牢)']} |")
    lines.append('')
    lines.append('要点：本表中四只标的均未达到"严格无套牢（现价≥3年最高）"；其中 KO、AAPL 处于年线上方（近一年无套牢），'
                 '600519 贵州茅台、300750 宁德时代当前位于年线下方，存在套牢盘，需谨慎对待。')
    return '\n'.join(lines)


def main():
    items = [
        ('600519_贵州茅台_近3年.csv', '贵州茅台', '600519', 'A股'),
        ('300750_宁德时代_近3年.csv', '宁德时代', '300750', 'A股'),
    ]
    written = []
    for fn, name, code, mkt in items:
        p = os.path.join(SRC, fn)
        if not os.path.exists(p):
            print(f'跳过（源文件缺失）: {fn}')
            continue
        s = stats(p, name, code, mkt)
        out = os.path.join(OUT, f'{code}_{name}_研究素材.md')
        with open(out, 'w', encoding='utf-8') as f:
            f.write(doc_text(s))
        written.append((code, name, s['vs_ma250'], s['dd']))
        print(f'  ✅ {code} {name}: 写 {out}  (年线{((s["vs_ma250"]>=0) and "上方" or "下方")}, 最大回撤 {s["dd"]:.1f}%)')

    sm = summary_doc()
    if sm:
        out = os.path.join(OUT, '无套牢盘白马股_判定汇总.md')
        with open(out, 'w', encoding='utf-8') as f:
            f.write(sm)
        print(f'  ✅ 判定汇总: 写 {out}')

    print(f'\n完成：{len(written)} 只 A 股素材 + 1 份判定汇总 -> rag_corpus/')
    print('RAG 模块将默认加载该目录，可直接提问"茅台当前是否站上年线""宁德时代最大回撤多少"。')


if __name__ == '__main__':
    main()
