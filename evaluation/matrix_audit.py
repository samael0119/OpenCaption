"""Auditable 3x3 cross-validation matrix evaluation (2026-11-26).

Combines:
  1. Full automated metrics across all 9 cells (WER, Chinese validity, copied-English rate,
     /no_think leak rate, MT P50/P95, ASR+MT P50/P95, model disk size, peak RSS).
  2. Strict unit-by-unit semantic judgments on the frozen 62 units / 119 atoms (same rubric as
     cs-domain-20261020/product_round_v2) for all 3 ASR x HY-MT1.5-1.8B cells plus the top Qwen3-1.7B cell.
"""

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation/results/matrix-20261126"
REF_PATH = ROOT / "evaluation/results/cs-domain-20261020/product_round_v2/reference.json"
BASE_AUDIT = ROOT / "evaluation/results/cs-domain-20261020/product_round_v2/audit.json"

JUDGMENTS = {
    "whisper_large_v3_turbo_q5__hy_mt_1.8b": {
        "clip:01": ([False], [False], [True], ["identity"], "donk->Doc，爆头对"),
        "clip:02": ([True, True], [], [], ["relation"], "门边暴露与9-12杀手均对，但句尾把tN1R误连为该杀手"),
        "clip:03": ([True, False], [True, True], [False], ["number"], "tN1R与sh1ro并列对，但15 frags错译为第15名"),
        "clip:04": ([True, True], [True], [], [], "xertioN还击子弹并带来空地"),
        "clip:05": ([False], [], [False], ["term"], "bomb错受术语表影响译作包点而非雷包"),
        "clip:06": ([True, True], [True], [True, False], [], "不确定中路声音+sh1ro鸟狙均对"),
        "clip:07": ([True, True], [True], [True], [], "换人+donk早期开局击杀"),
        "clip:08": ([False], [True], [False], ["term"], "B site仅译作那个包点，漏B区"),
        "clip:09": ([False, False], [True], [False, False, True], ["meaning"], "xertioN拥有bomb错译为强大武器，漏鸟狙"),
        "clip:10": ([True], [True], [], [], "xertioN最终必须进行连接"),
        "clip:11": ([False, True, True], [], [False, True, False], ["term", "meaning"], "cat->盖板，鸟狙和长门对"),
        "clip:12": ([True, False], [False], [], ["identity"], "错过时机对，xertioN->Zershin"),
        "clip:13": ([False], [], [False], ["meaning"], "必须行动但漏拿下包点"),
        "clip:14": ([False, False], [False], [False], ["identity", "meaning"], "漏小道受挫与xertioN主语"),
        "clip:15": ([True, True], [True], [], [], "胆怯坐回放弃机会，Spirit成功领先"),
        "clip:16": ([False, True], [], [], ["meaning"], "天才与疯狂走钢丝对，not get cleared错译为界限不被突破"),
        "clip:17": ([True, True], [True], [True], [], "风险值得一试，对Spirit拥有人数优势"),
        "clip:18": ([True, True], [], [], [], "心情糟糕/打得差+真讨厌这张地图"),
        "clip:19": ([False, True], [], [], ["meaning"], "both sides->boasting吹嘘，滑稽可笑对"),
        "clip:20": ([True, True], [True], [], [], "承认问题是第一步，Dust2显然是他的问题"),
        "clip:21": ([True, True], [True], [], [], "永远无法摆脱的问题，donk在角落里"),
        "clip:22": ([True], [], [], [], "包点玩家几乎独自完成工作"),
        "clip:23": ([False], [True], [], ["meaning"], "zont1x对，但clean shots out of Zontix错译为从手中清除目标"),
        "clip:24": ([False], [False], [], ["identity"], "donk->Domk"),
        "clip:25": ([], [], [], [], "存疑排除"),
        "clip:26": ([True], [True], [True], [], "Spirit设定的早期节奏，CT区"),
        "clip:27": ([True], [], [], [], "开场动作有点侵略性"),
        "clip:28": ([False, True], [True, True], [False, True, True], ["unsupported"], "sh1ro/donk/隧道/手枪对，但受静态术语表影响凭空加补枪射击"),
        "clip:29": ([False], [False], [], ["identity"], "MOUZ->用鼠标点击"),
        "clip_match_demo2:01": ([False, True, True], [False], [False, False], ["identity", "unsupported"], "漏yuurih且受静态术语表影响插入分差缩到一分"),
        "clip_match_demo2:02": ([True, True], [True, True], [], [], "molodoy所期待，kyousuke穿过场地瞄准目标"),
        "clip_match_demo2:03": ([True, False], [True, False], [False], ["identity"], "molodoy开局对，FURIA->Uri"),
        "clip_match_demo2:04": ([False, True], [False, True], [], ["identity"], "把FURIA自选Mirage错补成Falcons选择Mirage"),
        "clip_match_demo2:05": ([True, False], [True], [True], ["meaning"], "NiKo烟雾边缘扳回对，漏烟雾波动提供视野的因果"),
        "clip_match_demo2:06": ([True], [True], [], [], "TeSeS轮到上场了"),
        "clip_match_demo2:07": ([True, False, False], [False], [], ["identity"], "排好队对，m0NESY->Modesty"),
        "clip_match_demo2:08": ([True, False], [], [], ["meaning"], "默契配合对，baits->beats"),
        "clip_match_demo2:09": ([False, True], [False], [True], ["identity"], "无可用补枪对，漏YEKINDAR"),
        "clip_match_demo2:10": ([True, True], [True], [False], [], "yuurih仍在宫殿区域才刚开始发挥作用"),
        "clip_match_demo2:11": ([True, True, False], [True], [False], ["meaning"], "炸弹在NiKo旁边+火焰尴尬对，漏安全避火"),
        "clip_match_demo2:12": ([True, False], [True], [], ["meaning"], "yuurih被抓住对，漏没打出作用"),
        "clip_match_demo3:01": ([True, False, True], [True, True], [False], ["number"], "karrigan死人+b1t完成任务对，7HP->7到8英尺"),
        "clip_match_demo3:02": ([False, True, False], [False], [False, False, False], ["identity", "term"], "iM->Dimron，漏Hell"),
        "clip_match_demo3:03": ([True], [], [], [], "他有这个胆量吗？他能坚持住吗？"),
        "clip_match_demo3:04": ([True, False], [False, True], [True], ["identity"], "爆头/makazze对，jcobbb->jacob且未连接击杀对象"),
        "clip_match_demo3:05": ([True, False, False], [False], [False], ["identity", "unsupported"], "第二枪被挡住对，但受静态术语表泄露插入队内沟通/人数优势"),
        "clip_match_demo3:06": ([False, True], [True, False, True], [True], ["identity"], "frozen/broky/通风口对，w0nderful错译为情况不错"),
        "clip_match_demo3:07": ([False, True], [], [], ["unsupported"], "诱饵转移注意力对，但Spotter受术语表泄露错译为鸟狙"),
        "clip_match_demo3:08": ([False, False], [False], [], ["identity"], "frozen被听成broky"),
        "clip_match_demo3:09": ([True], [True], [], [], "frozen让分差缩小到了1分"),
        "clip_match_demo3:10": ([False, False], [False], [], ["identity", "meaning"], "jcobbb->Jacob，nonsense->废话"),
        "clip_interview_niko:01": ([True, True, True], [True], [True], [], "昨天对阵G2，评分1.54，保持良好状态"),
        "clip_interview_niko:02": ([True, False], [], [], ["meaning"], "再次表扬我对，working->bargain划算选择"),
        "clip_interview_niko:03": ([True, True], [], [], [], "继续计算数据+问昨天现场观众看法与场馆氛围"),
        "clip_interview_niko:04": ([True, True], [True], [], [], "知道会这么好+每次来葡萄牙氛围非常棒"),
        "clip_interview_niko:05": ([True, True], [], [], [], "比赛愉快充满激情，希望今天开心"),
        "clip_interview_niko:06": ([True, True, True], [True, True], [True], [], "观众最爱+Falcons对抗Spirit最重要+上次Major非常接近"),
        "clip_interview_niko:07": ([False, True], [False], [], ["identity"], "C10把Spirit状态最好错替为Falcons状态最好；艰难比赛对"),
        "clip_interview_niko:08": ([True], [], [], [], "需要做的就是像昨天那样"),
        "clip_interview_niko:09": ([True, True, True, True], [], [True], [], "充沛精力+队内沟通充分+正确决策+积极心态全对"),
        "clip_interview_niko:10": ([True, True], [], [], ["unsupported"], "输赢不重要+每轮100%状态对，但C14尾部多补了一句保持队内沟通"),
        "clip_interview_niko:11": ([True, True], [], [False], [], "至关重要+大赛中表现最出色"),
        "clip_interview_niko:12": ([True], [], [], ["unsupported"], "如果今天也能做到对，但C17把Context采访头带入译文"),
    },
    "whisper_small_q5__hy_mt_1.8b": {
        "clip:01": ([True], [True], [True], ["unsupported"], "donk爆头对，但多译而torzsi则不会"),
        "clip:02": ([True, True], [], [], [], "门附近暴露在杀手面前，9和12（轻微译作9点12点但数字保留）"),
        "clip:03": ([False, True], [False, True], [False], ["identity"], "漏tN1R，sh1ro与15分对"),
        "clip:04": ([False, True], [False], [], ["identity"], "xertioN->zertion，空地对"),
        "clip:05": ([True], [], [False], [], "对决中发现炸弹"),
        "clip:06": ([False, False], [False], [True, False], ["identity", "meaning"], "mid cross->中区炸弹受伤，sh1ro->Fero"),
        "clip:07": ([False, False], [False], [True], ["identity"], "donk->dock被译为他被击倒"),
        "clip:08": ([False], [False], [False], ["identity", "term"], "漏B与donk"),
        "clip:09": ([True, False], [True], [False, False, False], ["meaning"], "xertioN拥有炸弹对，漏鸟狙与M4"),
        "clip:10": ([False], [False], [], ["identity"], "xertioN变成我们"),
        "clip:11": ([False, False, False], [], [False, False, False], ["meaning"], "cat->猫板，漏后半句鸟狙和A大门"),
        "clip:12": ([False, False], [False], [], ["identity", "meaning"], "漏错过时机，xertioN->zershin"),
        "clip:13": ([True], [], [True], [], "必须行动，占领包点机会"),
        "clip:14": ([False, False], [False], [False], ["identity", "meaning"], "cat players->球员人数有限，xertioN->Zershin"),
        "clip:15": ([False, True], [True], [], ["negation"], "把never saw a chance翻成看到了攻击的机会（否定反转），Spirit领先对"),
        "clip:16": ([True, True], [], [], [], "天才与疯狂之间平衡+后期才登场希望不被清除"),
        "clip:17": ([True, True], [True], [True], [], "风险值得+对Spirit人数优势"),
        "clip:18": ([True, False], [], [], ["meaning"], "烦躁对，漏讨厌这张图"),
        "clip:19": ([False, False], [], [], ["meaning"], "both sides->这个姿势"),
        "clip:20": ([True, True], [True], [], [], "承认问题是第一步，Dust2是难题"),
        "clip:21": ([True, True], [True], [], [], "永远无法摆脱，Donk在角落里"),
        "clip:22": ([False], [], [], ["meaning"], "site player already got the job错听成already dead已经死了"),
        "clip:23": ([True], [True], [], [], "不错zont1x，干净利落射击"),
        "clip:24": ([True], [True], [], [], "donk等待等等我的击杀数"),
        "clip:25": ([], [], [], [], "存疑排除"),
        "clip:26": ([True], [True], [True], [], "Spirit早期节奏+CT区"),
        "clip:27": ([True], [], [], [], "开场动作需要进攻性打法"),
        "clip:28": ([True, False], [True, True], [False, True, True], ["term"], "sh1ro中路+donk隧道对，Berettas->只露出脸"),
        "clip:29": ([False], [False], [], ["identity"], "MOUZ->按着鼠标"),
        "clip_match_demo2:01": ([False, False, True], [False], [False, False], ["identity", "meaning"], "漏yuurih和边路，仅中路混战沟通混乱对"),
        "clip_match_demo2:02": ([True, True], [True, True], [], [], "molodoy期待，kyousuke走过瞄准目标"),
        "clip_match_demo2:03": ([True, False], [True, False], [False], ["identity"], "molodoy率先进攻，FURIA->yuurih"),
        "clip_match_demo2:04": ([False, False], [False, False], [], ["identity"], "错成Falcons发起攻击且漏Mirage"),
        "clip_match_demo2:05": ([True, False], [True], [True], ["unsupported"], "NiKo烟雾边缘扳回对，但术语表泄露加从包点且漏烟雾波动因果"),
        "clip_match_demo2:06": ([False], [True], [], ["meaning"], "TeSeS up to bat->一直处于下风位置"),
        "clip_match_demo2:07": ([True, False, True], [False], [], ["identity"], "排好队+绞肉机对，m0NESY->Modesty"),
        "clip_match_demo2:08": ([True, False], [], [], ["meaning"], "默契团结对，baits->BATEMIN"),
        "clip_match_demo2:09": ([False, True], [False], [True], ["identity"], "无补枪对，YEKINDAR->Yukinda"),
        "clip_match_demo2:10": ([True, True], [True], [False], [], "yuurih才开始激活宫殿"),
        "clip_match_demo2:11": ([True, True, False], [True], [False], ["unsupported"], "炸弹在NiKo旁+火焰尴尬对，但safe from flames受术语表泄露错译为从那些鸟狙那里"),
        "clip_match_demo2:12": ([False, False], [True], [], ["relation"], "主客体反转成他被yuurih抓住"),
        "clip_match_demo3:01": ([True, False, False], [True, False], [False], ["identity", "number", "unsupported"], "karrigan对，7HP->7-8英尺，bit错受术语表泄露译作鸟狙"),
        "clip_match_demo3:02": ([False, True, False], [False], [True, False, False], ["identity", "term"], "大厅和分散对，漏iM和Heaven/Hell"),
        "clip_match_demo3:03": ([True], [], [], [], "他有这个胆量吗？他能坚持住吗？"),
        "clip_match_demo3:04": ([True, False], [True, False], [True], ["identity"], "jcobbb爆头对，漏makazze"),
        "clip_match_demo3:05": ([True, False, False], [False], [False], ["identity"], "阻止进攻对，karrigan错替换"),
        "clip_match_demo3:06": ([False, False], [True, False, False], [True], ["identity"], "frozen击倒+通风口对，漏w0nderful与broky"),
        "clip_match_demo3:07": ([False, True], [], [], ["unsupported"], "诱饵转移注意力对，Spotter错译为鸟狙"),
        "clip_match_demo3:08": ([False, False], [False], [], ["identity"], "漏frozen"),
        "clip_match_demo3:09": ([False], [True], [], ["meaning"], "frozen让w0变成了w0--"),
        "clip_match_demo3:10": ([False, False], [False], [], ["identity", "meaning"], "jcobbb->Jacob"),
        "clip_interview_niko:01": ([False, False, True], [False], [False], ["identity", "number"], "漏G2与1.54，仅保留保持精神状态"),
        "clip_interview_niko:02": ([True, False], [], [], ["meaning"], "表扬我对，working->boring无聊"),
        "clip_interview_niko:03": ([True, True], [], [], [], "继续计算数据+问昨天观众看法与氛围"),
        "clip_interview_niko:04": ([True, True], [True], [], [], "知道会这么好+每次来葡萄牙氛围很棒"),
        "clip_interview_niko:05": ([True, True], [], [], ["unsupported"], "打球愉快有活力+希望今天充满乐趣，但C6受术语表泄露插入Falcons队内沟通充分"),
        "clip_interview_niko:06": ([True, True, True], [True, True], [True], [], "最喜爱选手+Falcons对Spirit+去年Major接近"),
        "clip_interview_niko:07": ([False, True], [False], [], ["identity"], "Spirit错替为Falcons状态最好；艰难比赛对"),
        "clip_interview_niko:08": ([True], [], [], [], "需要像昨天那样"),
        "clip_interview_niko:09": ([True, True, True, True], [], [True], [], "充沛精力+队内沟通充分+正确决策+积极心态全对"),
        "clip_interview_niko:10": ([True, True], [], [], ["unsupported"], "输赢无所谓+每轮100%对，但C14尾部补入保持队内沟通充分"),
        "clip_interview_niko:11": ([True, True], [], [True], [], "关键+Major表现最出色"),
        "clip_interview_niko:12": ([False], [], [], ["meaning"], "尾句听成Thank you for watching"),
    },
    "parakeet_tdt_v3_int8__hy_mt_1.8b": {
        "clip:01": ([True], [True], [True], [], "果然donk会找到那个爆头"),
        "clip:02": ([True, False], [], [], ["number"], "门边暴露对，9-12错译为九岁和十二岁"),
        "clip:03": ([False, True], [False, True], [False], ["identity"], "Shiro与15分对，漏tN1R"),
        "clip:04": ([False, False], [False], [], ["identity", "meaning"], "C5几乎空白，回显上一句"),
        "clip:05": ([False], [], [False], ["meaning"], "遗漏bomb spotted"),
        "clip:06": ([False, False], [False], [True, False], ["identity", "meaning"], "mid cross->伤害，sh1ro->英雄"),
        "clip:07": ([False, True], [True], [True], ["meaning"], "donk首杀对，漏换防"),
        "clip:08": ([False], [True], [False], ["term"], "B site仅译作包点漏B"),
        "clip:09": ([False, False], [False], [False, True, False], ["identity", "meaning"], "xertioN->Zertion，漏M4"),
        "clip:10": ([False], [False], [], ["identity"], "漏xertioN主语"),
        "clip:11": ([False, True, True], [], [False, True, False], ["term", "meaning"], "cat->盖板，鸟狙和长门对"),
        "clip:12": ([True, False], [False], [], ["identity"], "错过时机对，xertioN->Zerchin"),
        "clip:13": ([False], [], [False], ["meaning"], "必须行动但漏包点"),
        "clip:14": ([False, False], [False], [False], ["identity", "meaning"], "cat->球员人数有限，漏xertioN"),
        "clip:15": ([True, False], [False], [], ["identity", "meaning"], "胆怯坐回对，漏Spirit领先"),
        "clip:16": ([True, True], [], [], [], "天才与疯狂平衡+很晚出现希望不被清理"),
        "clip:17": ([True, False], [True], [True], ["relation"], "风险值得对，但对Spirit有人数优势反转成Spirit的人数优势很大"),
        "clip:18": ([True, True], [], [], [], "局势不利/打得糟糕+很讨厌这张地图"),
        "clip:19": ([True, True], [], [], [], "讨厌两边+太搞笑了"),
        "clip:20": ([False, False], [False], [], ["identity"], "Dust2->Dusty"),
        "clip:21": ([True, False], [False], [], ["identity"], "永远无法摆脱对，donk->医生"),
        "clip:22": ([False], [], [], ["meaning"], "site->心理战玩家"),
        "clip:23": ([True], [True], [], [], "好了zont1x，zont1x的干净击杀"),
        "clip:24": ([False], [False], [], ["identity"], "donk->Dom"),
        "clip:25": ([], [], [], [], "存疑排除"),
        "clip:26": ([True], [True], [True], [], "Spirit早期节奏+CT方"),
        "clip:27": ([True], [], [], [], "开局阶段进攻性打法"),
        "clip:28": ([True, False], [True, True], [False, True, True], ["term"], "Shiro中路+donk隧道对，Berettas误作人名"),
        "clip:29": ([False], [False], [], ["identity"], "MOUZ->按着鼠标"),
        "clip_match_demo2:01": ([True, False, True], [True], [False, False], ["term", "meaning"], "Yuri离开Palace+中路混战沟通混乱对，extremity->极限玩家"),
        "clip_match_demo2:02": ([False, True], [False, True], [], ["identity"], "molodoy->Monoloy，kyousuke走进瞄准范围对"),
        "clip_match_demo2:03": ([False, False], [False, False], [False], ["identity"], "molodoy->Mold，FURIA->Yuri"),
        "clip_match_demo2:04": ([False, True], [False, True], [], ["identity"], "Mirage起始点对，漏FURIA自选"),
        "clip_match_demo2:05": ([True, False], [True], [True], ["unsupported"], "NiKo烟雾边缘扳回对，但术语表泄露加从包点，vision->幻视"),
        "clip_match_demo2:06": ([False], [False], [], ["identity"], "漏TeSeS仅剩轮到上场"),
        "clip_match_demo2:07": ([True, False, True], [False], [], ["identity"], "排好队+绞肉机对，m0NESY->Odyssey"),
        "clip_match_demo2:08": ([True, False], [], [], ["meaning"], "默契团结对，baits->Bates人名"),
        "clip_match_demo2:09": ([False, True], [False], [True], ["identity"], "无补枪对，YEKINDAR->Kim"),
        "clip_match_demo2:10": ([False, True], [True], [False], ["meaning"], "palace->palettes丢失位置，Yuri才开始发挥作用对"),
        "clip_match_demo2:11": ([True, True, True], [True], [False], [], "炸弹在尼科旁，火焰尴尬，没关系避开火焰"),
        "clip_match_demo2:12": ([True, False], [True], [], ["meaning"], "Yuri被抓住对，漏没打出作用"),
        "clip_match_demo3:01": ([False, False, True], [False, True], [False], ["identity", "number"], "Bit完成任务对，漏karrigan，7HP->78"),
        "clip_match_demo3:02": ([False, True, False], [False], [True, False, False], ["identity", "term"], "大厅与分散对，iM->Emeron，漏Heaven/Hell"),
        "clip_match_demo3:03": ([True], [], [], [], "他有这个胆量吗？他能坚持住吗？"),
        "clip_match_demo3:04": ([True, False], [False, False], [True], ["identity"], "爆头对，jcobbb->Jenka，makazze->Carte"),
        "clip_match_demo3:05": ([True, False, False], [False], [False], ["identity"], "阻止第二人，漏b1t与大厅"),
        "clip_match_demo3:06": ([False, False], [True, False, False], [True], ["identity"], "frozen+通风口对，漏w0nderful与broky"),
        "clip_match_demo3:07": ([False, False], [], [], ["meaning"], "漏not get away，attention->紧张情绪消失"),
        "clip_match_demo3:08": ([False, False], [False], [], ["identity"], "漏frozen"),
        "clip_match_demo3:09": ([False], [False], [], ["identity", "meaning"], "漏frozen与one-round game"),
        "clip_match_demo3:10": ([False, False], [False], [], ["identity", "meaning"], "jcobbb->Jacob"),
        "clip_interview_niko:01": ([True, True, True], [True], [True], ["unsupported"], "G2/1.54/保持状态对，但C1受术语表泄露插入队内沟通充分"),
        "clip_interview_niko:02": ([True, False], [], [], ["meaning"], "再次表扬我对，漏seems to be working"),
        "clip_interview_niko:03": ([True, False], [], [], ["meaning"], "继续计算数据对，crowd->乌鸦且C4空"),
        "clip_interview_niko:04": ([False, False], [True], [], ["meaning"], "低音量漏掉C6全段"),
        "clip_interview_niko:05": ([False, False], [], [], ["meaning"], "低音量漏掉C6/C7全段"),
        "clip_interview_niko:06": ([True, False, False], [False, False], [False], ["identity", "meaning"], "C9低音量空白漏掉Falcons vs Spirit/Major"),
        "clip_interview_niko:07": ([True, True], [True], [], [], "Spirit状态最好+艰难比赛"),
        "clip_interview_niko:08": ([True], [], [], [], "像昨天那样"),
        "clip_interview_niko:09": ([True, True, False, True], [], [True], ["meaning"], "精力/沟通/积极心态对，C13漏正确决策"),
        "clip_interview_niko:10": ([True, True], [], [], ["unsupported"], "输赢不重要+每轮100%专注对，但C14尾部多补一句队内沟通"),
        "clip_interview_niko:11": ([True, True], [], [True], [], "至关重要+Major表现最出色"),
        "clip_interview_niko:12": ([False], [], [], ["meaning"], "C17低音量空白漏掉结尾"),
    },
    "whisper_large_v3_turbo_q5__qwen3_1.7b": {
        "clip:01": ([False], [False], [False], ["identity", "meaning"], "整句照抄英文未译"),
        "clip:02": ([True, True], [], [], ["relation"], "门边暴露+9和12，把tN1R连到杀手"),
        "clip:03": ([False, False], [False, True], [False], ["meaning"], "半句照抄英文未译"),
        "clip:04": ([False, True], [False], [], ["identity"], "前半句在C4未译，C5仅剩子弹与空间"),
        "clip:05": ([True], [], [False], [], "炸弹在对决中被发现"),
        "clip:06": ([True, True], [True], [True, True], [], "中路交叉声+shiro鸟狙均对"),
        "clip:07": ([True, True], [True], [True], [], "换人+donk首杀"),
        "clip:08": ([True], [True], [True], [], "往B点去了"),
        "clip:09": ([True, False], [True], [False, False, True], ["term"], "XertioN有炸弹对，scout->侦察"),
        "clip:10": ([True], [True], [], [], "XertioN将要链接上"),
        "clip:11": ([False, False, True], [], [False, False, False], ["term", "meaning"], "cat->帽盔板，scout未译"),
        "clip:12": ([True, False], [False], [], ["identity"], "错过时机对，xertioN->泽尔辛"),
        "clip:13": ([False], [], [False], ["meaning"], "漏包点"),
        "clip:14": ([False, False], [False], [False], ["identity", "meaning"], "漏小道与xertioN，夹杂英文timidly"),
        "clip:15": ([True, True], [True], [], ["meaning"], "虽有Spirit领先但夹杂英文timid"),
        "clip:16": ([True, True], [], [], [], "天才与疯狂平衡+最后时刻出场希望不被清除"),
        "clip:17": ([True, False], [False], [False], ["identity", "term"], "风险值得一试对，Spirit译作精神的数值优势"),
        "clip:18": ([False, True], [], [], ["meaning"], "tilted->歪了，讨厌地图对"),
        "clip:19": ([False, True], [], [], ["meaning"], "C21照抄英文未译"),
        "clip:20": ([True, False], [False], [], ["meaning"], "C24整句照抄英文Dust2未译"),
        "clip:21": ([False, True], [True], [], ["meaning"], "C24未译，Donk在角落对"),
        "clip:22": ([True], [], [], [], "现场玩家差点独自完成"),
        "clip:23": ([True], [True], [], [], "Zontix打出干净的射击"),
        "clip:24": ([False], [False], [], ["identity"], "donk->Domk"),
        "clip:25": ([], [], [], [], "存疑排除"),
        "clip:26": ([True], [True], [True], ["meaning"], "Spirit早期节奏+CT侧，但夹杂英文right/aggression/no_think"),
        "clip:27": ([True], [], [], ["meaning"], "夹杂英文aggression"),
        "clip:28": ([False, False], [True, False], [False, False, True], ["meaning"], "C31误重复C30，整句遗漏donk隧道双枪"),
        "clip:29": ([False], [False], [], ["identity"], "整句被C31重复覆盖遗漏"),
        "clip_match_demo2:01": ([True, False, True], [True], [False, True], ["term"], "Yuri出宫+中路战斗沟通混乱对，extremity->极限玩家"),
        "clip_match_demo2:02": ([False, False], [False, False], [], ["identity", "meaning"], "C5整句照抄英文，C6把kyousuke错译为小林"),
        "clip_match_demo2:03": ([True, False], [True, False], [False], ["identity", "unsupported"], "FURIA->Uri且凭空加转化为爆头"),
        "clip_match_demo2:04": ([True, True], [False, True], [], ["identity"], "Mirage开始比赛对，漏FURIA"),
        "clip_match_demo2:05": ([True, True], [True], [True], [], "尼柯烟雾边缘扳回，震荡波给机会（轻微重复）"),
        "clip_match_demo2:06": ([False], [False], [], ["identity"], "TeS未还原TeSeS"),
        "clip_match_demo2:07": ([True, False, False], [False], [], ["identity"], "m0NESY->Modesty"),
        "clip_match_demo2:08": ([True, False], [], [], ["meaning"], "C15照抄英文the synergy，baits->击败"),
        "clip_match_demo2:09": ([False, True], [False], [True], ["identity"], "无补枪对，漏YEKINDAR"),
        "clip_match_demo2:10": ([True, True], [True], [False], [], "Yuri仍在Palace开始激活"),
        "clip_match_demo2:11": ([True, True, False], [True], [False], ["meaning"], "夹杂英文awkward和/no_think，漏安全避火"),
        "clip_match_demo2:12": ([True, False], [True], [], ["meaning"], "Yuri被抓对，漏没打出作用"),
        "clip_match_demo3:01": ([True, False, True], [True, True], [False], ["number"], "Karrigan/Bit对，7HP->7,8英尺"),
        "clip_match_demo3:02": ([False, True, False], [False], [False, False, False], ["identity", "term"], "iM->Dimron，漏Hell"),
        "clip_match_demo3:03": ([True], [], [], [], "他有胆子吗？能否守住？"),
        "clip_match_demo3:04": ([True, False], [False, True], [True], ["identity"], "爆头/Makaze对，Jacob未还原且夹杂英文deny/bid/back"),
        "clip_match_demo3:05": ([True, False, False], [False], [False], ["identity", "meaning"], "大段中英夹杂"),
        "clip_match_demo3:06": ([False, True], [False, False, False], [True], ["identity"], "frozen->弗林斯，broky->博克利，漏w0nderful"),
        "clip_match_demo3:07": ([True, True], [], [], [], "不会溜走+足够作诱饵吸引注意力"),
        "clip_match_demo3:08": ([False, False], [False], [], ["meaning"], "C13/C14整句照抄英文未译"),
        "clip_match_demo3:09": ([False], [False], [], ["meaning"], "C15整句照抄英文未译"),
        "clip_match_demo3:10": ([False, False], [False], [], ["identity", "meaning"], "jcobbb->Jacob"),
        "clip_interview_niko:01": ([True, True, True], [True], [True], [], "对阵G2，1.54评分，保持能量"),
        "clip_interview_niko:02": ([True, False], [], [], ["meaning"], "夸我一次对，working->bargain"),
        "clip_interview_niko:03": ([True, True], [], [], [], "继续跑数+问昨天人群与场馆氛围"),
        "clip_interview_niko:04": ([True, True], [True], [], [], "知道会很好+来葡萄牙很棒体验"),
        "clip_interview_niko:05": ([True, True], [], [], [], "充满活力+希望今天玩得开心"),
        "clip_interview_niko:06": ([False, True, True], [True, True], [True], ["meaning"], "C8大段照抄英文未译；Falcons对Spirit+Major对"),
        "clip_interview_niko:07": ([True, True], [False], [], ["identity"], "Spirit错译为精神队；艰难比赛对"),
        "clip_interview_niko:08": ([True], [], [], [], "像昨天那样"),
        "clip_interview_niko:09": ([True, True, True, True], [], [True], [], "有能量/良好沟通/正确决定/积极心态全对"),
        "clip_interview_niko:10": ([True, True], [], [], ["meaning"], "输赢+每轮100%专注对，但C15泄露/不带任何标点"),
        "clip_interview_niko:11": ([False, False], [], [False], ["meaning"], "C16整句照抄英文未译"),
        "clip_interview_niko:12": ([True], [], [], [], "今天也能做到"),
    },
}


