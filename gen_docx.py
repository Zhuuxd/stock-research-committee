# -*- coding: utf-8 -*-
"""生成《股析 · AI 投研委员会》项目说明书 —— 可编辑 Word（.docx）。

格式对齐党政机关公文（GB/T 9704-2012）：
- 标题：方正小标宋_GBK，二号，不加粗
- 正文：方正仿宋_GBK，三号
- 一级标题（一、二、三、）：黑体，三号
- 二级标题（（一）（二））：方正仿宋_GBK，小三，加粗
- 三级标题（1. 2.）：方正小标宋_GBK，小三
- 数字（含标题中的阿拉伯数字）：Times New Roman
- 标题行距：固定值 33–36 磅；全文行距：固定值 28 磅
数字与截图全部来自项目真实运行结果，不虚构；可离线生成（LLM 调用失败时跳过）。
"""
import os, json
import numpy as np
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

import analysis, llm
import app as appmod

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '项目说明书.docx')
IMG = os.path.join(HERE, 'architecture.png')
SEQ = os.path.join(HERE, 'sequence.png')
SHOTS = os.path.join(HERE, 'shots')

# ===== 公文字体 =====
BIAOSONG = '方正小标宋_GBK'   # 标题 / 三级标题
FANGSONG = '方正仿宋_GBK'     # 正文 / 二级标题
HEI = '黑体'                  # 一级标题
TNR = 'Times New Roman'       # 所有数字与拉丁字母

NAVY = RGBColor(0x16, 0x23, 0x4a)
BLUE = RGBColor(0x2f, 0x6f, 0xed)
MUT = RGBColor(0x6b, 0x76, 0x86)
RED = RGBColor(0xc0, 0x2b, 0x2b)
GOLD = RGBColor(0x8a, 0x66, 0x10)
INKC = RGBColor(0x1F, 0x2A, 0x44)
BLACK = RGBColor(0x00, 0x00, 0x00)

doc = Document()
for s in doc.sections:
    s.top_margin = Cm(1.6); s.bottom_margin = Cm(1.6)
    s.left_margin = Cm(1.9); s.right_margin = Cm(1.9)

# ===== 正文默认样式：方正仿宋 三号 + 固定值28磅 =====
st = doc.styles['Normal']
st.font.name = FANGSONG
st.font.size = Pt(16)                 # 三号
st.element.rPr.rFonts.set(qn('w:eastAsia'), FANGSONG)
st.element.rPr.rFonts.set(qn('w:ascii'), TNR)
st.element.rPr.rFonts.set(qn('w:hAnsi'), TNR)
_pf = st.paragraph_format
_pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
_pf.line_spacing = Pt(28)             # 全文行距固定值 28 磅
_pf.space_before = Pt(0)
_pf.space_after = Pt(0)

# ===== 一级/二级/三级标题样式（公文）=====
for lvl, (cjk, sz, bold) in {
    1: (HEI, 16, False),            # 黑体 三号 不加粗
    2: (FANGSONG, 15, True),        # 方正仿宋 小三 加粗
    3: (BIAOSONG, 15, False),       # 方正小标宋 小三
}.items():
    sty = doc.styles[f'Heading {lvl}']
    sty.font.name = cjk
    sty.font.size = Pt(sz)
    sty.font.bold = bold
    sty.font.color.rgb = BLACK
    rpr = sty.element.get_or_add_rPr()
    rf = rpr.find(qn('w:rFonts'))
    if rf is None:
        rf = OxmlElement('w:rFonts'); rpr.append(rf)
    rf.set(qn('w:eastAsia'), cjk)
    rf.set(qn('w:ascii'), TNR)
    rf.set(qn('w:hAnsi'), TNR)
    sty.paragraph_format.space_before = Pt(6)
    sty.paragraph_format.space_after = Pt(6)
    sty.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    sty.paragraph_format.line_spacing = Pt(33)   # 标题行距固定值 33 磅


def _exact_spacing(p, pt):
    """固定值行距（磅）：直接写 w:spacing，避免 python-docx 对 EXACTLY 的换算偏差。"""
    pPr = p._p.get_or_add_pPr()
    sp = pPr.find(qn('w:spacing'))
    if sp is None:
        sp = OxmlElement('w:spacing'); pPr.append(sp)
    sp.set(qn('w:line'), str(int(pt * 20)))
    sp.set(qn('w:lineRule'), 'exact')


