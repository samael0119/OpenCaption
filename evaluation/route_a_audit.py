"""Auditable semantic judgment aggregation for Route A evaluation (2026-11-26).

Uses the exact same 62 scored reference units / 119 fact atoms / 47 match entities / 34 match terms
from evaluation/results/cs-domain-20261020/product_round_v2/reference.json.
"""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation/results/route-a-20261126"
REF_PATH = ROOT / "evaluation/results/cs-domain-20261020/product_round_v2/reference.json"
BASE_AUDIT = ROOT / "evaluation/results/cs-domain-20261020/product_round_v2/audit.json"
TRANS_PATH = OUT / "route_a_translations.jsonl"
SUMMARY_PATH = OUT / "route_a_summary.json"
ASR_ZIPF = OUT / "asr_results.json"
ASR_LA2 = OUT / "whisper_la2_v2_results.json"
ASR_WBASE = OUT / "whisper_base_results.json"

# Strict unit-by-unit AI-assisted non-blind judgments (same strictness as product_round_v2):
# Tuple: (atoms_bools, entities_bools, terms_bools, error_labels, note)
JUDGMENTS = {
    "whisper_la2_roster": {
        # --- clip (Spirit vs MOUZ, Dust2) ---
        "clip:01": ([True], [True], [True], [], "果然，donk找到了向E的爆头"),
        "clip:02": ([True, True], [], [], [], "门附近暴露在杀手面前，只有九和十二"),
        "clip:03": ([False, False], [False, True], [False], ["identity", "meaning"], "漏tN1R，15 frags错译为分差15个"),
        "clip:04": ([False, True], [False], [], ["identity", "meaning"], "xertioN->cershion，拉回来丢还击枪"),
        "clip:05": ([True], [], [False], [], "那个对决里也发现了那个炸弹（事实对，术语用炸弹非雷包）"),
        "clip:06": ([True, False], [False], [False, True], ["identity", "term"], "漏sh1ro，scout译作侦查"),
        "clip:07": ([False, False], [False], [False], ["meaning"], "trim裁剪区间遗漏"),
        "clip:08": ([False], [False], [False], ["meaning"], "trim裁剪区间遗漏"),
        "clip:09": ([False, False], [False], [False, False, True], ["identity", "meaning"], "仅留M4，漏xertioN/雷包/鸟狙"),
        "clip:10": ([False], [False], [], ["identity"], "xertioN错听为SIRO"),
        "clip:11": ([False, False, True], [], [False, False, False], ["term", "meaning"], "cat->猫牌，scout->侦查点，长门非规范A大门"),
        "clip:12": ([False, False], [False], [], ["identity", "meaning"], "漏Misses，xertioN->Zershin"),
        "clip:13": ([False], [], [False], ["term"], "site->视野"),
        "clip:14": ([False, False], [False], [False], ["identity", "term"], "cat->限制玩家，xertioN->Zershin"),
        "clip:15": ([True, True], [True], [], [], "胆怯地退后，让机会溜走，让Spirit领先"),
        "clip:16": ([True, True], [], [], [], "天才和疯狂之间走钢丝，来得太晚希望不被清理"),
        "clip:17": ([True, True], [True], [True], [], "风险但考虑到你们对Spirit有人数优势，值得考虑"),
        "clip:18": ([False, False], [], [], ["meaning"], "仅留我讨厌它，漏tilted与地图"),
        "clip:19": ([True, True], [], [], [], "我猜我讨厌它 双方都 太搞笑了"),
        "clip:20": ([False, False], [False], [], ["identity", "meaning"], "漏admitting与Dust2"),
        "clip:21": ([False, False], [False], [], ["identity", "meaning"], "donk->Doc，漏前半句"),
        "clip:22": ([False], [], [], ["meaning"], "site->心理队，虽保留几乎自己搞定但主语错"),
        "clip:23": ([False], [True], [], ["meaning"], "zont1x对，但clean shots->女王射击"),
        "clip:24": ([False], [False], [], ["identity"], "donk->Dom"),
        "clip:25": ([], [], [], [], "存疑排除整单元"),
        "clip:26": ([True], [True], [True], [], "Spirit设定的早期节奏，在CT方这边"),
        "clip:27": ([False], [], [], ["unsupported"], "补出“动作有点慢啊”与激进矛盾"),
        "clip:28": ([False, False], [True, True], [False, True, True], ["term", "meaning"], "sh1ro/donk全对，但top->talk说话，Berettas未译双枪"),
        "clip:29": ([False], [False], [], ["identity"], "MOUZ->按鼠标"),
        # --- clip_match_demo2 (Falcons vs FURIA, Mirage R7) ---
        "clip_match_demo2:01": ([True, False, True], [True], [False, False], ["term", "meaning"], "yuurih/中路混战/通讯疯狂对；extremity->极端玩家，skip a beat->跳过回合"),
        "clip_match_demo2:02": ([True, True], [True, True], [], [], "恰好是molodoy在等的那一刻，kyousuke走位进入瞄准点"),
        "clip_match_demo2:03": ([True, True], [True, True], [False], [], "莫洛多伊提供了开局，FURIA需要找到终结利用机会（首杀未直出）"),
        "clip_match_demo2:04": ([True, False], [True, True], [], ["meaning"], "Mirage自选对，但start us off->开始阻止"),
        "clip_match_demo2:05": ([True, True], [True], [True], [], "NiKo反击了就在烟雾边缘，拉锯战给了他视野"),
        "clip_match_demo2:06": ([True], [True], [], [], "TeSeS轮到上场了"),
        "clip_match_demo2:07": ([False, False, False], [False], [], ["meaning"], "40s后buffer trim bug导致重复/丢段"),
        "clip_match_demo2:08": ([False, False], [], [], ["meaning"], "40s后buffer trim bug丢段"),
        "clip_match_demo2:09": ([False, False], [False], [False], ["meaning"], "40s后buffer trim bug丢段"),
        "clip_match_demo2:10": ([False, False], [False], [False], ["meaning"], "40s后buffer trim bug丢段"),
        "clip_match_demo2:11": ([False, False, False], [False], [False], ["meaning"], "40s后buffer trim bug丢段"),
        "clip_match_demo2:12": ([False, False], [False], [], ["meaning"], "40s后buffer trim bug丢段"),
        # --- clip_match_demo3 (FaZe vs NAVI, Nuke R19) ---
        "clip_match_demo3:01": ([False, False, True], [False, True], [False], ["identity", "number"], "b1t结束局面正确；karrigan->kara，7HP->七八英尺"),
        "clip_match_demo3:02": ([False, True, False], [False], [False, False, False], ["identity", "term", "meaning"], "漏iM，Hell->求助"),
        "clip_match_demo3:03": ([True], [], [], [], "他有胆量吗他能坚持住吗"),
        "clip_match_demo3:04": ([True, False], [False, False], [True], ["identity"], "爆头对，但jcobbb->jank up且漏makazze对象"),
        "clip_match_demo3:05": ([False, False, False], [False], [False], ["identity", "meaning"], "number two denied/b1t均错"),
        "clip_match_demo3:06": ([True, False], [True, True, False], [True], ["identity"], "wonderful被frozen击倒+通风口均对，漏broky"),
        "clip_match_demo3:07": ([True, True], [], [], [], "不会逃脱，也许足够做诱饵引开注意力"),
        "clip_match_demo3:08": ([False, False], [False], [], ["meaning"], "trim/重复导致Can he frozen/Impact on impact丢失"),
        "clip_match_demo3:09": ([True], [True], [], [], "Frozen让它变成一局分差"),
        "clip_match_demo3:10": ([False, False], [False], [], ["identity", "meaning"], "jcobbb->Jacob，nonsense->胡闹"),
        # --- clip_interview_niko (NiKo interview) ---
        "clip_interview_niko:01": ([True, False, True], [True], [False], ["number"], "G2和延续能量对，但中文译文漏写1.54"),
        "clip_interview_niko:02": ([True, False], [], [], ["meaning"], "夸我一次对，working->bargaining谈判"),
        "clip_interview_niko:03": ([True, True], [], [], [], "继续把数字说出来+问昨天观众和气氛"),
        "clip_interview_niko:04": ([True, False], [False], [], ["identity"], "20s trim漏掉Portugal段"),
        "clip_interview_niko:05": ([False, True], [], [], ["meaning"], "trim仅留也很有趣，漏享受/活力"),
        "clip_interview_niko:06": ([True, True, True], [True, True], [False], [], "最受追捧+Falcons对阵Spirit关键+上次非常接近（漏Major术语）"),
        "clip_interview_niko:07": ([False, False], [True], [], ["meaning"], "trim漏掉状态最佳与艰难比赛"),
        "clip_interview_niko:08": ([False], [], [], ["meaning"], "trim漏掉重复昨天做法"),
        "clip_interview_niko:09": ([True, True, True, True], [], [True], [], "兴奋度/高沟通/正确决定/积极心态4项全对"),
        "clip_interview_niko:10": ([True, True], [], [], [], "输了就输了赢了就赢了，每局100%专注（修复原E2B反转错误）"),
        "clip_interview_niko:11": ([True, True], [], [False], [], "对我们最重要+大型赛事做得最好（大型赛事非Major）"),
        "clip_interview_niko:12": ([True], [], [], [], "如果今天也能做到这一点"),
    },
    "whisper_base_clean_segs": {
        # --- clip (no ASR roster prompt; tests clean Whisper base.en segmentation) ---
        "clip:01": ([False], [False], [True], ["identity", "negation"], "donk->don't go导致否定反转"),
        "clip:02": ([True, True], [], [], [], "门边暴露杀手，九和十二"),
        "clip:03": ([False, True], [False, True], [True], ["identity"], "Shiro与15击杀对，漏tN1R"),
        "clip:04": ([False, True], [False], [], ["identity"], "xertioN->Certian，空间对"),
        "clip:05": ([True], [], [False], [], "对决中发现炸弹"),
        "clip:06": ([True, False], [True], [False, True], ["term"], "Shiro对，scout->侦察"),
        "clip:07": ([True, False], [False], [False], ["identity"], "换人了+开局击杀对，donk->dog"),
        "clip:08": ([True], [False], [True], ["identity"], "去B点对，主语延续dog"),
        "clip:09": ([False, False], [False], [False, False, False], ["identity", "meaning"], "错听为侦查有没有炸弹"),
        "clip:10": ([False], [False], [], ["identity"], "漏xertioN主语"),
        "clip:11": ([False, False, False], [], [False, False, False], ["term", "meaning"], "cat->猫板，scout->侦查点，漏A大门"),
        "clip:12": ([True, False], [False], [], ["identity"], "错过时机对，xertioN->exertion太费劲"),
        "clip:13": ([False], [], [False], ["meaning"], "site->我能做到"),
        "clip:14": ([False, False], [False], [False], ["identity", "term"], "cat->猫队，xertioN->Certian"),
        "clip:15": ([True, True], [True], [], [], "胆怯退后让机会结束让Spirit领先"),
        "clip:16": ([True, True], [], [], [], "天才和疯狂走钢丝，太晚出来祈祷不被清理"),
        "clip:17": ([True, True], [True], [True], [], "风险但对Spirit有人数优势值得考虑"),
        "clip:18": ([False, False], [], [], ["meaning"], "漏I'm tilted"),
        "clip:19": ([True, True], [], [], [], "讨厌双方都一样，好笑"),
        "clip:20": ([False, False], [False], [], ["identity", "meaning"], "Dust2->does too丢失"),
        "clip:21": ([True, False], [False], [], ["identity"], "永远摆脱不了对，donk->Doc"),
        "clip:22": ([True], [], [], [], "站点队员几乎自己完成任务"),
        "clip:23": ([True], [True], [], [], "好的，Zontix干净利落的射击"),
        "clip:24": ([False], [False], [], ["identity"], "donk->狗"),
        "clip:25": ([], [], [], [], "存疑排除"),
        "clip:26": ([True], [True], [True], [], "Spirit早期节奏+CT方"),
        "clip:27": ([True], [], [], [], "开局有点激进"),
        "clip:28": ([False, False], [True, False], [False, True, True], ["identity", "term"], "Shero对，donk->docked，Berettas未译双枪"),
        "clip:29": ([False], [False], [], ["identity"], "MOUZ->按鼠标"),
        # --- demo2 (no ASR roster prompt) ---
        "clip_match_demo2:01": ([True, False, False], [True], [False, False], ["term", "meaning"], "Yuri出宫殿对；extremity->极端玩家，漏comms"),
        "clip_match_demo2:02": ([True, False], [True, True], [], ["meaning"], "Monodoy/kyousuke识别出但waltz误作人名"),
        "clip_match_demo2:03": ([True, False], [True, False], [False], ["identity"], "莫洛多伊开局对，FURIA->如果你真的"),
        "clip_match_demo2:04": ([True, False], [False, True], [], ["identity", "meaning"], "米拉杰对，漏FURIA且start us off->开始就停"),
        "clip_match_demo2:05": ([True, False], [True], [True], ["meaning"], "NiKo烟边扳回对，vision->envision想象一下"),
        "clip_match_demo2:06": ([False], [False], [], ["identity"], "TeSeS->chances，仅留轮到上场"),
        "clip_match_demo2:07": ([False, False, False], [False], [], ["identity", "meaning"], "m0NESY->谦虚，meat grinder->重点打磨"),
        "clip_match_demo2:08": ([True, False], [], [], ["meaning"], "协同团结对，baits->beats赢了"),
        "clip_match_demo2:09": ([False, True], [False], [False], ["identity", "term"], "YEKINDAR->王国，trade->交易"),
        "clip_match_demo2:10": ([True, True], [True], [False], [], "Yuri还在宫殿现在开始激活（宫殿非A二楼）"),
        "clip_match_demo2:11": ([False, True, True], [True], [False], ["relation"], "错连为激活炸弹，其余火焰尴尬/安全对"),
        "clip_match_demo2:12": ([False, False], [True], [], ["meaning"], "尾句截断为呼叫Yuri gets"),
        # --- demo3 (no ASR roster prompt) ---
        "clip_match_demo3:01": ([False, False, True], [False, True], [False], ["identity", "number"], "bit结束局面，karrigan->Karen，7HP->七八英尺"),
        "clip_match_demo3:02": ([False, True, False], [False], [False, False, False], ["identity", "term"], "漏iM，clamps->弹药，Hell->求救助"),
        "clip_match_demo3:03": ([True], [], [], [], "他有胆量吗 他能坚持住吗"),
        "clip_match_demo3:04": ([True, False], [False, False], [True], ["identity"], "爆头对，jcobbb->Jacob，makazze->麦卡里"),
        "clip_match_demo3:05": ([True, False, False], [False], [False], ["identity", "term"], "二号拒绝了对，b1t->大后卫，lobby->后方侧翼"),
        "clip_match_demo3:06": ([False, False], [True, False, False], [True], ["identity"], "frozen对，w0nderful->这很棒，漏broky"),
        "clip_match_demo3:07": ([False, True], [], [], ["identity"], "Spotting->斯波特错增主语，诱饵分散注意力对"),
        "clip_match_demo3:08": ([False, False], [False], [], ["identity", "meaning"], "frozen丢失，roll it->推进"),
        "clip_match_demo3:09": ([False], [True], [], ["number"], "one-round game错译成一局两分"),
        "clip_match_demo3:10": ([False, False], [False], [], ["identity", "meaning"], "jcobbb->Jacob，nonsense->更乱"),
        # --- interview_niko ---
        "clip_interview_niko:01": ([True, True, True], [True], [True], [], "对阵G2，1.54等级分，保持同样能量"),
        "clip_interview_niko:02": ([True, True], [], [], [], "再夸一次，让它起作用"),
        "clip_interview_niko:03": ([True, True], [], [], [], "继续跑数据+问昨天观众看法与场馆气氛"),
        "clip_interview_niko:04": ([True, True], [True], [], [], "知道会很棒，每次来葡萄牙都是疯狂竞技场气氛太棒"),
        "clip_interview_niko:05": ([True, True], [], [], [], "感觉舒服玩起来有活力，希望今天也开心"),
        "clip_interview_niko:06": ([True, True, True], [True, True], [False], [], "粉丝最爱+Falcons对Spirit关键+上次接近（大型比赛非Major）"),
        "clip_interview_niko:07": ([True, True], [True], [], [], "Spirit状态最好+知道是艰难比赛"),
        "clip_interview_niko:08": ([False], [], [], ["meaning"], "yesterday被切到下一段，本句译作像以前那样"),
        "clip_interview_niko:09": ([True, True, True, True], [], [True], [], "兴奋度/良好沟通/正确决定/积极心态4项全对"),
        "clip_interview_niko:10": ([False, True], [], [], ["meaning"], "漏which rounds we win，保留每局100%专注"),
        "clip_interview_niko:11": ([True, True], [], [False], [], "最关键+大型赛事做得最好"),
        "clip_interview_niko:12": ([True], [], [], [], "如果今天也能做到"),
    },
}


