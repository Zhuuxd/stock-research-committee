"""
股票多方法分析 Web Demo —— 后端（Flask）
提供：
  GET /                  单页应用
  GET /api/stocks        标的列表
  GET /api/analyze?stock=KO&method=technical   单方法分析 + 图表序列
  GET /api/overview?stock=KO                   同股多方法对比总览
数据来源：data/prices.db（由 build_data.py 生成；缺失时使用内置回测序列）
"""
import os
import io
import sqlite3
import json
import pandas as pd
import numpy as np
from flask import Flask, request, jsonify, render_template, send_file

from analysis import (run_analysis, run_all, compute_universe_factors, build_facts,
                     call_tool, portfolio_summary, monte_carlo_portfolio, scenario_impact)
import llm

# 关掉第三方库的网络/重试日志与告警，避免终端刷屏、影响演示与录屏
import logging
import warnings
logging.getLogger('yfinance').setLevel(logging.CRITICAL)
logging.getLogger('urllib3').setLevel(logging.CRITICAL)
logging.getLogger('requests').setLevel(logging.CRITICAL)
logging.getLogger('urllib').setLevel(logging.CRITICAL)
warnings.filterwarnings('ignore')

# 生成《投资备忘录》PDF 所需
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, 'data')
DB_PATH = os.path.join(DATA_DIR, 'prices.db')
MANIFEST = os.path.join(DATA_DIR, 'manifest.json')

app = Flask(__name__, template_folder=os.path.join(HERE, 'templates'),
            static_folder=os.path.join(HERE, 'static'))

MANIFEST_DATA = {}
if os.path.exists(MANIFEST):
    with open(MANIFEST, encoding='utf-8') as f:
        MANIFEST_DATA = json.load(f)
STOCK_NAMES = MANIFEST_DATA.get('stocks', {})

# 数据缓存（避免每次请求重读 SQLite）
_CACHE = {'all_d': None, 'market': None, 'universe': None}


def get_data():
    if _CACHE['all_d'] is None:
        _CACHE['all_d'] = load_all_stocks()
        _CACHE['market'] = load_market()
        _CACHE['universe'] = compute_universe_factors(_CACHE['all_d'])
    return _CACHE['all_d'], _CACHE['market'], _CACHE['universe']


# ---------------- 数据加载 ----------------
def load_all_stocks():
    """读取所有标的日线；缺失则使用内置回测序列（保证 Demo 可运行）。"""
    out = {}
    if os.path.exists(DB_PATH):
        con = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("SELECT stock,date,open,high,low,close,volume FROM prices", con)
        con.close()
        if len(df):
            for c in ['open', 'high', 'low', 'close', 'volume']:
                df[c] = pd.to_numeric(df[c], errors='coerce')
            df['date'] = pd.to_datetime(df['date'])
            for tk, g in df.groupby('stock'):
                g = g.sort_values('date').dropna(subset=['close']).reset_index(drop=True)
                out[tk] = g
    if not out:
        import build_data
        out = build_data.gen_synthetic()
    return out


def load_market():
    """市场基准代理：所有标的平均收盘价（按日期对齐）。"""
    all_d = load_all_stocks()
    dfs = []
    for tk, g in all_d.items():
        d = g[['date', 'close']].rename(columns={'close': tk})
        dfs.append(d)
    m = dfs[0]
    for d in dfs[1:]:
        m = pd.merge(m, d, on='date', how='outer')
    m = m.sort_values('date').ffill()
    out = m.copy()
    out['close'] = m[[tk for tk in all_d]].mean(axis=1)
    return out[['date', 'close']].reset_index(drop=True)


def build_series(df):
    """构造前端绘图用的序列（日期、OHLC、均线、回撤、MACD）。"""
    c = df['close']
    ma5 = c.rolling(5).mean()
    ma10 = c.rolling(10).mean()
    ma20 = c.rolling(20).mean()
    cummax = c.cummax()
    dd = (c / cummax - 1)
    # MACD：标准 12/26/9 参数（与 analysis.analyze_technical 一致）
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    macd_hist = (dif - dea) * 2
    def rnd(col, nd=2):
        return [None if pd.isna(x) else round(float(x), nd) for x in col]
    return {
        'dates': df['date'].dt.strftime('%Y-%m-%d').tolist(),
        'close': rnd(c),
        'open': rnd(df['open']) if 'open' in df.columns else rnd(c),
        'high': rnd(df['high']) if 'high' in df.columns else rnd(c),
        'low': rnd(df['low']) if 'low' in df.columns else rnd(c),
        'ma5': rnd(ma5),
        'ma10': rnd(ma10),
        'ma20': rnd(ma20),
        'drawdown': [None if pd.isna(x) else round(float(x), 4) for x in dd],
        'macd_hist': rnd(macd_hist, 4),
        'macd_dif': rnd(dif, 4),
        'macd_dea': rnd(dea, 4),
    }


