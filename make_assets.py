# -*- coding: utf-8 -*-
"""生成《股析·AI投研委员会》系统架构图 —— 五层结构（前端 / Agent编排 / AI技术 / 计算 / 数据）。
输出 architecture.png，供项目说明书 / PPT 直接使用。所有技术栈与实际实现一致（不虚报）。"""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = "C:/Windows/Fonts/simhei.ttf"
W, H = 1000, 920
BG = (255, 255, 255)
INK = (26, 32, 48)
MUT = (107, 118, 134)
NAVY = (22, 35, 74)
BLUE = (47, 111, 237)
GOLD = (201, 147, 31)
PURPLE = (124, 92, 214)
GREEN = (26, 158, 95)
RED = (192, 43, 43)
CARD = (255, 255, 255)
PANEL = (246, 248, 251)


def font(sz):
    return ImageFont.truetype(FONT, sz)


def round_rect(d, xy, r, fill=None, outline=None, width=2):
    d.rounded_rectangle(xy, radius=r, fill=fill, outline=outline, width=width)


def tcenter(d, box, text, f, fill=INK):
    l, t, r, b = box
    w = d.textlength(text, font=f)
    x = l + (r - l - w) / 2
    y = t + (b - t - f.size) / 2
    d.text((x, y), text, font=f, fill=fill)


def draw_card(d, x, y, w, h, title, sub, accent):
    round_rect(d, (x, y, x + w, y + h), 10, fill=CARD, outline=accent, width=2)
    tcenter(d, (x, y + 8, x + w, y + 30), title, font(14), fill=INK)
    if sub:
        tcenter(d, (x, y + h - 24, x + w, y + h - 3), sub, font(10), fill=MUT)


# (层名, 颜色, 右侧说明, 卡片列表[(标题, 副标题)])
BANDS = [
    ("前端展示层", BLUE, "单页应用 + ECharts：对话流 / K线+MACD / 蒙特卡洛扇形图",
     [("对话投研流", "像聊天一样提问"), ("投研作战室", "四 Agent 实时辩论"), ("风险可视化", "否决印章 / 决策闭环")]),
    ("Agent 编排层", PURPLE, "自研 Router 自主调度：四大 Analyst Agent + CIO，支持函数调用（Tool Calling）",
     [("宏观情绪 Agent", "调市场情绪引擎"), ("基本面 Agent", "调多因子模型"), ("技术面 Agent", "调 MACD 引擎"),
      ("风控 Agent", "一票否决权"), ("CIO 首席投资官", "共识机制裁决")]),
    ("AI 技术层", GOLD, "大模型只做解读与决策（不计算指标） + RAG 检索溯源",
     [("LLM 推理", "DeepSeek / GPT 兼容"), ("RAG 检索", "向量召回 + 引用溯源"), ("Prompt 工程", "人设 / 冲突 / 妥协")]),
    ("计算层 · Python 量化引擎", NAVY, "严谨数学全部在此完成：确定性计算，可复现、零幻觉",
     [("MACD(12,26,9)", "金叉/死叉判定"), ("最大回撤 / 波动", "下行风险与波动率"), ("蒙特卡洛", "千条路径扇形图"),
      ("VaR / 情景压力", "加息·衰退冲击")]),
    ("数据层", GREEN, "精选跨行业真实历史快照（本地），已打通 Tushare / AkShare 接口可无缝扩展",
     [("本地真实快照", "8 只跨行业种子池"), ("Tushare / AkShare", "实时 API 一键切换")]),
]

img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)

tcenter(d, (0, 14, W, 44), "股析 · AI 投研委员会 —— 五层系统架构", font(24), fill=NAVY)
tcenter(d, (0, 46, W, 70), "明确边界：量化引擎负责严谨数学计算（绝不幻觉）；大模型只负责解读、辩论与决策", font(12), fill=MUT)