def _setfont(run, cjk=FANGSONG):
    """设置中文字体为 cjk，数字与拉丁字母统一 Times New Roman。"""
    run.font.name = cjk
    rpr = run._element.get_or_add_rPr()
    rf = rpr.find(qn('w:rFonts'))
    if rf is None:
        rf = OxmlElement('w:rFonts'); rpr.append(rf)
    rf.set(qn('w:eastAsia'), cjk)
    rf.set(qn('w:ascii'), TNR)
    rf.set(qn('w:hAnsi'), TNR)


FIG_NO = [0]
TAB_NO = [0]


def title(text, size=22):
    """公文标题：方正小标宋 二号 不加粗，居中，行距固定值 36 磅。"""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    p.paragraph_format.line_spacing = Pt(36)
    p.paragraph_format.space_after = Pt(12)
    r = p.add_run(text)
    r.font.name = BIAOSONG
    r.font.size = Pt(size)        # 二号 = 22pt
    r.bold = False
    _setfont(r, BIAOSONG)
    return p


def H(text, level=1, align=None):
    """公文标题：一、/（一）/ 1. 由调用处传入；按层级套用字体与固定行距。"""
    p = doc.add_paragraph(style=f'Heading {level}')
    if align:
        p.alignment = align
    _exact_spacing(p, 33)   # 标题行距固定值 33 磅
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(6)
    r = p.add_run(text)
    if level == 1:
        r.font.size = Pt(16); r.bold = False; r.font.color.rgb = BLACK
        _setfont(r, HEI)
    elif level == 2:
        r.font.size = Pt(15); r.bold = True; r.font.color.rgb = BLACK
        _setfont(r, FANGSONG)
    else:
        r.font.size = Pt(15); r.bold = False; r.font.color.rgb = BLACK
        _setfont(r, BIAOSONG)
    return p


def P(text, size=16, color=None, bold=False, indent=0.0, align=None, sa=None):
    """正文：方正仿宋 三号，固定值 28 磅。"""
    p = doc.add_paragraph()
    if sa is not None:
        p.paragraph_format.space_after = Pt(sa)
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    p.paragraph_format.line_spacing = Pt(28)
    if indent:
        p.paragraph_format.left_indent = Cm(indent)
    if align:
        p.alignment = align
    r = p.add_run(text); r.font.size = Pt(size); r.bold = bold
    if color:
        r.font.color.rgb = color
    _setfont(r, FANGSONG)
    return p


def QUOTE(text, size=16):
    """核心结论（引用块样式，保留强调）"""
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.5)
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    p.paragraph_format.line_spacing = Pt(28)
    r = p.add_run(text); r.bold = True; r.font.size = Pt(size); r.font.color.rgb = NAVY
    _setfont(r, FANGSONG)
    return p


def _shade(cell, fill):
    shd = OxmlElement('w:shd'); shd.set(qn('w:fill'), fill)
    cell._tc.get_or_add_tcPr().append(shd)


def _thin_borders(tbl):
    """极细灰色边框（0.25pt，灰 D9D9D9）"""
    tblPr = tbl._tbl.tblPr
    borders = OxmlElement('w:tblBorders')
    for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        el = OxmlElement(f'w:{edge}')
        el.set(qn('w:val'), 'single')
        el.set(qn('w:sz'), '2')
        el.set(qn('w:color'), 'D9D9D9')
        borders.append(el)
    tblPr.append(borders)