# ---------------- 路由 ----------------
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/stocks')
def api_stocks():
    names = STOCK_NAMES if STOCK_NAMES else {tk: {'name': tk} for tk in
                                             ['AAPL', 'MSFT', 'NVDA', 'TSLA', 'KO', 'MCD', 'JNJ', 'JPM']}
    items = [{'ticker': tk, 'name': v.get('name', tk), 'en': v.get('en', ''),
              'category': v.get('category', '')} for tk, v in names.items()]
    return jsonify({'source': MANIFEST_DATA.get('source', 'builtin'),
                    'as_of': MANIFEST_DATA.get('as_of', '-'),
                    'label': MANIFEST_DATA.get('label', ''),
                    'stocks': items})


@app.route('/api/analyze')
def api_analyze():
    tk = request.args.get('stock', 'KO')
    method = request.args.get('method', 'technical')
    all_d = load_all_stocks()
    if tk not in all_d:
        return jsonify({'error': '未知标的'}), 400
    df = all_d[tk]
    if len(df) < 30:
        return jsonify({'error': '数据不足'}), 400
    uf = compute_universe_factors(all_d)
    mkt = load_market() if method == 'capm' else None
    try:
        result = run_analysis(method, df, mkt, ticker=tk, universe=uf)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    series = build_series(df)
    name = STOCK_NAMES.get(tk, {}).get('name', tk)
    return jsonify({'stock': tk, 'name': name,
                    'as_of': MANIFEST_DATA.get('as_of', '-'),
                    'analysis': result, 'series': series})


@app.route('/api/overview')
def api_overview():
    tk = request.args.get('stock', 'KO')
    all_d = load_all_stocks()
    if tk not in all_d:
        return jsonify({'error': '未知标的'}), 400
    df = all_d[tk]
    if len(df) < 30:
        return jsonify({'error': '数据不足'}), 400
    uf = compute_universe_factors(all_d)
    mkt = load_market()
    all_res = run_all(df, mkt, ticker=tk, universe=uf)
    methods = [{'method': m, 'name': all_res[m]['name'],
                'signal': all_res[m]['signal'],
                'conclusion': all_res[m]['conclusion']} for m in
               ['technical', 'momentum', 'multifactor', 'capm']]
    name = STOCK_NAMES.get(tk, {}).get('name', tk)
    score = sum({'看多': 1, '看空': -1, '中性': 0}.get(m['signal'], 0) for m in methods)
    verdict = '偏多' if score > 0 else ('偏空' if score < 0 else '分歧/中性')
    return jsonify({'stock': tk, 'name': name,
                    'as_of': MANIFEST_DATA.get('as_of', '-'),
                    'methods': methods, 'verdict': verdict,
                    'series': build_series(df)})


def _open_browser(port):
    """启动后自动打开浏览器（设 NO_BROWSER=1 可关闭）。"""
    import time
    import webbrowser
    time.sleep(1.5)
    try:
        webbrowser.open(f'http://127.0.0.1:{port}')
    except Exception:
        pass


# ---------------- AI 智能体接口 ----------------
def _facts_for(tk):
    all_d, market, universe = get_data()
    if tk not in all_d:
        return None
    return build_facts(tk, all_d, market, universe)


def _make_executor(session_tk):
    all_d, market, universe = get_data()

    def executor(name, args):
        if name == '__facts__':
            return _facts_for(session_tk) or {'error': 'no facts'}
        tk = args.get('stock') or session_tk
        if tk not in all_d:
            return {'error': f'未知标的: {tk}'}
        return call_tool(name, tk, all_d, market, universe)

    return executor


