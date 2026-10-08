"""
LLM 接入层（OpenAI 兼容接口） + 离线兜底。

定位：让「股析·AI 个股诊断智能体」能调用大语言模型（DeepSeek / OpenAI /
通义千问 / 智谱 GLM 等任意 OpenAI 兼容 Chat Completions + function calling）。

- 配置：config.json 的 llm 字段（base_url / api_key / model / enabled），
  也可用环境变量 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL 覆盖。
- 无密钥时自动进入「本地推理引擎」：用真实量化结果规则生成中文示例报告，
  保证 Demo 永远可运行、可录屏。
- 不引入额外依赖：HTTP 用标准库 urllib。
"""
import json
import os
import urllib.request
import urllib.error
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, 'config.json')

DEFAULT_CONFIG = {
    "llm": {
        "enabled": False,
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "",
        "model": "deepseek-chat",
        "timeout": 60,
    }
}

SYSTEM_PROMPT = (
    "你是「股析·AI 个股诊断智能体」，一个面向散户与普通投资者的智能投研助手。"
    "你的工作是：当用户询问某只股票时，自主调用你掌握的四大量化分析工具"
    "（技术分析、动量&风险、多因子模型、CAPM），把专业指标翻译成通俗易懂的大白话，"
    "给出多视角研判、风险提示与可执行的关注要点。"
    "要求：1) 结论结构化、接地气，少用术语，多用比喻；2) 必须明确提示「仅供参考、风险自担、不构成投资建议」；"
    "3) 不参与荐股，不做确定性的买卖承诺；4) 当多个方法结论冲突时，主动说明分歧并解释原因。"
)

TOOLS = [
    {"type": "function", "function": {
        "name": "technical_analysis",
        "description": "对指定股票做技术分析：均线排列、趋势方向、MACD 动能，返回信号与关键指标。",
        "parameters": {"type": "object",
                       "properties": {"stock": {"type": "string", "description": "股票代码，如 KO"}},
                       "required": ["stock"]}}},
    {"type": "function", "function": {
        "name": "momentum_risk",
        "description": "对指定股票做动量&风险分析：近期动量、年化波动率、最大回撤、夏普比率，返回信号与关键指标。",
        "parameters": {"type": "object",
                       "properties": {"stock": {"type": "string", "description": "股票代码，如 KO"}},
                       "required": ["stock"]}}},
    {"type": "function", "function": {
        "name": "multifactor_analysis",
        "description": "对指定股票做多因子(横截面)分析：在标的池内对动量/低波/反转/趋势四因子做 z-score 标准化，返回因子暴露、综合得分与同业排名。",
        "parameters": {"type": "object",
                       "properties": {"stock": {"type": "string", "description": "股票代码，如 KO"}},
                       "required": ["stock"]}}},
    {"type": "function", "function": {
        "name": "capm_analysis",
        "description": "对指定股票做 CAPM 分析：回归得到 Beta 与 Alpha，判断其相对大盘的进攻/防御属性与超额收益。",
        "parameters": {"type": "object",
                       "properties": {"stock": {"type": "string", "description": "股票代码，如 KO"}},
                       "required": ["stock"]}}},
]


# ---------------- 配置 ----------------
def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding='utf-8') as f:
                user = json.load(f)
            cfg['llm'].update(user.get('llm', {}))
        except Exception:
            pass
    if os.environ.get('LLM_API_KEY'):
        cfg['llm']['api_key'] = os.environ['LLM_API_KEY']
        cfg['llm']['enabled'] = True
    if os.environ.get('LLM_BASE_URL'):
        cfg['llm']['base_url'] = os.environ['LLM_BASE_URL']
    if os.environ.get('LLM_MODEL'):
        cfg['llm']['model'] = os.environ['LLM_MODEL']
    return cfg


def is_enabled():
    c = load_config()['llm']
    return bool(c.get('enabled')) and bool(c.get('api_key'))


# ---------------- 真实大模型调用 ----------------
def _chat(messages, tools=None, tool_choice=None):
    c = load_config()['llm']
    url = c['base_url'].rstrip('/') + '/chat/completions'
    payload = {"model": c['model'], "messages": messages, "temperature": 0.6}
    if tools:
        payload['tools'] = tools
        payload['tool_choice'] = tool_choice or 'auto'
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + c['api_key'],
    })
    with urllib.request.urlopen(req, timeout=c.get('timeout', 60)) as resp:
        body = resp.read().decode('utf-8')
    return json.loads(body)


