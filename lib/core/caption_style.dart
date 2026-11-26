/// Explicit presentation preferences. Standard retains the validated prompt.
enum CaptionStyle {
  standard('标准', '自然、清楚，保留标准 ID 和原意'),
  natural('自然解说（实验）', '少量常用句式更口语，保留原意，不主动加梗'),
  community('社区趣味（实验）', '中文社区表达；仅在明确语义下少量玩梗');

  const CaptionStyle(this.label, this.description);
  final String label, description;

  static CaptionStyle fromId(String? id) =>
      values.firstWhere((style) => style.name == id, orElse: () => standard);
}