@app.route('/api/diagnose')
def api_diagnose():
    tk = request.args.get('stock', 'KO')
    facts = _facts_for(tk)
    if not facts or facts.get('error'):
        return jsonify({'error': facts.get('error', '未知标的') if facts else '未知标的'}), 400
    prompt = (f"请基于以下对股票 {tk} 的量化分析事实，写一份面向普通投资者的"
              f"「AI 个股诊断报告」，要求：分「综合研判 / 四大方法要点 / 给普通投资者的大白话 / 风险提示」四段，"
              f"用 markdown，语言通俗、带具体数字，结尾必须写免责声明。\n\n量化事实：\n"
              f"{json.dumps(facts, ensure_ascii=False, indent=2)}")
    report = llm.synthesize(llm.SYSTEM_PROMPT, prompt)
    mode = 'llm' if llm.is_enabled() else 'mock'
    if not report:
        report = llm.mock_report(facts)
        mode = 'mock'
    name = STOCK_NAMES.get(tk, {}).get('name', tk)
    return jsonify({'stock': tk, 'name': name,
                    'as_of': MANIFEST_DATA.get('as_of', '-'),
                    'report': report, 'mode': mode,
                    'verdict': facts['verdict'], 'facts': facts})


@app.route('/api/chat', methods=['POST'])
def api_chat():
    body = request.get_json(force=True, silent=True) or {}
    tk = body.get('stock', 'KO')
    messages = body.get('messages', [])
    if not messages or not any(m.get('role') == 'user' for m in messages):
        return jsonify({'error': 'messages 不能为空'}), 400
    executor = _make_executor(tk)
    reply = llm.run_agent(llm.SYSTEM_PROMPT, messages, executor)
    mode = 'llm' if llm.is_enabled() else 'mock'
    return jsonify({'reply': reply, 'mode': mode, 'facts': _facts_for(tk)})


@app.route('/api/debate')
def api_debate():
    tk = request.args.get('stock', 'KO')
    facts = _facts_for(tk)
    if not facts or facts.get('error'):
        return jsonify({'error': facts.get('error', '未知标的') if facts else '未知标的'}), 400
    mode = 'llm' if llm.is_enabled() else 'mock'
    if mode == 'mock':
        d = llm.mock_debate(facts)
        d['stock'] = tk
        return jsonify(d)
    # 真实模式：三个角色各自基于事实发言 + 裁判汇总
    roles = []
    personas = [
        ('技术派', '你是技术派分析师，只看价格趋势、均线、MACD，语气干脆。'),
        ('动量&风险派', '你是动量&风险派分析师，关注涨势、波动率、回撤、夏普，强调风控。'),
        ('价值&因子派', '你是价值&因子派分析师，关注相对同业的因子暴露与排名，看重相对强弱。'),
    ]
    for name, persona in personas:
        p = (f"{persona} 请基于以下量化事实，用 2-3 句话给出你对股票 {tk} 的观点（带具体信号）。\n"
             f"{json.dumps(facts, ensure_ascii=False, indent=2)}")
        text = llm.synthesize(persona, p) or ''
        roles.append({'role': name, 'stance': _stance_of(text, facts), 'text': text})
    judge_p = (f"你是裁判。以下是三位分析师对股票 {tk} 的观点，请综合成一段「综合研判」，"
               f"说明分歧点并给普通投资者一句建议。\n"
               + "\n".join(f"{r['role']}：{r['text']}" for r in roles))
    judge = llm.synthesize('你是客观公正的投研裁判。', judge_p) or ''
    return jsonify({'stock': tk, 'roles': roles, 'judge': judge, 'mode': 'llm',
                    'verdict': facts['verdict'], 'facts': facts})


def _stance_of(text, facts):
    for m in facts['methods']:
        if m['name'] in text and m['signal'] in ('看多', '看空'):
            return m['signal']
    return '中性'


# ---------------- 模块一：多智能体投研委员会 ----------------
@app.route('/api/committee')
def api_committee():
    tk = request.args.get('stock', 'KO')
    facts = _facts_for(tk)
    if not facts or facts.get('error'):
        return jsonify({'error': facts.get('error', '未知标的') if facts else '未知标的'}), 400
    c = llm.run_committee(tk, facts)
    c['name'] = STOCK_NAMES.get(tk, {}).get('name', tk)
    c['as_of'] = MANIFEST_DATA.get('as_of', '-')
    return jsonify(c)


