/// Subtitle foreground colors that remain legible over the dark overlay and
/// can be persisted without coupling the controller to Flutter widgets.
enum SubtitleColor {
  white('white', '白色', 0xffffffff),
  yellow('yellow', '黄色', 0xffffe082),
  cyan('cyan', '青色', 0xff80deea),
  green('green', '绿色', 0xffa5d6a7);

  const SubtitleColor(this.id, this.label, this.argb);

  final String id;
  final String label;
  final int argb;

  static SubtitleColor fromId(
    String? id, {
    SubtitleColor fallback = SubtitleColor.white,
  }) => switch (id) {
    'yellow' => SubtitleColor.yellow,
    'cyan' => SubtitleColor.cyan,
    'green' => SubtitleColor.green,
    _ => fallback,
  };
}