ft = font(14)
fn = font(10)
y = 84
band_boxes = []
for name, color, note, cards in BANDS:
    bh = 34 + 18 + 70  # 标题条 + 说明 + 卡片区（保证卡片标题与副标题不重叠）
    round_rect(d, (30, y, W - 30, y + bh), 13, fill=PANEL, outline=color, width=2)
    bar_w = d.textlength(name, font=ft) + 30
    round_rect(d, (30, y, 30 + bar_w, y + 32), 9, fill=color)
    tcenter(d, (30, y, 30 + bar_w, y + 32), name, ft, fill=(255, 255, 255))
    d.text((30 + bar_w + 12, y + 10), note, font=fn, fill=MUT)
    n = len(cards)
    gap = 14
    cw = (W - 60 - (n - 1) * gap) / n
    cy = y + 52
    ch = bh - 62
    for k, (t1, t2) in enumerate(cards):
        draw_card(d, 30 + k * (cw + gap), cy, cw, ch, t1, t2, color)
    band_boxes.append((y, y + bh, color))
    y += bh + 24  # 24px 留给箭头

# 层间箭头
for (t0, b0, c0), (t1, b1, c1) in zip(band_boxes, band_boxes[1:]):
    cx = W / 2
    d.line([(cx, b0 + 2), (cx, t1 - 12)], fill=c0, width=3)
    d.polygon([(cx - 7, t1 - 12), (cx + 7, t1 - 12), (cx, t1 - 1)], fill=c0)
tcenter(d, (30, band_boxes[-1][1] + 4, W - 30, H - 46),
        "技术严谨性声明：AI 只负责分析和辩论，绝对不瞎算指标；MACD、VaR 等严谨数据全部由 Python 引擎计算后作为 Context 喂给 LLM。",
        font(13), fill=INK)
tcenter(d, (30, H - 42, W - 30, H - 18),
        "杜绝“写死剧本 / 大模型幻觉”——指标确定性可复现，LLM 只做解读与共识决策。",
        font(13), fill=MUT)

out = os.path.join(HERE, "architecture.png")
img.save(out)
print("saved", out, img.size)


# ================= 第二张图：系统操作时序图（竖向流程） =================
def gen_sequence():
    W2, H2 = 900, 720
    img2 = Image.new("RGB", (W2, H2), BG)
    d2 = ImageDraw.Draw(img2)
    tcenter(d2, (0, 14, W2, 44), "系统操作时序：一次提问如何走完整个投研决策", font(22), fill=NAVY)
    tcenter(d2, (0, 46, W2, 70), "每一步都可追溯：意图识别 → 工具取数 → 多 Agent 辩论 → 风控拦截 → 共识裁决 → 输出", font(12), fill=MUT)
    steps = [
        ("①", "👤 用户输入", "「帮我看看英伟达能买吗？」", BLUE),
        ("②", "🧠 大模型意图识别", "解析问题、锁定标的（NVDA）", PURPLE),
        ("③", "🔧 Tool Calling 取数", "调度 Python 量化引擎：MACD / 回撤 / 波动", GOLD),
        ("④", "⚖️ 多 Agent 并发辩论", "宏观 / 基本面 / 技术面 / 风控 交叉引用", PURPLE),
        ("⑤", "🛡 风控拦截", "突破阈值 → 行使一票否决权", RED),
        ("⑥", "👔 CIO 共识裁决", "综合各方 + 风控边界 → 妥协实操决策", NAVY),
        ("⑦", "📄 输出《投资备忘录》", "仓位 / 止损线，可一键导出 PDF", GREEN),
    ]
    y = 86
    bh, gap = 68, 12
    for i, (num, title, sub, color) in enumerate(steps):
        round_rect(d2, (60, y, W2 - 60, y + bh), 12, fill=CARD, outline=color, width=2)
        # 序号圆
        d2.ellipse((78, y + bh/2 - 18, 78 + 36, y + bh/2 + 18), fill=color)
        tcenter(d2, (78, y + bh/2 - 18, 114, y + bh/2 + 18), num, font(15), fill=(255, 255, 255))
        d2.text((132, y + 12), title, font=font(16), fill=INK)
        d2.text((132, y + 40), sub, font=font(12), fill=MUT)
        if i < len(steps) - 1:
            cx = W2 / 2
            d2.line([(cx, y + bh + 2), (cx, y + bh + gap - 6)], fill=MUT, width=3)
            d2.polygon([(cx - 7, y + bh + gap - 8), (cx + 7, y + bh + gap - 8), (cx, y + bh + gap)], fill=MUT)
        y += bh + gap
    out2 = os.path.join(HERE, "sequence.png")
    img2.save(out2)
    print("saved", out2, img2.size)


gen_sequence()