# ---------------- 模块一增强：一键生成《投资备忘录》PDF ----------------
def build_memo_pdf(c):
    """根据委员会结果生成排版精美的《投资备忘录》PDF，返回 bytes。"""
    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    FONT = 'STSong-Light'
    NAVY = colors.HexColor('#16234a'); BLUE = colors.HexColor('#2f6fed')
    RED = colors.HexColor('#e23b3b'); GOLD = colors.HexColor('#c9931f')
    DIM = colors.HexColor('#6b7686')
    ss = getSampleStyleSheet()
    H1 = ParagraphStyle('H1', fontName=FONT, fontSize=18, leading=24, alignment=TA_CENTER, textColor=NAVY, spaceAfter=2)
    SUB = ParagraphStyle('SUB', fontName=FONT, fontSize=10, leading=15, alignment=TA_CENTER, textColor=DIM)
    H2 = ParagraphStyle('H2', fontName=FONT, fontSize=12.5, leading=17, spaceBefore=10, spaceAfter=4, textColor=BLUE)
    BODY = ParagraphStyle('BODY', fontName=FONT, fontSize=10, leading=15)
    SMALL = ParagraphStyle('SMALL', fontName=FONT, fontSize=8.5, leading=12.5, textColor=DIM)
    WHITEB = ParagraphStyle('WHITEB', fontName=FONT, fontSize=14, leading=18, textColor=colors.white)
    WHITES = ParagraphStyle('WHITES', fontName=FONT, fontSize=11, leading=15, textColor=colors.white)
    MEMO = ParagraphStyle('MEMO', fontName=FONT, fontSize=10, leading=15.5, backColor=colors.HexColor('#f5f7fb'), borderPadding=8, spaceBefore=2, spaceAfter=2)
    story = []
    tk = c.get('stock') or ''
    name = c.get('name') or tk
    asof = c.get('as_of') or '-'
    veto = bool(c.get('veto'))
    stance = c.get('cio_stance') or '—'
    conf = c.get('confidence') or 0
    story.append(Paragraph('投资备忘录', H1))
    story.append(Paragraph(f'AI 投研委员会 · {tk} {name} · 数据截至 {asof}', SUB))
    story.append(Spacer(1, 8))
    vt = Table([[Paragraph(f'<b>委员会裁决：{stance}</b>', WHITEB),
                 Paragraph(f'委员会共识度 {conf}%', WHITES)]],
               colWidths=[112 * mm, 62 * mm])
    vt.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), (RED if veto else GOLD)),
                            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                            ('LEFTPADDING', (0, 0), (-1, -1), 10), ('RIGHTPADDING', (0, 0), (-1, -1), 10),
                            ('TOPPADDING', (0, 0), (-1, -1), 9), ('BOTTOMPADDING', (0, 0), (-1, -1), 9)]))
    story.append(vt)
    if veto:
        vb = Table([[Paragraph('⚠ 风控部门已行使【一票否决权】，其余分析师意见已暂停，本备忘录以风控意见为准。',
                               ParagraphStyle('vb', fontName=FONT, fontSize=10, leading=14, textColor=RED))]])
        vb.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fdeaea')),
                                ('BOX', (0, 0), (-1, -1), 0.8, RED),
                                ('LEFTPADDING', (0, 0), (-1, -1), 8), ('TOPPADDING', (0, 0), (-1, -1), 6),
                                ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
        story.append(Spacer(1, 6)); story.append(vb)
    story.append(Spacer(1, 6))
    story.append(Paragraph('一、多智能体辩论摘要', H2))
    for s in c.get('steps', []):
        if s.get('is_cio'):
            continue
        role = s.get('role', ''); st = s.get('stance', ''); txt = s.get('text', '')
        story.append(Paragraph(f'<b>{role}</b>　<font color="#6b7686">[{st}]</font>',
                               ParagraphStyle('h', fontName=FONT, fontSize=10, leading=14, spaceBefore=2)))
        story.append(Paragraph(txt, ParagraphStyle('b', fontName=FONT, fontSize=9.5, leading=14)))
        story.append(Spacer(1, 4))
    story.append(Paragraph('二、CIO 投资备忘录（操作建议）', H2))
    story.append(Paragraph(c.get('memo') or '（无）', MEMO))
    story.append(Spacer(1, 8))
    story.append(Paragraph('三、风险提示与声明', H2))
    story.append(Paragraph(
        '本备忘录由 AI 多智能体系统基于历史行情与量化指标自动生成（<b>AI 生成内容，未经人工尽职调查</b>）。'
        '内容仅供比赛演示与学习，不构成任何投资建议。市场有风险，投资需谨慎；据此操作，盈亏自负。',
        SMALL))
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=16 * mm,
                            leftMargin=18 * mm, rightMargin=18 * mm, title='投资备忘录')
    doc.build(story)
    buf.seek(0)
    return buf.read()