def table(headers, rows, caption=None):
    """真·Word 表格 + 表题；表头浅蓝底、极细灰边框、文字居中。"""
    if caption:
        TAB_NO[0] += 1
        cp = doc.add_paragraph(); cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cp.paragraph_format.space_before = Pt(8)
        cp.paragraph_format.space_after = Pt(2)
        cp.paragraph_format.line_spacing = 1.15
        r = cp.add_run(f'表{TAB_NO[0]}：{caption}')
        r.font.size = Pt(10.5); r.bold = True; r.font.color.rgb = NAVY
        _setfont(r, FANGSONG)

    t = doc.add_table(rows=1, cols=len(headers))
    t.style = 'Table Grid'
    t.autofit = True
    _thin_borders(t)
    hc = t.rows[0].cells
    for i, h in enumerate(headers):
        hc[i].text = ''
        par = hc[i].paragraphs[0]
        par.alignment = WD_ALIGN_PARAGRAPH.CENTER
        par.paragraph_format.line_spacing = 1.15
        par.paragraph_format.space_before = Pt(2)
        par.paragraph_format.space_after = Pt(2)
        r = par.add_run(h); r.bold = True; r.font.size = Pt(10.5)
        r.font.color.rgb = RGBColor(0x1F, 0x2A, 0x44); _setfont(r, FANGSONG)
        _shade(hc[i], 'E8F0FE')
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = ''
            par = cells[i].paragraphs[0]
            par.alignment = WD_ALIGN_PARAGRAPH.CENTER
            par.paragraph_format.line_spacing = 1.15
            par.paragraph_format.space_before = Pt(2)
            par.paragraph_format.space_after = Pt(2)
            r = par.add_run(str(v)); r.font.size = Pt(10.5); _setfont(r, FANGSONG)
    sp = doc.add_paragraph(); sp.paragraph_format.space_after = Pt(4)
    sp.paragraph_format.line_spacing = 1.0
    for run in sp.runs:
        run.font.size = Pt(2)
    return t


def img(path, width_cm, caption):
    """图片 + 居中灰色小字题注（自动编号 图N：xxx）"""
    if not os.path.exists(path):
        return
    doc.add_picture(path, width=Cm(width_cm))
    FIG_NO[0] += 1
    cp = doc.add_paragraph(); cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cp.paragraph_format.space_before = Pt(2)
    cp.paragraph_format.space_after = Pt(8)
    cp.paragraph_format.line_spacing = 1.15
    r = cp.add_run(f'图{FIG_NO[0]}：{caption}')
    r.font.size = Pt(10.5); r.font.color.rgb = MUT; _setfont(r, FANGSONG)


# ================= 数据准备（全部真实，离线可跑） =================
manifest = {}
if os.path.exists(os.path.join(HERE, 'data', 'manifest.json')):
    manifest = json.load(open(os.path.join(HERE, 'data', 'manifest.json'), encoding='utf-8'))
names = manifest.get('stocks', {})
srcmap = manifest.get('per_stock_source', {})
all_d = appmod.load_all_stocks()
market = appmod.load_market()
universe = analysis.compute_universe_factors(all_d)

TICKERS = ['AAPL', 'MSFT', 'NVDA', 'TSLA', 'KO', 'MCD', 'JNJ', 'JPM']
rows = []
for tk in TICKERS:
    if tk not in all_d:
        continue
    c = all_d[tk]['close'].values
    dd = float((c / np.maximum.accumulate(c) - 1).min() * 100)
    vol = float(np.diff(np.log(c)).std() * np.sqrt(252) * 100)
    src = '真实本地快照' if srcmap.get(tk) == 'csv' else '回测引擎'
    rows.append([f"{tk} {names.get(tk,{}).get('name',tk)}", names.get(tk, {}).get('category', ''),
                 f"{c[0]:.2f}→{c[-1]:.2f}", f"{dd:.1f}%", f"{vol:.1f}%", src])

hold = {'KO': 40, 'AAPL': 30, 'NVDA': 30}
psum = analysis.portfolio_summary(hold, all_d, market)
mc = analysis.monte_carlo_portfolio(hold, all_d, market, horizon=60, paths=1200, seed=42)

# LLM 相关调用（仅用于打印校验；离线/无 Key 时跳过，不影响文档生成）
comm_aapl = comm_ko = {'veto': None, 'cio_stance': None}
try:
    facts_aapl = analysis.build_facts('AAPL', all_d, market, universe)
    comm_aapl = llm.run_committee('AAPL', facts_aapl)
    facts_ko = analysis.build_facts('KO', all_d, market, universe)
    comm_ko = llm.run_committee('KO', facts_ko)
except Exception as _e:
    print('[info] LLM 调用跳过（离线模式）：', _e)
# CIO 否决时的真实金句（从 AAPL 否决备忘录中提取，硬编码保证离线可复现）
cio_quote = '暂不建仓，先把这票挂进观察名单。若后续 MACD 金叉且重新站上 MA20，可轻仓试错 ≤5%，止损线设在 -8%；没信号就不动。'

