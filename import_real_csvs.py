"""
真实行情 CSV 导入器
================================================================
把"金融朋友"下载的真实行情（中文列头：日期/开盘/最高/最低/收盘/成交量）
转换成 build_data.read_csv 所需的英文列格式，写入 data/csv/<TICKER>.csv。

映射规则（读取时自动按中文列名归位）：
    日期   -> date
    开盘   -> open
    最高   -> high
    最低   -> low
    收盘   -> close
    成交量 -> volume

用法：
    python import_real_csvs.py                 # 仅导入在 STOCKS 列表内的美股（KO / AAPL）
    python import_real_csvs.py --all           # 额外导入 A 股（600519 贵州茅台 / 300750 宁德时代）
    python import_real_csvs.py --src "其它目录"

导入后运行：python build_data.py   （重建 prices.db / json / manifest）
"""
import os
import argparse
import pandas as pd
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_CSV = os.path.join(HERE, 'data', 'csv')

# 源目录默认指向用户提供的"无套牢盘白马股_3年CSV / 美股8只_近3年"
DEFAULT_SRC = r"C:\Users\admin\WorkBuddy\2026-09-06-15-11-59\无套牢盘白马股_3年CSV\美股8只_近3年"

# 文件名（不含扩展名）-> 目标 TICKER（必须是 build_data.STOCKS 里的键，或 --all 时单独登记）
# AAPL 此前已从父目录导入 data/csv/AAPL.csv，这里只导入本批 7 只新真实快照
FILE_TO_TICKER = {
    'KO_可口可乐_近3年': 'KO',
    'MSFT_微软_近3年': 'MSFT',
    'NVDA_英伟达_近3年': 'NVDA',
    'TSLA_特斯拉_近3年': 'TSLA',
    'MCD_麦当劳_近3年': 'MCD',
    'JNJ_强生_近3年': 'JNJ',
    'JPM_摩根大通_近3年': 'JPM',
}
# --all 时额外导入的 A 股（写进 data/csv/<代码>.csv，需在 STOCKS 里登记才能被 Demo 使用）
ASHARE_FILE_TO_TICKER = {
    '600519_贵州茅台_近3年': '600519',
    '300750_宁德时代_近3年': '300750',
}

COL_MAP = {
    '日期': 'date', '开盘': 'open', '最高': 'high',
    '最低': 'low', '收盘': 'close', '成交量': 'volume',
}


def _convert(src_path, ticker):
    """读取一份真实 CSV，转为标准英文列，返回 DataFrame。"""
    df = pd.read_csv(src_path, encoding='utf-8-sig')
    df.columns = [str(c).strip() for c in df.columns]
    # 找不到中文列时，退回英文列（兼容已经是英文格式的快照）
    eng = {'date', 'open', 'high', 'low', 'close', 'volume'}
    if not set(COL_MAP).issubset(set(df.columns)):
        if eng.issubset(set(map(str.lower, df.columns))):
            df.columns = [c.lower() for c in df.columns]
        else:
            raise ValueError(f'{src_path} 缺少必要列（需要 日期/开盘/最高/最低/收盘/成交量）')
    else:
        df = df.rename(columns=COL_MAP)
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    for c in ['open', 'high', 'low', 'close', 'volume']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df = df.dropna(subset=['close', 'date']).sort_values('date').reset_index(drop=True)
    df['date'] = df['date'].dt.strftime('%Y-%m-%d')
    # 不变量修正：high>=max(o,c), low<=min(o,c)
    df['high'] = np.maximum.reduce([df['high'], df['open'], df['close']])
    df['low'] = np.minimum.reduce([df['low'], df['open'], df['close']])
    return df[['date', 'open', 'high', 'low', 'close', 'volume']]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', default=DEFAULT_SRC, help='真实 CSV 所在目录')
    ap.add_argument('--all', action='store_true', help='同时导入 A 股（600519/300750）')
    args = ap.parse_args()

    os.makedirs(DATA_CSV, exist_ok=True)
    mapping = dict(FILE_TO_TICKER)
    if args.all:
        mapping.update(ASHARE_FILE_TO_TICKER)

    imported, skipped = [], []
    for fname, tk in mapping.items():
        src = os.path.join(args.src, fname + '.csv')
        if not os.path.exists(src):
            skipped.append((tk, '源文件不存在'))
            continue
        try:
            out = _convert(src, tk)
            if len(out) < 120:
                skipped.append((tk, f'行数过少({len(out)})'))
                continue
            outpath = os.path.join(DATA_CSV, tk + '.csv')
            out.to_csv(outpath, index=False)
            imported.append((tk, len(out), out['date'].iloc[0], out['date'].iloc[-1]))
        except Exception as e:
            skipped.append((tk, f'错误: {e}'))

    print('=== 导入完成 ===')
    for tk, n, d0, d1 in imported:
        print(f'  ✅ {tk:6s} -> data/csv/{tk}.csv  ({n} 行, {d0}..{d1})')
    for tk, why in skipped:
        print(f'  ⚠️  {tk:6s} 跳过: {why}')
    print('\n下一步：运行  python build_data.py   重建 prices.db / json / manifest')


if __name__ == '__main__':
    main()