@app.route('/api/memo_pdf', methods=['POST'])
def api_memo_pdf():
    c = request.get_json(force=True, silent=True) or {}
    if not c.get('steps'):
        return jsonify({'error': '缺少委员会数据，请先召开投研委员会'}), 400
    c.setdefault('stock', '')
    c.setdefault('name', c.get('stock') or '')
    try:
        data = build_memo_pdf(c)
    except Exception as e:
        return jsonify({'error': f'生成失败：{e}'}), 500
    safe = (c.get('name') or c.get('stock') or 'AI').replace('/', '_').replace(' ', '_')
    return send_file(io.BytesIO(data), mimetype='application/pdf',
                     as_attachment=True, download_name=f'投资备忘录_{safe}.pdf')


# ---------------- 模块二：组合压力测试 / 蒙特卡洛 ----------------
@app.route('/api/portfolio', methods=['POST'])
def api_portfolio():
    body = request.get_json(force=True, silent=True) or {}
    holdings = {str(k).upper(): float(v) for k, v in (body.get('holdings') or {}).items()
                if v not in (None, '', 0)}
    if not holdings:
        return jsonify({'error': 'holdings 不能为空，例如 {"KO":40,"AAPL":30,"GE":30}'}), 400
    all_d, market, _ = get_data()
    unknown = [t for t in holdings if t not in all_d]
    if unknown:
        return jsonify({'error': f'未知标的: {unknown}'}), 400
    summary = portfolio_summary(holdings, all_d, market)
    if 'error' in summary:
        return jsonify({'error': summary['error']}), 400
    horizon = int(body.get('horizon', 60))
    paths = int(body.get('paths', 1000))
    monte = monte_carlo_portfolio(holdings, all_d, market, horizon=min(252, max(10, horizon)),
                                  paths=min(5000, max(200, paths)),
                                  keep_paths=min(300, max(60, paths)))
    # 情景定义：(市场基准预期冲击 %, 情景名)
    scenarios = []
    for shock, label in [(-2.0, '美联储加息 25bp'), (-4.0, '美联储加息 50bp'),
                        (-8.0, '经济温和衰退'), (+3.0, '风险偏好回暖(利好)')]:
        try:
            scenarios.append(scenario_impact(holdings, all_d, market,
                                             market_shock_pct=shock, label=label))
        except Exception:
            pass
    return jsonify({'holdings': holdings, 'summary': summary, 'monte_carlo': monte,
                    'scenarios': scenarios})


# ---------------- 模块三：非结构化数据 RAG ----------------
RAG_CORPUS_DIR = os.path.join(HERE, 'rag_corpus')


def load_rag_corpus():
    """加载内置 A 股白马股素材库（rag_corpus/），返回拼接后的纯文本。"""
    if not os.path.isdir(RAG_CORPUS_DIR):
        return ''
    parts = []
    for fn in sorted(os.listdir(RAG_CORPUS_DIR)):
        p = os.path.join(RAG_CORPUS_DIR, fn)
        if fn.lower().endswith('.pdf'):
            try:
                import pypdf
                r = pypdf.PdfReader(p)
                parts.append('\n'.join((pg.extract_text() or '') for pg in r.pages))
            except Exception:
                continue
        elif fn.lower().endswith(('.txt', '.md', '.csv')):
            try:
                parts.append(open(p, encoding='utf-8', errors='ignore').read())
            except Exception:
                continue
    return '\n\n'.join(parts)