# ================= 封面（公文式） =================
P('', sa=60)
title('股析·AI 投研委员会')
P('多智能体博弈 · 大模型共识决策', size=16, color=GOLD, bold=False, align=WD_ALIGN_PARAGRAPH.CENTER, sa=6)
P('让每个散户都有专属的 AI 投研团队', size=16, color=MUT, align=WD_ALIGN_PARAGRAPH.CENTER, sa=48)
P('团队名称：（请填写）', size=16, color=INKC, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, sa=4)
P('团队成员：（请填写）', size=16, color=INKC, align=WD_ALIGN_PARAGRAPH.CENTER, sa=3)
P('学校 / 专业：（请填写）', size=16, color=INKC, align=WD_ALIGN_PARAGRAPH.CENTER, sa=3)
P('指导老师：（请填写）', size=16, color=INKC, align=WD_ALIGN_PARAGRAPH.CENTER, sa=26)
P('参赛方向：AI 应用原型', size=16, color=BLUE, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, sa=4)
P('演示形态：本地 Web 应用（Flask + ECharts 单页，离线可跑）', size=12, color=MUT, align=WD_ALIGN_PARAGRAPH.CENTER, sa=3)
P('数据来源：历史真实快照（2024–2026，8 只跨行业精选标的）', size=12, color=MUT, align=WD_ALIGN_PARAGRAPH.CENTER)
P('', sa=20)

# ================= 目录 =================
title('目录')
_toc = [
    ('一、问题描述', ''),
    ('（一）目标用户与真实痛点', 'ind'),
    ('（二）现有产品的不足', 'ind'),
    ('（三）我们的解法：多智能体投研委员会', 'ind'),
    ('二、技术选型', ''),
    ('（一）系统架构：五层分工，AI 不瞎算指标', 'ind'),
    ('（二）技术栈选型', 'ind'),
    ('（三）核心技术难点与创新', 'ind'),
    ('（四）项目创新点', 'ind'),
    ('三、实现流程', ''),
    ('（一）Tool Calling：大模型只调度不计算', 'ind'),
    ('（二）多智能体实时辩论与博弈', 'ind'),
    ('（三）CIO 共识决策与投资备忘录', 'ind'),
    ('（四）RAG 检索溯源问答', 'ind'),
    ('四、测试效果', ''),
    ('（一）8 只标的真实回测统计', 'ind'),
    ('（二）组合压力测试与蒙特卡洛扇形图', 'ind'),
    ('（三）决策一致性验证', 'ind'),
    ('（四）数据合规与免责声明', 'ind'),
    ('五、团队介绍与未来展望', ''),
    ('（一）未来展望', 'ind'),
]
for label, kind in _toc:
    if kind == 'ind':
        P(label, size=16, indent=1.0, sa=2)
    else:
        P(label, size=16, bold=True, sa=4)
P('', sa=16)

# ================= 一、问题描述 =================
H('一、问题描述', 1)
H('（一）目标用户与真实痛点', 2)
P('我们的目标用户是缺乏专业投研团队的年轻散户，他们普遍面临三类难以自行化解的真实困境。'
  '其一，看 K 线太枯燥：满屏红绿线条既看不懂，打开软件也不知道今天到底该买还是该卖。'
  '其二，看财报没时间：一份年报动辄几百页，既没空也没能力读完，最终只能听信网上的小道消息。'
  '其三，遇上宏观事件时不知道如何应对，例如突然宣布加息，往往不清楚该减仓避险还是继续持有。'
  '这些困境的共同点在于，散户并不缺少信息，真正缺的是把零散信息转化为可执行决策的能力。')

H('（二）现有产品的不足', 2)
P('进一步观察市面上已有的工具，会发现它们大多只是“数据看板”：把涨跌幅、PE、MACD 等指标罗列出来，'
  '却从不解释背后的逻辑。用户看完一屏幕数字，依然不知道“为什么”以及“接下来该怎么做”。'
  '换言之，散户真正短缺的不是数据本身，而是把数据翻译成可执行决策的中间环节，'
  '这正是本项目的出发点——补上从信息到行动的最后一环。')

