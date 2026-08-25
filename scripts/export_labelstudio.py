# -*- coding: utf-8 -*-
"""把金答案核对 60 题导出为 Label Studio 任务包 + 标注配置。
数据源:study_logs/wikistate_gold_rating.html 内嵌 ITEMS(与评分页同源同序)。
产出:data/labelstudio_tasks.json(任务)+ data/labelstudio_config.xml(界面)。
"""
import html
import json
import re
from pathlib import Path

ROOT = Path(r"D:\ZZL_cluade")
src = (ROOT / "study_logs/wikistate_gold_rating.html").read_text(encoding="utf-8")
items = json.loads(re.search(r"const ITEMS\s*=\s*(\[.*?\]);", src, re.S).group(1))
conv_block = re.search(r"CONV\s*=\s*\{(.*?)\};", src, re.S).group(1)
CONV = dict(re.findall(r"(\w+):\s*\"(.*?)\"", conv_block, re.S))

tasks = []
for it in items:
    rows = "".join(
        f"<tr><td style='white-space:nowrap;font-weight:600'>{html.escape(c['date'])}</td>"
        f"<td>{html.escape(c['value'])}</td>"
        f"<td style='color:#667'>{html.escape(c['span'])}</td></tr>"
        for c in it["chain"])
    chain_html = (
        "<table border='1' cellpadding='6' style='border-collapse:collapse;"
        "font-size:13px;width:100%'>"
        "<tr><th>日期</th><th>值</th><th>对话原句(锚点)</th></tr>"
        f"{rows}</table>"
        f"<p style='color:#886;font-size:12.5px'>{html.escape(CONV.get(it['type'], ''))}</p>")
    tasks.append({"data": {
        "item_id": it["id"],
        "qtype": it["type"],
        "question": it["q"],
        "gold": str(it["gold"]),
        "chain_html": chain_html,
    }})
(ROOT / "data/labelstudio_tasks.json").write_text(
    json.dumps(tasks, ensure_ascii=False, indent=1), encoding="utf-8")

CONFIG = """<View>
  <Style>
    .gold-box{background:#eef3e8;border-radius:6px;padding:8px 12px;font-size:16px}
  </Style>
  <Header value="题型:$qtype   |   编号:$item_id"/>
  <Text name="q" value="$question"/>
  <View className="gold-box">
    <Header size="4" value="标准答案(gold):$gold"/>
  </View>
  <HyperText name="chain" value="$chain_html"/>
  <Header size="4" value="按上方状态链与约定,标准答案是否正确?"/>
  <Choices name="verdict" toName="q" choice="single" required="true">
    <Choice value="一致" hotkey="1"/>
    <Choice value="不一致" hotkey="2"/>
    <Choice value="不确定" hotkey="3"/>
  </Choices>
  <Header size="5" value="备注(「不一致」时请写一句为什么;对约定本身有异议也写这里)"/>
  <TextArea name="note" toName="q" rows="2" maxSubmissions="1"/>
</View>"""
(ROOT / "data/labelstudio_config.xml").write_text(CONFIG, encoding="utf-8")
print(f"tasks: {len(tasks)} -> data/labelstudio_tasks.json; config written")