def main():
    refs = json.loads(REF_PATH.read_text())["units"]
    base = json.loads(BASE_AUDIT.read_text())
    asr = json.loads((OUT / "matrix_asr_results.json").read_text())
    tr = json.loads((OUT / "matrix_translate_summary.json").read_text())
    rows = [json.loads(l) for l in (OUT / "matrix_translations.jsonl").read_text().splitlines()]

    han = re.compile(r"[\u3400-\u9fff]")
    by_cell = {}
    for r in rows:
        by_cell.setdefault(r["cell"], []).append(r)

    auto_cells = {}
    for cell, rs in by_cell.items():
        asr_name, mt_name = cell.split("__")
        real = [r for r in rs if r["source_id"] != "cs_demo2_18s" and r["english_asr"].strip()]
        valid_zh = sum(bool(han.search(r["chinese"])) for r in real)
        copied_en = sum(r["chinese"].strip().lower() == r["english_asr"].strip().lower() for r in real)
        no_think = sum("/no_think" in r["chinese"].lower() for r in real)
        cstat = tr["cells"][cell]
        auto_cells[cell] = {
            "asr": asr_name,
            "mt": mt_name,
            "asr_size_mb": asr["models"][asr_name]["model_size_mb"],
            "mt_size_mb": tr["mt_models"][mt_name]["size_mb"],
            "total_disk_mb": round(asr["models"][asr_name]["model_size_mb"] + tr["mt_models"][mt_name]["size_mb"], 1),
            "mt_peak_rss_mb": tr["mt_models"][mt_name]["peak_rss_mb"],
            "match_wer_causal": asr["models"][asr_name]["weighted_match_wer_causal"],
            "interview_wer_causal": asr["models"][asr_name]["interview_wer_causal"],
            "asr_p50_ms_clip": asr["models"][asr_name]["clips"]["clip"]["chunk_p50_ms"],
            "mt_p50_ms": cstat["mt_p50_ms"],
            "mt_p95_ms": cstat["mt_p95_ms"],
            "asr_plus_mt_p50_ms": cstat["asr_plus_mt_p50_ms"],
            "asr_plus_mt_p95_ms": cstat["asr_plus_mt_p95_ms"],
            "valid_zh_rate": round(valid_zh / len(real), 4),
            "copied_en_count": copied_en,
            "no_think_leak_count": no_think,
        }

    semantic = {}
    for cell, cj in JUDGMENTS.items():
        for scope in ["primary_match", "secondary_interview"]:
            chosen = [u for u in refs if (u["source_id"] == "clip_interview_niko") == (scope == "secondary_interview")]
            entries = []
            for u in chosen:
                atoms, ents, terms, errs, note = cj[u["id"]]
                assert len(atoms) == len(u["atoms"]), f"{cell} {u['id']} atoms"
                assert len(ents) == len(u["entities"]), f"{cell} {u['id']} ents"
                assert len(terms) == len(u["terms"]), f"{cell} {u['id']} terms"
                whole = u["score_whole"] and all(atoms) and not errs
                entries.append((u, atoms, ents, terms, errs, whole))
            semantic[f"{cell}__{scope}"] = {
                "whole_correct": sum(w for *_, w in entries),
                "whole_total": sum(u["score_whole"] for u, *_ in entries),
                "atoms_correct": sum(sum(a) for _, a, *_ in entries),
                "atoms_total": sum(len(u["atoms"]) for u, *_ in entries),
                "entities_correct": sum(sum(e) for _, _, e, *_ in entries),
                "entities_total": sum(len(u["entities"]) for u, *_ in entries),
                "terms_correct": sum(sum(t) for _, _, _, t, *_ in entries),
                "terms_total": sum(len(u["terms"]) for u, *_ in entries),
                "error_units": {
                    k: sum(k in errs for _, _, _, _, errs, _ in entries)
                    for k in ["identity", "term", "number", "negation", "unsupported", "relation", "meaning"]
                },
            }

    out = {
        "baseline_e2b_cs2_auto": {
            "primary_match": base["summary"]["cs2_auto_primary_match"],
            "secondary_interview": base["summary"]["cs2_auto_secondary_interview"],
        },
        "all_9_cells_auto": auto_cells,
        "top_4_cells_semantic": semantic,
    }
    (OUT / "matrix_audit.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    for k, v in semantic.items():
        print(f"{k:58s}: whole={v['whole_correct']:2d}/{v['whole_total']:2d} atoms={v['atoms_correct']:2d}/{v['atoms_total']:2d} ent={v['entities_correct']:2d}/{v['entities_total']:2d} term={v['terms_correct']:2d}/{v['terms_total']:2d} errs={v['error_units']}")


if __name__ == "__main__":
    main()