def main():
    refs = json.loads(REF_PATH.read_text())["units"]
    base = json.loads(BASE_AUDIT.read_text())
    tr_sum = json.loads(SUMMARY_PATH.read_text())
    la2 = json.loads(ASR_LA2.read_text())
    wbase = json.loads(ASR_WBASE.read_text())
    zipf = json.loads(ASR_ZIPF.read_text())

    summary = {}
    per_source = {}
    for arm, arm_j in JUDGMENTS.items():
        for scope in ["primary_match", "secondary_interview"]:
            chosen = [u for u in refs if (u["source_id"] == "clip_interview_niko") == (scope == "secondary_interview")]
            entries = []
            for u in chosen:
                atoms, ents, terms, errs, note = arm_j[u["id"]]
                assert len(atoms) == len(u["atoms"]), f"{arm} {u['id']} atoms mismatch"
                assert len(ents) == len(u["entities"]), f"{arm} {u['id']} entities mismatch"
                assert len(terms) == len(u["terms"]), f"{arm} {u['id']} terms mismatch"
                whole = u["score_whole"] and all(atoms) and not errs
                entries.append((u, atoms, ents, terms, errs, whole))
            summary[f"{arm}_{scope}"] = {
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
        for src in ["clip", "clip_match_demo2", "clip_match_demo3", "clip_interview_niko"]:
            chosen = [u for u in refs if u["source_id"] == src]
            ws = 0
            wt = 0
            ac = 0
            at = 0
            for u in chosen:
                atoms, ents, terms, errs, _ = arm_j[u["id"]]
                if u["score_whole"]:
                    wt += 1
                    if all(atoms) and not errs:
                        ws += 1
                ac += sum(atoms)
                at += len(u["atoms"])
            per_source[f"{arm}_{src}"] = {
                "whole_correct": ws,
                "whole_total": wt,
                "atoms_correct": ac,
                "atoms_total": at,
            }

    out = {
        "scope": "AI-assisted non-blind development comparison on the same frozen 62 units / 119 atoms as cs-domain-20261020/product_round_v2; Linux CPU 4 threads; cgroup 6GiB/swap0",
        "reference_sha256": hashlib.sha256(REF_PATH.read_bytes()).hexdigest(),
        "translations_sha256": hashlib.sha256(TRANS_PATH.read_bytes()).hexdigest(),
        "baseline_cs2_auto": {
            "primary_match": base["summary"]["cs2_auto_primary_match"],
            "secondary_interview": base["summary"]["cs2_auto_secondary_interview"],
            "inference_p50_ms": base["mechanics"]["cs2_auto"]["inference_p50_ms"],
            "inference_p95_ms": base["mechanics"]["cs2_auto"]["inference_p95_ms"],
        },
        "route_a_summary": summary,
        "per_source": per_source,
        "latency_and_resources": tr_sum,
        "asr_wer_summary": {
            "e2b_cs2_auto": {"match_wer": 0.278, "interview_wer": 0.223},
            "zipformer_int8_hotwords": {
                "match_wer_stream": zipf["variants"]["int8_hotwords"]["weighted_match_wer_stream"],
                "match_wer_cont": zipf["variants"]["int8_hotwords"]["weighted_match_wer_continuous"],
                "interview_wer_stream": zipf["variants"]["int8_hotwords"]["interview_wer_stream"],
            },
            "whisper_base_no_prompt_full": {
                "match_wer": 0.222,
                "interview_wer": wbase["no_prompt"]["clip_interview_niko"]["wer"],
                "cs_demo2_18s_wer": wbase["no_prompt"]["cs_demo2_18s"]["wer"],
            },
            "whisper_la2_v2_roster": {
                "match_wer_stream": la2["weighted_match_wer_stream"],
                "interview_wer_stream": la2["interview_wer_stream"],
                "cs_demo2_18s_wer": la2["clips"]["cs_demo2_18s"]["wer_stream"],
                "step_p50_ms_clip": la2["clips"]["clip"]["streamed"]["step_p50_ms"],
                "first_en_ms_demo2_18s": la2["clips"]["cs_demo2_18s"]["streamed"]["first_preview_ready_ms"],
            },
        },
    }
    (OUT / "audit.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(out["route_a_summary"], ensure_ascii=False, indent=2))
    print("\nPER SOURCE:", json.dumps(out["per_source"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
