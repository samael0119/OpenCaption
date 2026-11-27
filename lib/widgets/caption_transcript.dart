import 'dart:math' as math;
import 'package:flutter/material.dart';

/// Preserve the chosen hue while meeting readable contrast on either theme.
Color captionTextColor(Color preferred, Color surface) {
  double contrast(Color value) {
    final a = value.computeLuminance(), b = surface.computeLuminance();
    return (math.max(a, b) + .05) / (math.min(a, b) + .05);
  }

  if (contrast(preferred) >= 4.5) return preferred;
  final target = contrast(Colors.black) >= contrast(Colors.white)
      ? Colors.black
      : Colors.white;
  for (var step = 1; step <= 20; step++) {
    final candidate = Color.lerp(preferred, target, step / 20)!;
    if (contrast(candidate) >= 4.5) return candidate;
  }
  return target;
}

class CaptionTranscript extends StatelessWidget {
  const CaptionTranscript({
    super.key,
    required this.source,
    required this.translation,
    required this.showSource,
    required this.showTranslation,
    required this.fontSize,
    required this.sourceColor,
    required this.translationColor,
    this.failed = false,
    this.latest = false,
    this.footer,
  });
  final String source, translation;
  final bool showSource, showTranslation, failed, latest;
  final double fontSize;
  final Color sourceColor, translationColor;
  final Widget? footer;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final surface = Theme.of(context).scaffoldBackgroundColor;
    final secondary = showSource && source.trim().isNotEmpty && showTranslation;
    final sourceForeground = captionTextColor(
      failed ? colors.error : sourceColor,
      surface,
    );
    final translationForeground = captionTextColor(
      failed ? colors.error : translationColor,
      surface,
    );
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (showSource && source.trim().isNotEmpty)
            Text(
              source,
              style: TextStyle(
                fontSize: secondary ? math.max(12, fontSize * .78) : fontSize,
                height: 1.5,
                color: sourceForeground,
                fontWeight: FontWeight.w400,
              ),
            ),
          if (showTranslation) ...[
            if (secondary) const SizedBox(height: 8),
            Text(
              translation,
              style: TextStyle(
                fontSize: fontSize,
                height: 1.5,
                color: translationForeground,
                fontWeight: latest ? FontWeight.w600 : FontWeight.w500,
              ),
            ),
          ],
          ?footer,
          const SizedBox(height: 18),
          Divider(
            height: 1,
            color: colors.outlineVariant.withValues(alpha: .5),
          ),
        ],
      ),
    );
  }
}