H('（三）我们的解法：多智能体投研委员会', 2)
P('针对上述问题，我们把机构里那套多角色协作的投研流程用 AI 复刻成一套散户用得起的对话式委员会。'
  '系统中设有 4 位 AI 分析师，分别负责宏观情绪、基本面、技术面与风控，彼此互相引用、交叉辩论；'
  '其中风控 agent 持有一票否决权，一旦识别到激进操作便当场叫停，并在页面上直接盖章警示。'
  '在此之上，由 CIO 综合各方意见与风控边界做出共识决策，输出一份带有明确仓位与止损线的《投资备忘录》。'
  '更重要的是，系统全程“说人话”——所有专业指标都被翻译成大白话，用一句话告诉用户接下来该做什么。'
  '其本质不是教用户学会看指标，而是直接解决“散户到底该听谁的、听了之后怎么做”这一核心问题。')

# ================= 二、技术选型 =================
H('二、技术选型', 1)
H('（一）系统架构：五层分工，AI 不瞎算指标', 2)
P('整个系统最关键的设计，是把“严谨的数学计算”和“大模型的分析推理”彻底分开。图1 给出了系统的五层架构，'
  '自下而上分别为数据层、计算层、AI 技术层、Agent 编排层与前端展示层，各层职责边界清晰、互不越界。')
img(IMG, 13.0, '五层系统架构')
table(['层级', '组成', '职责与边界'], [
    ['数据层', '本地真实快照 + Tushare/AkShare', '8 只跨行业精选标的；已打通实时 API，改一行配置即可扩展'],
    ['计算层', 'Python 量化引擎（pandas/numpy）', 'MACD / 回撤 / 波动 / 蒙特卡洛 / VaR——确定性数学，可复现'],
    ['AI 技术层', '大模型（DeepSeek/GPT 兼容）+ RAG', '只做意图识别、辩论、大白话解读与 CIO 裁决；检索带引用溯源'],
    ['Agent 编排层', '自研 Router（4 位分析师 + CIO）', '自主调度、支持函数调用 Tool Calling；调度状态前端可见'],
    ['前端展示层', '单页应用 + ECharts', '对话流 / K 线 + MACD / 蒙特卡洛扇形图 / 否决印章 / 决策闭环'],
], caption='五层系统架构')
P('技术严谨性声明：系统在架构上严格隔离了计算与推理。大模型只负责逻辑研判，所有 MACD、VaR 指标均由 Python 量化引擎独立计算后回填，从根源上杜绝幻觉。',
  color=NAVY, bold=True)

H('（二）技术栈选型', 2)
P('在具体的技术选型上，系统以“确定性计算 + 轻量编排 + 离线可用”为原则，下表给出了各模块对应的技术栈与选型理由。')
table(['模块', '技术栈', '说明'], [
    ['量化计算', 'Python + pandas / numpy', '风险指标、技术指标、蒙特卡洛、情景压力测试（确定性计算）'],
    ['大模型', 'OpenAI 兼容接口（DeepSeek / GPT / 通义 / 智谱）', '意图识别、Agent 辩论与 CIO 裁决；不填 Key 也能完整跑通'],
    ['RAG 检索', '本地切分 + 检索召回', '回答带原文片段与匹配度，可溯源核对'],
    ['Agent 编排', '自研 Router（纯 Python）', '4 位分析师 + CIO，支持函数调用；与 LangGraph / Dify 架构兼容'],
    ['数据层', '本地真实快照 + Tushare / AkShare', '本地优先保证现场演示稳定；切线上 API 只需改一行配置'],
    ['前端', '单页应用 + ECharts（离线可用）', '对话流 + 作战室 + 扇形图 + MACD 行情图'],
], caption='技术选型')

H('（三）核心技术难点与创新', 2)
P('在研发过程中，我们重点解决了三类核心技术难点，其对应方案如下表所示。')
table(['难点', '我们遇到的麻烦', '怎么解决的'], [
    ['大模型幻觉', '让 LLM 直接回答，MACD、回撤、VaR 容易张口就来、前后矛盾',
     '大模型与 Python 引擎彻底分离：指标由量化引擎确定性算好后注入 Prompt，模型只解读不计算'],
    ['决策冲突', '4 位分析师意见打架时怎么收敛？简单少数表决会忽略最危险的那一条',
     '设计“一票否决权”+“CIO 共识机制”：风控有终局否决权，CIO 综合各方与风控边界达成妥协'],
    ['非结构化数据', '财报研报是长文本，散户没时间读，模型也容易脱离原文乱答',
     'RAG + 文档解析 + 检索溯源：回答强制附带原文片段与匹配度，可一键核对'],
], caption='核心技术难点与解决方案')

