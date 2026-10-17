# 自然耳语与录制噪声独立补充材料

2026-10-14，北京时间。新材料在本次模型/VAD输出前冻结，独立于既有52例诊断和短答批次；尚未推理，不标为验收通过。

来源：[爱丁堡大学官方语料页](https://datashare.ed.ac.uk/items/30d10e2e-0ccb-483b-b499-8b3c98ad0a2c)、[发布方README](https://datashare.ed.ac.uk/server/api/core/bitstreams/90c9169c-1753-42d9-843a-63300a40a280/content)。CSTR NAM TIMIT Plus，Yamagishi、Brown、Yang、Clark、King，University of Edinburgh / CSTR，DOI 10.7488/ds/2994。README/COPYING声明ODC-By 1.0；保留完整文本与署名，仅本机评测，不发布音频。

此语料是实际人声耳语，含普通耳机麦克风与接触式NAM麦克风两路；只使用18段 `VOICECOMMAND-NOISY/*_headset.wav` 普通麦克风录音。背景来自录制时播放的咖啡厅噪声（发布方说明约65dB[A]、约10dB SNR），没有在本次实验中合成噪声或衰减人声。它覆盖真实耳语在录制噪声环境中的情况，不能等同于实际赛事或任意自然低声场景。

获取采用有界HTTPS Range：归档1.34GiB，只读取前12MiB便配齐18音频/文本。首次8MiB请求返回416；使用独立下载URL后范围成功，原前8MiB有18文本/13耳机文件，再增4MiB得到完整18耳机文件。两范围都匹配发布方ETag `d82a9594a4eaed8c06c5527367e31453`；该值是归档预期MD5，**没有下载整个归档，不能宣称全档MD5已验证**。已记录前缀SHA256及逐文件hash。

素材保留全部18耳机文件和原始参考提示文本，按文件名固定顺序，总计**63.884375秒、一位说话人**。从实际分发的96kHz单声道16-bit PCM转为16kHz单声道16-bit PCM，不裁剪、不调音量、不归一化。转换后RMS0.047654–0.079562；弱声是实际耳语发声方式，不是按低RMS挑样本。全部<=5s，可按原始完整录音输入模型。

参考来自发布方预定词语文本，包括time/desk/show/down/run/create/folder/open/music/download/document/browser/media/recognition/sleep/wakeup/active/quit。它不是模型转录，也不是另找人员重新校对的双语金标；背景其他声音没有完整逐词标注。只有一名女性说话人，模型预训练污染未知。`wakeup`与`wake up`的拼写差异可能影响严格字面指标，不将单纯高WER自动解释为丢语音。

文件入口：

- `evaluation/results/v020-independent/whisper_holdout_cases.json`：冻结来源、参考、波形/文本hash、转换及声级。
- `whisper_vad_cases.tsv`、`whisper_vad_plan.json`：reset/continuous各18例，共36记录；**沿用已有52例诊断前冻结的规则**，不因新素材调阈值。
- `assets/nam_original/VOICECOMMAND-*`、`assets/nam_readme.txt`、`assets/nam_license.txt`、`assets/nam_metadata.json`：原始文件与来源/许可。
- `evaluation/v020_prepare_whisper_holdout.py`：可复核准备脚本；已运行并冻结，禁止依据输出重新选样。

后续 `opencaption-v020-whisper-holdout.service` 已启动等待：必须在既有3次长稳及后续任务完成后才用相同模型锁，512MiB/swap0/120s完成VAD，再6GiB/swap0/900s做54请求（双语无提示/基础提示36配对、英语18）。主任务失败则停止，不继续声称版本已验证。汇总保留NoSpeech/invalid、英文WER与完整指令匹配；无中文金标，只能检查中文格式，不能宣称中文准确性通过。

当前尚无whisper_evidence.tsv或whisper_model.jsonl完成记录。新材料用于检验音乐诊断方案会不会误丢真实耳语；候选诊断仍没有接入产品过滤。原音乐虚构失败、独立CS2/转会/切图中文质量缺口未因此关闭。

等待期间另复查队伍别名边界：未知Academy/Junior/Youth后缀不能给母队投票，新增一项回归待跑；联合缺口样例改成不重叠的真实采样区间。后续任务仍未生成源快照/未开始测试，这些待测修改会随首次快照固定；长稳使用的旧class始终没有重编译。
