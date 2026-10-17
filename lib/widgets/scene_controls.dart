import 'package:flutter/material.dart';
import '../core/session_controller.dart';

/// Optional current-session correction, inside the existing status disclosure.
class SceneControls extends StatelessWidget {
  const SceneControls({super.key, required this.controller});
  final SessionController controller;

  @override
  Widget build(BuildContext context) {
    final c = controller;
    final enabled = c.canCorrectScene;
    Widget choice(
      String key,
      String label,
      String? selected,
      List<String> choices,
      ValueChanged<String?> apply,
    ) => Padding(
      padding: const EdgeInsets.only(top: 12),
      child: DropdownButtonFormField<String>(
        key: ValueKey('$key-${selected ?? 'auto'}'),
        initialValue: selected ?? '',
        isExpanded: true,
        menuMaxHeight: 280,
        decoration: InputDecoration(labelText: label),
        items: [
          const DropdownMenuItem(value: '', child: Text('自动')),
          ...choices.map(
            (value) => DropdownMenuItem(
              value: value,
              child: Text(value, maxLines: 1, overflow: TextOverflow.ellipsis),
            ),
          ),
        ],
        onChanged: enabled
            ? (value) => apply(value == '' ? null : value)
            : null,
      ),
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                '场景纠正',
                style: Theme.of(context).textTheme.titleSmall,
              ),
            ),
            TextButton(
              onPressed: enabled && c.hasSceneCorrection
                  ? c.restoreAutomaticScene
                  : null,
              child: const Text('恢复自动'),
            ),
          ],
        ),
        const Text('可选，只用于本次会话；战队选齐双方后生效。'),
        choice(
          'scene-map',
          '地图',
          c.manualMap,
          c.corpus.sceneChoices('map'),
          (value) => c.correctScene(
            map: value,
            team1: c.manualTeam1,
            team2: c.manualTeam2,
          ),
        ),
        choice(
          'scene-team1',
          '战队一',
          c.manualTeam1,
          c.corpus
              .sceneChoices('team')
              .where((t) => t != c.manualTeam2)
              .toList(),
          (value) => c.correctScene(
            map: c.manualMap,
            team1: value,
            team2: c.manualTeam2,
          ),
        ),
        choice(
          'scene-team2',
          '战队二',
          c.manualTeam2,
          c.corpus
              .sceneChoices('team')
              .where((t) => t != c.manualTeam1)
              .toList(),
          (value) => c.correctScene(
            map: c.manualMap,
            team1: c.manualTeam1,
            team2: value,
          ),
        ),
        if (c.sceneCorrectionConflict)
          Padding(
            padding: const EdgeInsets.only(top: 12),
            child: Text(
              '字幕线索与纠正不同，当前仍采用你的选择。',
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ),
      ],
    );
  }
}