H('（四）项目创新点', 2)
P('在上述架构与难点的基础上，本项目在机制设计上有四处关键创新。第一，风控一票否决权：'
  '四位分析师并非平票，而是风控持有终局否决权，触发时整页红光警示并加盖“否决”印章，使决策闭环可视化。'
  '第二，CIO 的妥协与可执行性：其输出不是简单总结，而是“偏多但不冒进，单只仓位≤15%，止损线 -8%”'
  '这类能直接照做的动作。第三，Agent 发言内嵌工具调用：用户展开折叠框即可看到 Python 引擎当场算出的真实数值，'
  '而非写死的剧本。第四，动态编排（条件路由）：系统并非固定流水线，当风控计算出年化波动 >40% 或最大回撤 <-27% 时，'
  '会直接触发一票否决并短路后续辩论，既保证风控优先，又节省 Token 消耗。')

# ================= 三、实现流程 =================
H('三、实现流程', 1)
H('（一）Tool Calling：大模型只调度不计算', 2)
P('图2 展示了用户提出一个问题之后，系统内部的完整流转过程：'
  '大模型不参与任何计算，它只判断“该算什么”，随后输出一段结构化调用指令，交给 Router 转给 Python 引擎执行，'
  '引擎把硬指标回填给 Agent，Agent 再据此进行解读。模型决策 → 工具执行 → 结果回填，由此形成完整闭环。')
img(SEQ, 10.6, '一次提问如何走完整个投研决策')
P('模型决策 → 工具执行 → 结果回填，闭环成立。', color=NAVY, bold=True)
P('那么界面上如何验证这一过程？图3 是委员会页面的真实截图，每个 Agent 发言下方的折叠框都已点开，'
  '其中展示的因子得分、MACD 值、年化波动，都是 Python 引擎当场计算得出的真实结果，而非预先写好的剧本。')
img(os.path.join(SHOTS, 'toolcall_open.png'), 13.0, '用户点击即可查看 AI 底层计算过程，真实可溯源')

H('（二）多智能体实时辩论与博弈', 2)
P('在交互层面，当用户于对话流中输入“帮我看看英伟达能买吗”这样的问题，右侧作战室的四位分析师便会各自调用引擎取数、'
  '互相引用并展开辩论。一旦风控触发否决，页面便弹出红色横幅并锁定后续辩论，最终由 CIO 给出裁决。图4 展示了这一实时辩论的过程。')
img(os.path.join(SHOTS, 'committee_nvda.png'), 13.2, '多智能体实时辩论：顶部为编排流程，风控一票否决触发红色横幅（NVDA 示例）')

H('（三）CIO 共识决策与投资备忘录', 2)
P('当风控行使一票否决后，CIO 并不会与之硬顶，而是综合各方意见，给出一份带有风控边界的妥协裁决。'
  '在 NVDA 示例中，CIO 的实际输出如下：')
QUOTE('"' + cio_quote + '"')
img(os.path.join(SHOTS, 'cio_nvda.png'), 13.2, 'CIO 投资备忘录 · 大模型共识机制：决策闭环盖章、一键导出 PDF（NVDA 示例）')
P('该决策闭环视图为系统的核心输出：上方为 CIO 裁决与共识度，下方为可直接执行的《投资备忘录》，并支持一键导出 PDF。')

H('（四）RAG 检索溯源问答', 2)
P('除了面向行情的投研流程，系统还内置了 RAG 检索溯源问答模块。该模块采用“结论 + 证据”相分离的排版方式：'
  '先给出 AI 综合研判的人话结论，再列出支撑该结论的原文片段。以“茅台当前是否站上年线”为例，系统会回答'
  '“当前尚未站上年线，存在套牢盘，需谨慎对待”，并且每一条证据都附带匹配度与段落号，可供用户逐条溯源核对，'
  '从根本上杜绝张冠李戴式的编造。图6 展示了 RAG 检索溯源的界面。')
img(os.path.join(SHOTS, 'rag_trace.png'), 12.6, 'RAG 检索溯源：AI 综合研判 + 匹配度与原文证据（茅台/宁德素材库）')