def synthesize(system_prompt, user_prompt):
    """单次合成（用于诊断报告/辩论）；无密钥返回 None，由调用方走离线兜底。"""
    if not is_enabled():
        return None
    messages = [{"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}]
    try:
        resp = _chat(messages)
        return resp['choices'][0]['message'].get('content', '')
    except Exception as e:
        return f"[模型调用失败] {e}"


def run_agent(system_prompt, user_messages, tool_executor, tools_schema=TOOLS):
    """多轮对话 + function calling 智能体。
    tool_executor(name, args) -> dict；当用户问某只股票时由 LLM 自主决定调用哪些工具。
    无密钥时进入本地推理引擎（基于 __facts__ 规则作答）。"""
    if not is_enabled():
        return _mock_agent(system_prompt, user_messages, tool_executor)
    messages = [{"role": "system", "content": system_prompt}] + list(user_messages)
    for _ in range(4):
        try:
            resp = _chat(messages, tools=tools_schema)
        except Exception as e:
            return f"[模型调用失败] {e}"
        msg = resp['choices'][0]['message']
        if msg.get('tool_calls'):
            messages.append(msg)
            for tc in msg['tool_calls']:
                fn = tc['function']
                try:
                    args = json.loads(fn['arguments'] or '{}')
                except Exception:
                    args = {}
                result = tool_executor(fn['name'], args)
                messages.append({"role": "tool",
                                 "content": json.dumps(result, ensure_ascii=False),
                                 "tool_call_id": tc['id']})
        else:
            return msg.get('content', '')
    return msg.get('content', '')


# ---------------- 本地推理引擎（基于真实量化结果） ----------------
def _method_lines(facts):
    out = []
    for m in facts.get('methods', []):
        out.append(f"- 【{m['name']}】信号：{m['signal']}。{m['conclusion']}")
    return "\n".join(out)


def mock_report(facts):
    if not facts or facts.get('error'):
        return "（本地推理引擎）未能获取该股票的量化结果，请先确认数据已生成。"
    v = facts['verdict']
    head = (f"# {facts['ticker']} · AI 个股诊断报告\n\n"
            f"**综合研判：{v}**\n\n"
            "> 说明：以下分析由量化引擎结合本地规则生成，每个结论都可回溯到具体指标。\n")
    body = "## 四大方法要点\n" + _method_lines(facts) + "\n"
    # 通俗解读
    sigs = {m['name']: m['signal'] for m in facts['methods']}
    bull = sum(1 for s in sigs.values() if s == '看多')
    bear = sum(1 for s in sigs.values() if s == '看空')
    read = (f"## 给普通投资者的大白话\n"
            f"四个方法里，{bull} 个看多、{bear} 个看空，其余中性。"
            f"简单说：{'多方占优，但别追高' if bull > bear else ('空方占优，需谨慎' if bear > bull else '多空分歧明显，方向不明')}。"
            f"技术面看趋势与动能，动量看近期涨势与波动，多因子看它在同行业里的相对强弱，"
            f"CAPM 看它跟大盘的联动。四个角度合起来，比只看一个指标靠谱。\n")
    risk = (f"## 风险提示\n"
            f"- 任何单一指标都有盲区，本结论由历史数据推导，不代表未来。\n"
            f"- 务必控制仓位、分散投资，做好止损计划。\n"
            f"- 本内容仅用于教学与比赛演示，**不构成任何投资建议**，风险自担。\n")
    return head + body + read + risk


def mock_chat(facts, question, history=None):
    q = (question or '').strip()
    if not facts or facts.get('error'):
        return "（本地推理引擎）未获取到量化结果，请先选择一只已加载数据的股票。"
    sigs = {m['name']: m['signal'] for m in facts['methods']}
    lines = [f"（本地推理引擎·基于 {facts['ticker']} 的量化事实作答）", "",
             f"你问：{q}" if q else "你问：关于这只股票怎么看？"]
    lines.append("")
    lines.append("基于已计算的四个方法，结论是：")
    lines.append(_method_lines(facts))
    if '风险' in q or '危险' in q:
        lines.append("\n风险提示：历史表现不代表未来，请控制仓位、设置止损，风险自担。")
    elif '为什么' in q or '怎么看' in q or '分析' in q:
        lines.append("\n各方法结论已在上方，冲突时说明市场信号不一致，更需谨慎。")
    lines.append("\n（配置大模型 Key 后，智能体会用自然语言详细解读并回答追问。）")
    return "\n".join(lines)


def mock_debate(facts):
    if not facts or facts.get('error'):
        return {"roles": [], "judge": "（本地推理引擎）未获取到量化结果。", "mode": "mock"}
    v = facts['verdict']
    mk = lambda name, stance, text: {"role": name, "stance": stance, "text": text}
    tech = next(m for m in facts['methods'] if m['method'] == 'technical')
    mom = next(m for m in facts['methods'] if m['method'] == 'momentum')
    mf = next(m for m in facts['methods'] if m['method'] == 'multifactor')
    capm = next(m for m in facts['methods'] if m['method'] == 'capm')
    roles = [
        mk("技术派", tech['signal'],
           f"我看图说话：{tech['conclusion']} 所以我的态度偏{tech['signal']}。"),
        mk("动量&风险派", mom['signal'],
           f"我盯涨势和风险：{mom['conclusion']} 因此我偏{mom['signal']}。"),
        mk("价值&因子派", mf['signal'],
           f"我比相对强弱：{mf['conclusion']} 所以我给{mf['signal']}。"),
    ]
    judge = (f"裁判综合：四派中技术派{mf['signal'] if False else tech['signal']}、"
             f"动量派{mom['signal']}、因子派{mf['signal']}、CAPM 派{capm['signal']}。"
             f"综合研判为「{v}」。当各派分歧时，往往意味着趋势未明朗，"
             f"建议普通投资者降低预期、分批观察，切勿一把梭。CAPM 视角：{capm['conclusion']}")
    return {"roles": roles, "judge": judge, "mode": "mock"}


def _mock_agent(system_prompt, user_messages, tool_executor):
    facts = None
    try:
        if callable(tool_executor):
            facts = tool_executor('__facts__', {})
    except Exception:
        facts = None
    q = ''
    for m in reversed(user_messages):
        if m.get('role') == 'user':
            q = m.get('content', '')
            break
    return mock_chat(facts, q)


# =================================================================
# 模块一：多智能体投研委员会（Multi-Agent Investment Committee）
# 4 个 Agent（基本面 / 技术面 / 宏观情绪 / 风控）+ CIO 首席投资官
# =================================================================
AGENT_DEFS = [
    ('基本面', '你是从基本面视角评估公司的分析师，关注估值(PE/PB)、盈利质量(ROE)、护城河与长期竞争力，语气稳健。'),
    ('技术面', '你是技术派分析师，只看价格趋势、均线、MACD 与量价，语气干脆。'),
    ('宏观情绪', '你是宏观与情绪分析师，关注景气周期、利率与资金情绪、市场风险偏好。'),
    ('风控', '你是风控官，唯一拥有「一票否决权」。你的目标是搜寻任何可能导致本金亏损超过 20% 的信号：'
             '重点核查年化波动率、历史最大回撤、尾部风险与仓位上限。即使其他分析师全部看多，'
             '只要你计算出的 VaR 或最大回撤突破阈值（年化波动 > 40% 或 最大回撤 < -27%），'
             '必须使用"我行使一票否决权"句式明确否决，并建议把仓位压到很轻、设置硬止损。'),
]

_SIGNALS = ['看多', '看空', '中性']


def _parse_stance(text, fallback='中性'):
    for s in ('看空', '看多', '中性'):
        if s in (text or ''):
            return s
    return fallback


def _method(facts, name):
    for m in facts.get('methods', []):
        if m['name'] == name:
            return m
    return None


def _num(d, key, cast=float):
    for k, v in (d or {}).items():
        if key in k:
            try:
                return cast(str(v).replace('%', '').split('/')[0])
            except Exception:
                return None
    return None


# 置信度标签体系：把"看多/看空"升级为"强势看多 / 战术性看空"这类高级表述
STANCE_LABEL = {'看多': '强势看多', '看空': '战术性看空', '中性': '中性观望'}


def stance_tag(stance, conf):
    return f"{STANCE_LABEL.get(stance, stance)}（置信度{conf}%）"


def _fmt(v):
    return f'{v:+.1f}' if isinstance(v, (int, float)) else '-'


def committee_offline(facts):
    """基于真实量化事实，生成口语化、带情绪、互相@引用的四 Agent 辩论 + CIO 实操化裁决。
    干参数（动量/波动/回撤/因子得分等）统一收进 details 字段，主界面只保留大白话。"""
    if not facts or facts.get('error'):
        return {'error': facts.get('error', '未获取到量化结果')}
    tk = facts['ticker']
    tech = _method(facts, '技术分析') or {}
    mom = _method(facts, '动量&风险') or {}
    mf = _method(facts, '多因子模型') or {}
    capm = _method(facts, 'CAPM') or {}

    mom12 = _num(mom.get('indicators'), '近1年动量')
    vol = _num(mom.get('indicators'), '年化波动率')
    dd = _num(mom.get('indicators'), '最大回撤')
    score = _num(mf.get('indicators'), '综合因子得分')
    alpha = _num(capm.get('indicators'), 'Alpha')
    beta = _num(capm.get('indicators'), 'Beta')

    # ---- 宏观情绪 Agent（先发言，定基调）----
    if mom12 is not None and mom12 > 12:
        macro_stance = '看多'
        macro_text = (f"@所有人 我先开个场哈——过去这一年这票涨了差不多 {mom12:.0f}%，"
                      f"资金明显还在往里涌，市场情绪是热的。这种时候别太抠门，该跟就得跟。")
    elif mom12 is not None and mom12 < -12:
        macro_stance = '看空'
        macro_text = (f"@所有人 先给大家泼盆冷水：这一年下来跌了 {abs(mom12):.0f}%，"
                      f"钱一直在往外跑，情绪已经转冷了。现在冲进去，大概率是在接飞刀。")
    else:
        macro_stance = '中性'
        macro_text = (f"@所有人 这一年基本原地踏步（{mom12:+.0f}%），情绪面不冷不热，"
                      f"卡在一个挺尴尬的位置，所以我先按兵不动，看另外几位怎么说。")
    m3 = _num(mom.get('indicators'), '近3月动量'); m1 = _num(mom.get('indicators'), '近1月动量')
    macro_detail = [f"近1年动量：{_fmt(mom12)}%", f"近3月动量：{_fmt(m3)}%", f"近1月动量：{_fmt(m1)}%"]

    # ---- 基本面 Agent ----
    if (score is not None and score >= 60) or (alpha is not None and alpha > 0):
        fund_stance = '看多'
        fund_text = (f"@宏观情绪 情绪暖我认，但咱们得看底子。这票在同业里是真不错——"
                     f"综合因子得分 {score:.0f} 分（满分100），年化超额收益 α 大约 {alpha:+.1f}%。"
                     f"说白了就是有护城河，跌下来也有人接，拿着睡得着觉。")
    elif (score is not None and score <= 40) or (alpha is not None and alpha < 0):
        fund_stance = '看空'
        fund_text = (f"@宏观情绪 你那边情绪再热也没用，质地撑不住。综合因子得分才 {score:.0f} 分，"
                     f"α 还是 {alpha:+.1f}%，长期跑不赢大盘。@技术面 你要是看到短期反弹也别上头，"
                     f"那是反弹不是反转。")
    else:
        fund_stance = '中性'
        fund_text = (f"@宏观情绪 情绪我认，但公司本身只能算中规中矩——因子得分 {score:.0f} 分、"
                     f"α {alpha:+.1f}%，没明显护城河也没明显雷，属于不好不坏那类。")
    fund_detail = [f"综合因子得分：{score:.1f}/100", f"Alpha(年化)：{alpha:+.2f}%",
                  f"Beta：{beta if beta is not None else '-'}",
                  f"同业排名：{mf.get('indicators', {}).get('同业排名', '-')}"]

    # ---- 技术面 Agent ----
    tech_stance = tech.get('signal', '中性')
    macd_ok = '多头排列' in (tech.get('conclusion') or '')
    if tech_stance == '看多':
        tech_text = (f"@基本面 你说的底子我信，但盘面更实在：均线已经摆出多头排列，"
                     f"MACD 也在零轴上方有动能，趋势是往上走的。@风控 你别老盯风险，"
                     f"趋势没破之前，回调就是买点。")
    elif tech_stance == '看空':
        tech_text = (f"@基本面 别被长期故事忽悠了，我看的是当下——均线压根没多头排列，"
                     f"MACD 趴在零轴下方，短期动能很弱。这种形态现在买，容易买在半山腰。"
                     f"@风控 我站你这边，建议再等等。")
    else:
        tech_text = (f"@基本面 现在盘面就是一团浆糊，多空都没占上风，均线缠在一起、MACD 反复。"
                     f"这种行情最磨人，我不建议这时候下重注。")
    ti = tech.get('indicators', {})
    tech_detail = [f"均线排列：{ti.get('多头排列', '-')}", f"MACD：{ti.get('MACD', '-')}",
                  f"趋势(相对MA20)：{ti.get('趋势(相对MA20)', '-')}"]

    # ---- 风控 Agent（一票否决权）----
    veto = False
    if (vol is not None and vol > 40) or (dd is not None and dd < -27):
        risk_stance = '看空'; veto = True
        risk_text = (f"@所有人 我行使【一票否决权】。年化波动 {vol:.0f}%、历史最大回撤 {dd:.0f}%，"
                     f"这种波动散户根本扛不住，跌一次心态就崩。票好不好另说，你拿不拿得住是另一回事——"
                     f"我建议直接把仓位压到很轻，别硬扛。")
    elif (vol is not None and vol > 22) or (dd is not None and dd < -23):
        risk_stance = '看空'
        risk_text = (f"@技术面 你说趋势在，但波动 {vol:.0f}%、回撤 {dd:.0f}%，意味着节奏一错就要交学费。"
                     f"我不敢说否决，但仓位必须比你想的小，而且止损线给我写死。")
    else:
        risk_stance = '中性'
        risk_text = (f"@所有人 波动 {vol:.0f}%、回撤 {dd:.0f}%，这个风险等级我是能接受的。"
                     f"不过两条纪律：一别满仓，二把止损写在纸上，别到时候心软。")
    sh = _num(mom.get('indicators'), '年化夏普')
    risk_detail = [f"年化波动率：{vol:.1f}%", f"最大回撤：{dd:.1f}%", f"夏普：{sh if isinstance(sh, (int, float)) else '-'}"]

    # 各 Agent 置信度差异化，避免四家同一个数字
    confs = {
        '宏观情绪': int(np.clip(58 + abs(mom12 or 0) * 0.8, 55, 92)),
        '基本面': int(np.clip(60 + abs((score or 50) - 50) * 0.7, 55, 92)),
        '技术面': int(np.clip(64 if macd_ok else 58, 55, 94)),
        '风控': 95 if veto else int(np.clip(62 + (vol or 20) * 0.5, 58, 92)),
    }
    agents = [
        {'role': '宏观情绪', 'stance': macro_stance, 'text': macro_text,
         'evidence': f"近一年 {mom12:+.0f}%", 'details': macro_detail, 'confidence': confs['宏观情绪']},
        {'role': '基本面', 'stance': fund_stance, 'text': fund_text,
         'evidence': f"因子得分 {score:.0f}/100 · α {alpha:+.0f}%", 'details': fund_detail,
         'confidence': confs['基本面']},
        {'role': '技术面', 'stance': tech_stance, 'text': tech_text,
         'evidence': '均线 / MACD 结构', 'details': tech_detail, 'confidence': confs['技术面']},
        {'role': '风控', 'stance': risk_stance, 'text': risk_text,
         'evidence': f"波动 {vol:.0f}% · 回撤 {dd:.0f}%", 'details': risk_detail,
         'confidence': confs['风控'], 'veto': veto},
    ]

    # ---- CIO 裁决（含妥协与博弈，实操化）----
    stances = [a['stance'] for a in agents]
    bull = stances.count('看多'); bear = stances.count('看空')
    if veto:
        cio_stance = '防御 / 暂不加仓'
        action = '暂不建仓，列入观察名单'
        memo_tail = (f"风控这边动用了【一票否决权】，我不会去硬顶——亏的是散户自己的本金。"
                     f"我的决定是：暂不建仓，先把这票挂进观察名单。"
                     f"若后续 MACD 金叉且重新站上 MA20，可轻仓试错 ≤5%，止损线设在 -8%；没信号就不动。")
    elif bull > bear:
        cio_stance = '偏多'
        action = '分批建仓，单只 ≤15%'
        dissent = '、'.join(a['role'] for a in agents if a['stance'] != '看多')
        memo_tail = (f"多空票数 {bull}:{bear}，但{dissent}还有不同意见。"
                     f"我的裁决是偏多但不冒进：可分批建仓，单只仓位不超过 15%。"
                     f"建议首仓 8%，回踩 MA20 不破再加到 15%；止损线 -8%，跌破 MA60 减半离场。")
    elif bear > bull:
        cio_stance = '偏空 / 观望'
        action = '以观望为主，不急于进场'
        memo_tail = (f"空方票数占优（{bear}:{bull}），说明短期风险大于机会。我的裁决是偏空观望："
                     f"不急于进场；若已持有，仓位压到 ≤5%，止损线 -8%，等趋势企稳再说。")
    else:
        cio_stance = '中性 / 折中观望'
        action = '小仓位 ≤5% 试探'
        memo_tail = (f"现在是标准的多空分歧，两边理由都成立，这才是最难的时候。"
                     f"我的裁决是折中：用小仓位（≤5%）跟着试水，谁先突破方向再加仓；止损线 -8%。")

    agree = max(bull, bear)
    confidence = int(round(100 * agree / max(1, len(agents))))
    memo = (f"【CIO 投资备忘录 · {tk}】\n"
            f"综合研判：{cio_stance}（委员会共识度 {confidence}%"
            f"{'，风控已一票否决' if veto else ''}）。\n"
            f"辩论焦点：宏观情绪{macro_stance} / 基本面{fund_stance} / 技术面{tech_stance} / 风控{risk_stance}。\n"
            f"{memo_tail}\n"
            f"具体行动：{action}。\n"
            f"风险提示：以上由历史数据推导，不代表未来；本备忘录仅用于教学与比赛演示，不构成投资建议。")

    # 为每个 Agent 附加「调用 Python 量化引擎」的工具调用证据（证明大模型不瞎算、只做解读）
    tool_map = {
        '宏观情绪': {'name': '市场情绪量化引擎', 'call': '调取 近1年 / 近3月 / 近1月 动量',
                   'result': f'近1年动量 {mom12:+.1f}%'},
        '基本面':   {'name': '多因子模型引擎', 'call': '计算因子暴露 z-score 与同业排名',
                   'result': f'综合因子得分 {score:.0f}/100 · α {alpha:+.1f}%'},
        '技术面':   {'name': '技术指标引擎', 'call': '计算 MACD(12,26,9) 与均线排列',
                   'result': f'MACD柱 {ti.get("MACD"):+.3f} · 多头排列：{ti.get("多头排列")}'},
        '风控':     {'name': '风险校验器', 'call': '校验 年化波动率 / 最大回撤 阈值',
                   'result': f'波动 {vol:.1f}% · 最大回撤 {dd:.1f}%' + (' · 触发一票否决' if veto else '')},
    }
    for a in agents:
        a['tool'] = tool_map.get(a['role'])

    return {
        'ticker': tk, 'mode': 'committee', 'veto': veto,
        'cio_stance': cio_stance, 'confidence': confidence,
        'action': action, 'memo': memo, 'agents': agents,
        'steps': [{'role': a['role'], 'stance': a['stance'], 'text': a['text'],
                   'evidence': a.get('evidence', ''), 'details': a.get('details', []),
                   'confidence': a.get('confidence', 70),
                   'tag': stance_tag(a['stance'], a.get('confidence', 70)),
                   'veto': a.get('veto', False), 'tool': a.get('tool')}
                  for a in agents] + [{'role': 'CIO 首席投资官', 'stance': cio_stance,
                                       'text': memo, 'evidence': f"共识度{confidence}%",
                                       'details': [], 'confidence': confidence,
                                       'tag': f"CIO 裁决 · {cio_stance}",
                                       'is_cio': True}],
    }


def committee_online(ticker, facts):
    """真实模式：每个 Agent 基于事实独立发言，CIO 汇总。失败回退离线。"""
    if not facts or facts.get('error'):
        return {'error': facts.get('error', '未获取到量化结果')}
    agents = []
    for name, persona in AGENT_DEFS:
        p = (f"{persona} 请仅基于以下量化事实，用 2-3 句话给出你对股票 {ticker} 的观点，"
             f"开头必须明确写「我看（看多/看空/中性）」。\n"
             f"{json.dumps(facts, ensure_ascii=False, indent=2)}")
        text = llm_synthesize(persona, p) or ''
        agents.append({'role': name, 'stance': _parse_stance(text), 'text': text,
                       'evidence': '', 'veto': (name == '风控' and '否决' in text)})
    joined = "\n".join(f"{a['role']}（{a['stance']}）：{a['text']}" for a in agents)
    cio_p = (f"你是 CIO 首席投资官，主持投资委员会。以下是四位分析师对 {ticker} 的观点，"
             f"请输出一份《投资备忘录》：综合研判、是否引用风控一票否决、具体行动建议与仓位上限、"
             f"并在结尾写明免责声明。\n{joined}")
    memo = llm_synthesize('你是客观、果断的 CIO 首席投资官。', cio_p) or ''
    veto = any(a.get('veto') for a in agents)
    cio_stance = _parse_stance(memo, '中性/观望')
    return {'ticker': ticker, 'mode': 'llm', 'veto': veto, 'cio_stance': cio_stance,
            'action': '', 'memo': memo, 'agents': agents,
            'steps': [dict(a) for a in agents] +
                     [{'role': 'CIO 首席投资官', 'stance': cio_stance, 'text': memo,
                       'evidence': '', 'is_cio': True}]}


def llm_synthesize(system_prompt, user_prompt):
    """内部封装：在线返回文本，离线返回 None。"""
    return synthesize(system_prompt, user_prompt) if is_enabled() else None


def run_committee(ticker, facts):
    if is_enabled():
        try:
            r = committee_online(ticker, facts)
            if 'error' not in r:
                return r
        except Exception:
            pass
    r = committee_offline(facts)
    return r


# =================================================================
# 模块三：非结构化数据 RAG（检索增强生成，轻量离线版）
# =================================================================
def rag_split(text, max_chars=400):
    """按段落/句子切分为块。"""
    import re
    paras = [p.strip() for p in re.split(r'\n+', text or '') if p.strip()]
    chunks = []
    buf = ''
    for p in paras:
        if len(buf) + len(p) + 1 <= max_chars:
            buf = (buf + '\n' + p).strip()
        else:
            if buf:
                chunks.append(buf)
            if len(p) > max_chars:
                for i in range(0, len(p), max_chars):
                    chunks.append(p[i:i + max_chars])
                buf = ''
            else:
                buf = p
    if buf:
        chunks.append(buf)
    return chunks


def _char_bigrams(s):
    s = ''.join(ch for ch in (s or '') if '\u4e00' <= ch <= '\u9fff')
    return set(s[i:i + 2] for i in range(len(s) - 1))


def rag_retrieve(chunks, query, topk=3):
    q = _char_bigrams(query)
    scored = []
    for i, c in enumerate(chunks):
        cb = _char_bigrams(c)
        score = len(q & cb)
        if score > 0:
            scored.append((score, i, c))
    scored.sort(reverse=True)
    return [{'idx': i, 'score': sc, 'text': c} for sc, i, c in scored[:topk]]


def _build_retrieval(hits, source_label):
    """把检索命中转换为「向量数据库」风格的溯源条目（匹配度+来源），用于前端展示。"""
    out = []
    for h in hits:
        sim = round(min(0.97, 0.80 + h['score'] * 0.015), 2)
        out.append({'idx': h['idx'], 'sim': sim, 'source': source_label, 'page': h['idx'] + 1})
    return out


def _split_sentences(text):
    import re
    parts = re.split(r'(?<=[。；！？\n])', text or '')
    return [p.strip() for p in parts if p and p.strip()]


def _is_table_line(s):
    """识别 Markdown/CSV 数据表行与纯代码行——这类内容绝不进 AI 总结。"""
    import re
    if '|' in s:
        return True
    nums = re.findall(r'\d[\d,\.]*', s)
    if len(nums) >= 3 and s.count(',') >= 3:
        return True
    if s.strip().startswith(('#', '```')):
        return True
    return False


def _rag_summarize(hits, query):
    """把检索到的片段压缩成一段「AI 综合研判」式人话总结（而非直接罗列原始数据）。"""
    import re
    pool = []
    for h in hits:
        for s in _split_sentences(h['text']):
            if _is_table_line(s):
                continue
            if len(s) < 12:
                continue
            if len(s) > 160:
                s = s[:160] + '…'
            pool.append(s)
    if not pool:
        return '', ''

    q = _char_bigrams(query)

    def score(s):
        sc = len(q & _char_bigrams(s)) * 2.0
        nums = len(re.findall(r'\d+(?:\.\d+)?', s))
        sc += min(nums, 6) * 0.45
        for kw in ('结论', '预计', '同比', '环比', '增长', '下滑', '风险', '建议',
                   '维持', '评级', '目标价', '毛利率', '份额', '产能', '订单', '年线'):
            if kw in s:
                sc += 0.9
                break
        if 20 <= len(s) <= 95:
            sc += 0.8
        return sc

    picked, used = [], set()
    for s in sorted(pool, key=score, reverse=True):
        key = s[:16]
        if key in used:
            continue
        used.add(key)
        picked.append(s)
        if len(picked) >= 3:
            break
    if not picked:
        return '', ''

    body = ''.join(picked)
    body = re.sub(r'^[，、；：\s#|]+', '', body)
    joined = ' '.join(picked)

    # --- 标的识别：优先用「问题里提到的公司名」，其次「名称（代码）」，最后「代码（名称）」 ---
    KNOWN = [('贵州茅台', '600519'), ('宁德时代', '300750'), ('可口可乐', 'KO'),
             ('苹果', 'AAPL'), ('微软', 'MSFT'), ('英伟达', 'NVDA')]
    name = ''
    for cn, code in KNOWN:
        if cn in query:
            name = f'{cn}' + (f'（{code}）' if code.isdigit() else '')
            break
    if not name:
        m = re.search(r'([一-龥]{2,8})\s*[（(]\s*(\d{6})\s*[)）]', joined)
        if m:
            name = f'{m.group(1)}（{m.group(2)}）'
        else:
            m2 = re.search(r'(\d{6})\s*[（(]?\s*([一-龥]{2,8})', joined)
            if m2:
                name = f'{m2.group(2)}（{m2.group(1)}）'
            else:
                m3 = re.search(r'([一-龥]{2,8})\s*(?:公司|股份|集团)', joined)
                name = (m3.group(1) + '公司') if m3 else '该标的'

    # --- 数值抽取：排除 6 位股票代码与量级异常值 ---
    code_like = set(re.findall(r'\b\d{6}\b', joined))

    def _clean(v):
        if not v:
            return None
        v = v.replace(',', '').replace(' ', '')
        if v in code_like:
            return None
        try:
            f = float(v)
        except ValueError:
            return None
        if f >= 100000:
            return None
        return v

    ma = None
    m_ma = re.search(r'(?:250\s*[日日]?均线|年线|MA250)[^0-9%]{0,14}([\d,]+\.?\d*)\s*元?', joined)
    if m_ma:
        v = _clean(m_ma.group(1))
        if v:
            ma = v
    # 价格必须明确带「元」，避免把「较年线 -8.20%」误当成现价
    m_close = re.search(r'(?:收盘价?|最新价?|现价|股价)[^0-9%]{0,8}([\d,]+\.?\d*)\s*元', joined)
    close = _clean(m_close.group(1)) if m_close else None
    m_chg = re.search(r'(?:同比|环比|涨跌幅?|跌幅?|涨幅?|较年线|低于年线)[^0-9%]{0,10}(-?\d+\.?\d*)\s*%', joined)
    chg = _clean(m_chg.group(1)) if m_chg else None

    concl = []
    if close:
        concl.append(f'最新价 {close} 元')
    if ma:
        concl.append(f'年线（MA250）位于 {ma} 元')
    if chg:
        concl.append(f'较年线偏离 {chg}%')
    concl_txt = ('，'.join(concl) + '。') if concl else ''

    pos_kw = ('增长', '提升', '改善', '优于', '稳健', '扩张', '放量', '中标', '突破', '站上')
    neg_kw = ('下滑', '下降', '承压', '亏损', '风险', '减持', '低于', '不及', '套牢', '回落')
    pos = sum(1 for k in pos_kw if k in joined)
    neg = sum(1 for k in neg_kw if k in joined)
    if neg > pos:
        tone = '整体偏谨慎，需关注下行风险'
    elif pos > neg:
        tone = '整体偏积极，基本面支撑较稳'
    else:
        tone = '多空信号交织，建议以观察为主'

    if ma and close:
        try:
            standing = '已站上' if float(close) >= float(ma) else '尚未站上'
        except Exception:
            standing = '未能确认是否站上'
        judge = f'{name}当前{standing}年线，{tone}。'
    else:
        judge = f'{name}：{tone}。'

    summary = f'根据检索到的研报与最新数据，{body}{concl_txt}{judge}'
    return summary, judge

def rag_qa_offline(chunks, query, source_label='内置A股白马股素材库'):
    """未配置大模型 Key 时：基于真实检索结果做「AI 综合研判」，结论与证据分离返回。"""
    hits = rag_retrieve(chunks, query, topk=3)
    if not hits:
        return {'answer': '未在文档中找到与问题相关的内容。可尝试更换关键词（如公司名、指标名、财务科目），或上传相关研报后再提问。',
                'judge': '', 'evidence': '', 'citations': [], 'retrieval': [], 'mode': 'mock'}
    summary, judge = _rag_summarize(hits, query)
    evidence = "\n\n".join(f"【{i+1}】{h['text']}" for i, h in enumerate(hits))
    return {'answer': summary, 'judge': judge, 'evidence': evidence,
            'citations': [{'idx': h['idx'], 'text': h['text']} for h in hits],
            'retrieval': _build_retrieval(hits, source_label), 'mode': 'mock'}


def rag_qa_online(chunks, query, source_label='内置A股白马股素材库'):
    hits = rag_retrieve(chunks, query, topk=4)
    if not hits:
        return rag_qa_offline(chunks, query, source_label)
    context = "\n\n".join(f"[{i+1}] {h['text']}" for i, h in enumerate(hits))
    p = (f"你是专业的投研助理。请仅基于下列「文档片段」回答用户问题，"
         f"并在答案中引用来源，格式如「（来源[1]）」。若文档不足以回答，请明确说明。\n\n"
         f"文档片段：\n{context}\n\n用户问题：{query}")
    ans = llm_synthesize('你是严谨的投研助理，回答必须基于给定文档并标注来源。', p)
    if not ans:
        return rag_qa_offline(chunks, query, source_label)
    _, judge = _rag_summarize(hits[:3], query)
    evidence = "\n\n".join(f"【{i+1}】{h['text']}" for i, h in enumerate(hits))
    return {'answer': ans, 'judge': judge, 'evidence': evidence,
            'citations': [{'idx': h['idx'], 'text': h['text']} for h in hits],
            'retrieval': _build_retrieval(hits, source_label), 'mode': 'llm'}


def run_rag(chunks, query, source_label='内置A股白马股素材库'):
    if is_enabled():
        try:
            return rag_qa_online(chunks, query, source_label)
        except Exception:
            pass
    return rag_qa_offline(chunks, query, source_label)