@app.route('/api/rag', methods=['POST'])
def api_rag():
    doc_text = ''
    query = ''
    use_corpus = False
    source_label = ''
    if request.content_type and 'multipart/form-data' in request.content_type:
        query = (request.form.get('query') or '').strip()
        f = request.files.get('file')
        if f:
            raw = f.read()
            source_label = f.filename or '上传文档'
            if f.filename and f.filename.lower().endswith('.pdf'):
                try:
                    import pypdf
                    r = pypdf.PdfReader(io.BytesIO(raw))
                    doc_text = '\n'.join((pg.extract_text() or '') for pg in r.pages)
                except Exception as e:
                    return jsonify({'error': f'PDF 解析失败，请确认文件未加密且格式正确（{e}）'}), 400
            else:
                doc_text = raw.decode('utf-8', errors='ignore')
        # multipart 下若未上传文件，则使用表单里的 doc_text（粘贴文本场景）
        if not doc_text.strip():
            doc_text = request.form.get('doc_text', '') or ''
            if doc_text.strip():
                source_label = '粘贴文本'
        use_corpus = request.form.get('use_corpus') == '1'
    else:
        body = request.get_json(force=True, silent=True) or {}
        doc_text = body.get('doc_text', '') or ''
        query = (body.get('query') or '').strip()
        use_corpus = bool(body.get('use_corpus'))
        if doc_text.strip():
            source_label = '粘贴文本'

    # 未提供文档时，默认使用内置 A 股白马股素材库（满足"RAG 模块用 A 股"的演示诉求）
    if not doc_text.strip() and use_corpus:
        doc_text = load_rag_corpus()
        source_label = '内置A股白马股素材库（贵州茅台 / 宁德时代）'
    if not doc_text.strip():
        doc_text = load_rag_corpus()  # 兜底：始终有素材可检索
        source_label = '内置A股白马股素材库（贵州茅台 / 宁德时代）'
    if not doc_text.strip():
        return jsonify({'error': '文档内容为空（可粘贴文本、上传 .txt/.pdf，或直接使用内置 A 股素材库）'}), 400
    if not query:
        return jsonify({'error': '问题(query)不能为空'}), 400
    chunks = llm.rag_split(doc_text)
    res = llm.run_rag(chunks, query, source_label=source_label or '检索语料')
    res['chunks_total'] = len(chunks)
    res['corpus'] = 'a_share' if use_corpus else 'custom'
    return jsonify(res)


# ---------------- 模块二增强：预设宏观情景（一键推演） ----------------
# 每个情景给出市场基准冲击经验值 + 针对该情景的对冲建议（演示用，教学口径）
SCENARIO_PRESETS = {
    'fed_hike': {
        'shock': -2.0, 'label': '美联储加息 25bp',
        'desc': '利率上行，高估值与高杠杆资产首当其冲',
        'hedge': '建议减配高 Beta 标的，增配短久期/现金，或买入黄金 ETF（如 518880）对冲约 15% 仓位。',
    },
    'ai_bubble': {
        'shock': -6.0, 'label': 'AI 泡沫破裂',
        'desc': '科技/AI 交易拥挤，回撤时踩踏明显',
        'hedge': 'AI/科技仓位过重，建议降至核心仓位的 60%，增配公用事业与必选消费等防御板块。',
    },
    'geopolitical': {
        'shock': -5.0, 'label': '地缘政治危机',
        'desc': '避险情绪升温，风险资产普跌',
        'hedge': '建议买入黄金 ETF 与国债 ETF 对冲（合计 15-20% 仓位），并降低整体杠杆。',
    },
    'recession': {
        'shock': -8.0, 'label': '经济温和衰退',
        'desc': '盈利预期下修，周期性资产走弱',
        'hedge': '增配必选消费/医药等防御板块，黄金+国债对冲，现金仓位提升至 20%。',
    },
}


@app.route('/api/scenario', methods=['POST'])
def api_scenario():
    body = request.get_json(force=True, silent=True) or {}
    key = body.get('scenario', 'fed_hike')
    if key not in SCENARIO_PRESETS:
        key = 'fed_hike'
    holdings = {str(k).upper(): float(v) for k, v in (body.get('holdings') or {}).items()
                if v not in (None, '', 0)}
    if not holdings:
        return jsonify({'error': 'holdings 不能为空，例如 {"KO":40,"AAPL":30,"GE":30}'}), 400
    all_d, market, _ = get_data()
    unknown = [t for t in holdings if t not in all_d]
    if unknown:
        return jsonify({'error': f'未知标的: {unknown}'}), 400
    preset = SCENARIO_PRESETS[key]
    try:
        res = scenario_impact(holdings, all_d, market,
                             market_shock_pct=preset['shock'], label=preset['label'])
    except Exception:
        return jsonify({'error': '情景推演失败，请重试'}), 500
    if 'error' in res:
        return jsonify({'error': res['error']}), 400
    res['key'] = key
    res['desc'] = preset['desc']
    res['hedge'] = preset['hedge']
    return jsonify(res)


# ---------------- 全局兜底：任何未捕获异常都返回干净 JSON（不暴露堆栈） ----------------
@app.errorhandler(Exception)
def _handle_err(e):
    return jsonify({'error': '服务暂时不可用，请稍后重试'}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f'\n  股析 Demo 已启动 -> http://127.0.0.1:{port}')
    print('  浏览器会自动打开；要停止请在本窗口按 Ctrl+C\n')
    if os.environ.get('NO_BROWSER') != '1':
        import threading
        threading.Thread(target=_open_browser, args=(port,), daemon=True).start()
    app.run(host='127.0.0.1', port=port, debug=False)