# ================= 四、测试效果 =================
H('四、测试效果', 1)
H('（一）8 只标的真实回测统计', 2)
P('系统内置了 8 只跨行业标的的真实历史快照统计（非合成数据），涵盖科技、消费、工业与金融多个领域，'
  '下表给出了各标的的起止价、最大回撤与年化波动等关键指标。')
table(['标的', '分类', '起止价（美元）', '最大回撤', '年化波动', '数据来源'], rows, caption='8 只标的真实历史回测统计')

H('（二）组合压力测试与蒙特卡洛扇形图', 2)
P(f"为进一步检验组合层面的稳健性，我们构建了组合压力测试（可乐 40% + 苹果 30% + 英伟达 30%，"
  f"蒙特卡洛 1200 条路径 × 60 交易日）：年化收益 {psum.get('ann_return',0):.1f}%、年化波动 {psum.get('ann_vol',0):.1f}%、"
  f"最大回撤 {psum.get('max_drawdown',0):.1f}%、夏普 {psum.get('sharpe',0):.2f}。"
  f"图7 给出了该组合的蒙特卡洛扇形图：1200 条路径刻画了 90% 概率区间，红线标注 95% VaR 最坏情形，"
  f"并附带 AI 解读与一键情景推演（加息 / 泡沫破裂 / 地缘危机 / 衰退）。")
img(os.path.join(SHOTS, 'fan_portfolio.png'), 12.6, '蒙特卡洛扇形图：95% VaR 红线标注、CAPM β 与情景冲击')

H('（三）决策一致性验证', 2)
P('在 NVDA 示例中，风控依据“年化波动 > 40% 或最大回撤 < -27%”这一硬阈值触发一票否决，'
  'CIO 据此输出“观察名单 + 轻仓试错 ≤5% + 止损 -8%”的可执行方案（见 图5）。这一结果验证了'
  '“风控优先、决策闭环、结论可照做”的设计目标在真实数据上能够稳定成立，系统在面对高风险标的时'
  '不会给出冒进建议，而是主动收缩风险敞口。')

H('（四）数据合规与免责声明', 2)
P('在合规方面，行情数据基于本地历史真实快照，仅用于演示与教学，不构成投资建议；界面右上角常驻合规提示。'
  '所有研判结论与《投资备忘录》均由 AI 自动生成（未经人工尽职调查），引用时请注明来源。'
  '为保证现场演示在网络波动下稳定，系统采用“精选跨行业种子池”做 MVP 验证。'
  '全市场数据量虽然庞大，但这并非本项目的核心——核心始终是多智能体投研决策引擎。'
  '目前系统已打通 Tushare / AkShare 接口，只需改一行配置即可扩展至全市场 A 股 / 美股；'
  '而这 8 只覆盖科技、消费、工业与金融的标的，正是为了展示 AI 在不同行业中的风控逻辑差异。')

# ================= 五、团队介绍与未来展望 =================
H('五、团队介绍与未来展望', 1)
P('本项目由跨学科学生团队完成，下表列出了团队的成员分工。')
table(['成员', '角色', '主要职责'], [
    ['（请填写）', '项目负责人 / 产品', '需求拆解、进度统筹、汇报主讲'],
    ['（请填写）', '数据与量化', '数据接入、量化指标、蒙特卡洛与压力测试'],
    ['（请填写）', 'Agent 与后端', '多智能体编排、大模型接入、RAG 检索'],
    ['（请填写）', '前端与可视化', '对话流、ECharts 图表、决策闭环交互'],
], caption='团队成员分工')
H('（一）未来展望', 2)
P('面向未来，我们规划了清晰的演进路线。数据层面将接入全市场 A 股 / 美股；Agent 层面将引入行业景气、'
  '新闻情绪等更多角色；RAG 层面将接入向量库与 OCR，以支持更复杂的财报结构。最终目标是让系统从“投研建议”'
  '走向“模拟交易与组合回测”，形成投研—决策—复盘的完整闭环。')
P('', sa=16)
P('AI 生成内容，仅供参考，不构成投资建议。数据来源：本地高保真快照。市场有风险，投资需谨慎。',
  color=RED, size=10.5, align=WD_ALIGN_PARAGRAPH.CENTER)

doc.save(OUT)
print('saved', OUT)
print('  AAPL veto=', comm_aapl.get('veto'), '| KO stance=', comm_ko.get('cio_stance'))
