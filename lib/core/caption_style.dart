import 'dart:convert';
import 'package:flutter/services.dart';

/// Explicit presentation preferences. Standard retains the validated prompt.
enum CaptionStyle {
  standard('标准', '自然、清楚，保留标准 ID 和原意'),
  natural('自然解说（实验）', '流畅口语化中文解说表达，保留原意与数字，不主动加梗'),
  community('社区趣味（实验）', '接地气的中文社区风格与选手外号，不编造事实或改动数字');

  const CaptionStyle(this.label, this.description);
  final String label, description;

  static CaptionStyle fromId(String? id) =>
      values.firstWhere((style) => style.name == id, orElse: () => standard);
}

class CommunityNickname {
  const CommunityNickname(
    this.id,
    this.variants, {
    this.team = '',
    this.translatedForms = const [],
    this.requireContext = false,
  });
  final String id;
  final List<String> variants;
  final String team;
  final List<String> translatedForms;
  final bool requireContext;

  String get chinese => variants.first;

  String pick([int? seed]) {
    if (variants.length <= 1) return variants.first;
    final value = seed ?? DateTime.now().microsecondsSinceEpoch;
    return variants[value.abs() % variants.length];
  }
}

/// Deterministic style & nickname renderer for the decoupled pipeline.
/// Loads player nicknames from `assets/corpora/cs2_player_nicknames.json`
/// (shared single source of truth with native `CaptionStyle.kt`).
class CaptionStyleRenderer {
  static const nicknamesAsset = 'assets/corpora/cs2_player_nicknames.json';

  static List<CommunityNickname> _names = const [];
  static List<CommunityNickname> get names => _names;

  static Future<void> loadNicknames(AssetBundle bundle) async {
    final raw = await bundle.loadString(nicknamesAsset);
    loadNicknamesJson(raw);
  }

  static void loadNicknamesJson(String raw) {
    final decoded = jsonDecode(raw) as Map<String, dynamic>;
    final list = decoded['players'] as List? ?? const [];
    final parsed = <CommunityNickname>[];
    for (final entry in list) {
      if (entry is! Map) continue;
      final id = (entry['id'] as String? ?? '').trim();
      final variants = (entry['nicknames'] as List? ?? const [])
          .whereType<String>()
          .map((s) => s.trim())
          .where((s) => s.isNotEmpty)
          .toList();
      if (id.isEmpty || variants.isEmpty) continue;
      final forms = (entry['translated_forms'] as List? ?? const [])
          .whereType<String>()
          .map((s) => s.trim())
          .where((s) => s.isNotEmpty)
          .toList();
      parsed.add(
        CommunityNickname(
          id,
          variants,
          team: (entry['team'] as String? ?? '').trim(),
          translatedForms: forms,
          requireContext: entry['require_context'] == true,
        ),
      );
    }
    _names = List.unmodifiable(parsed);
  }

  static bool _contextAllows(CommunityNickname name, String activeContext) {
    if (!name.requireContext) return true;
    final ctx = activeContext.toLowerCase();
    if (ctx.isEmpty) return false;
    if (ctx.contains(name.id.toLowerCase())) return true;
    if (name.team.isNotEmpty &&
        name.team != '其他' &&
        ctx.contains(name.team.toLowerCase())) {
      return true;
    }
    return false;
  }

  /// Optional community-flavor phrase hints injected into HY-MT1.5 ONLY when
  /// the user explicitly selects `CaptionStyle.community` with the CS2 glossary.
  static final List<(RegExp, String, String)> _communityPromptHints = [
    (RegExp(r'\bwhiff(?:s|ed|ing)?\b', caseSensitive: false), 'whiff', '马枪'),
    (RegExp(r'\bdry\s+peek(?:s|ed|ing)?\b', caseSensitive: false), 'dry peek', '干拉'),
    (RegExp(r'\bwide\s+swing(?:s|ed|ing)?\b', caseSensitive: false), 'wide swing', '大拉'),
    (RegExp(r'\bone[- ]tap(?:s|ped)?\b', caseSensitive: false), 'one tap', '一发入魂'),
    (RegExp(r'\bfull(?:y)?\s+blind\b', caseSensitive: false), 'full blind', '吃全白'),
    (RegExp(r'\blow\s+(?:hp|health)\b', caseSensitive: false), 'low HP', '大残'),
    (RegExp(r'\bfake\s+defus(?:e|es|ed|ing)\b', caseSensitive: false), 'fake defuse', '假拆'),
    (RegExp(r'\bforce[- ]buy(?:s|ing)?\b', caseSensitive: false), 'force buy', '强起'),
    (RegExp(r'\bfull\s+buy(?:s|ing)?\b', caseSensitive: false), 'full buy', '长枪局'),
    (RegExp(r'\bthrough\s+(?:the\s+)?smoke\b', caseSensitive: false), 'through the smoke', '穿烟'),
    (RegExp(r'\blurk(?:s|ed|ing|er)?\b', caseSensitive: false), 'lurk', '老六单摸'),
    (RegExp(r'\bfree\s+kill\b', caseSensitive: false), 'free kill', '白给'),
    (RegExp(r'\bcollateral\b', caseSensitive: false), 'collateral', '一穿二'),
    (RegExp(r'\bninja\s+defuse\b', caseSensitive: false), 'ninja defuse', '偷包'),
  ];

  static Map<String, String> matchedCommunityHints(String english) {
    final result = <String, String>{};
    for (final (pattern, surface, target) in _communityPromptHints) {
      if (pattern.hasMatch(english)) {
        result[surface] = target;
      }
    }
    return result;
  }

  static RegExp _token(String id) => RegExp(
    '(?<![A-Za-z0-9_-])${RegExp.escape(id)}(?![A-Za-z0-9_-])',
    caseSensitive: false,
  );

  static final RegExp _allMissed = RegExp(
    r'^He (?:misses every shot|missed every shot|misses all (?:his |the )?shots|missed all (?:his |the )?shots)[.!]?$',
    caseSensitive: false,
  );

  static final RegExp _missedChinese = RegExp(
    r'^(?:他)?(?:一枪(?:都)?(?:没中|没打中)|所有(?:的)?(?:子弹|射击)都没(?:有)?(?:打中|命中))[。！!，,]?$',
  );

  static Map<String, String> matchedNicknames(
    String english, {
    int? seed,
    String activeContext = '',
  }) {
    final result = <String, String>{};
    for (final name in _names) {
      if (!_contextAllows(name, activeContext)) continue;
      if (_token(name.id).hasMatch(english)) {
        result[name.id] = name.pick(seed);
      }
    }
    return result;
  }

  static String render({
    required String english,
    required String chinese,
    required CaptionStyle style,
    required bool nicknames,
    required bool cs2,
    int? nicknameSeed,
    String activeContext = '',
  }) {
    if (!cs2) return chinese;
    var text = chinese;
    void replace(String from, String to) {
      if (text.contains(from)) text = text.replaceAll(from, to);
    }

    if (style == CaptionStyle.natural || style == CaptionStyle.community) {
      replace('只剩下', '只剩');
      replace('手枪回合', '手枪局');
      replace('经济回合', '经济局');
      if (RegExp(r'\bforce[- ]buy\b', caseSensitive: false).hasMatch(english)) {
        replace('强行购买', '强起');
        replace('强制购买', '强起');
      }
      if (RegExp(r'\bfull\s+buy\b', caseSensitive: false).hasMatch(english)) {
        replace('全额购买', '长枪局');
        replace('全买回合', '长枪局');
      }
      if (RegExp(r'one[- ]versus[- ]two|1v2', caseSensitive: false)
          .hasMatch(english)) {
        replace('单对双人', '一打二');
        replace('一对二', '一打二');
        replace('赢了一打二', '拿下了一打二');
      }
      if (RegExp(r'one[- ]versus[- ]three|1v3', caseSensitive: false)
          .hasMatch(english)) {
        replace('一对三', '一打三');
        replace('赢了一打三', '拿下了一打三');
      }
      if (RegExp(r'one[- ]versus[- ]four|1v4', caseSensitive: false)
          .hasMatch(english)) {
        replace('一对四', '一打四');
      }
      if (RegExp(r'one[- ]versus[- ]one|1v1', caseSensitive: false)
          .hasMatch(english)) {
        replace('一对一', '一打一');
      }
      if (RegExp(
        r'^(?:They|We|You|He|She) (?:should |must |need to )?save (?:their |our |your |his |her |the )?(?:weapons|guns|rifles|awp)(?:,? (?:rather than|not) (?:go for )?the retake)?[.!]?$',
        caseSensitive: false,
      ).hasMatch(english.trim())) {
        replace('保存他们的武器', '保枪');
        replace('保留他们的武器', '保枪');
        replace('保存武器', '保枪');
      }
      if (RegExp(r'\bretake\b', caseSensitive: false).hasMatch(english)) {
        replace('去夺回', '回防');
        replace('重新夺回', '回防');
      }
      if (RegExp(r'\b(?:gets?\s+two\s+kills|double\s+kill|2k)\b', caseSensitive: false)
          .hasMatch(english)) {
        replace('获得了两次击杀', '拿到双杀');
        replace('拿到两次击杀', '拿到双杀');
      }
      if (RegExp(r'\b(?:gets?\s+three\s+kills|triple\s+kill|3k)\b', caseSensitive: false)
          .hasMatch(english)) {
        replace('获得了三次击杀', '拿到三杀');
        replace('拿到三次击杀', '拿到三杀');
      }
      if (RegExp(r'\b(?:gets?\s+four\s+kills|quad\s+kill|4k)\b', caseSensitive: false)
          .hasMatch(english)) {
        replace('获得了四次击杀', '拿到四杀');
        replace('拿到四次击杀', '拿到四杀');
      }
      if (RegExp(r'\bfake\s+defus', caseSensitive: false).hasMatch(english)) {
        replace('假装拆除', '假拆');
      }
      if (RegExp(r'\blow\s+(?:hp|health)\b|\bone\s+hp\b', caseSensitive: false)
          .hasMatch(english)) {
        replace('生命值很低', '大残');
        replace('血量很低', '大残');
      }
      if (RegExp(r'\bround is not over\b', caseSensitive: false)
          .hasMatch(english)) {
        replace('局不是结束', '这一局还没结束');
      }
      if (RegExp(r'\bdefused\b', caseSensitive: false).hasMatch(english) &&
          RegExp(r'^炸弹(?:还没有|还没|尚未|已经|已|终于)?被解除(?:了)?[。！!]?$')
              .hasMatch(text)) {
        replace('被解除', '被拆掉');
      }
    }

    if (style == CaptionStyle.community) {
      if (RegExp(r'\bwhiff(?:s|ed|ing)?\b', caseSensitive: false)
          .hasMatch(english)) {
        replace('打空了', '马枪了');
        replace('没打中', '马枪了');
      }
      if (RegExp(r'\bone[- ]tap(?:s|ped)?\b', caseSensitive: false)
          .hasMatch(english)) {
        replace('一枪爆头', '一发入魂');
      }
      if (RegExp(r'\bfull(?:y)?\s+blind\b', caseSensitive: false)
          .hasMatch(english)) {
        replace('完全致盲', '吃全白');
        replace('完全失明', '吃全白');
      }
      if (RegExp(r'\bninja\s+defuse\b', caseSensitive: false).hasMatch(english)) {
        replace('忍者拆包', '偷包');
      }
    }

    if (nicknames) {
      for (final name in _names) {
        if (!_contextAllows(name, activeContext)) continue;
        final pattern = _token(name.id);
        if (!pattern.hasMatch(english)) continue;
        final chosen = name.pick(nicknameSeed);
        text = text.replaceAll(pattern, chosen);
        for (final form in name.translatedForms) {
          final exactForm = RegExp(
            '(^|[\\s，。；！？、,:;!?])${RegExp.escape(form)}(?=\$|[\\s，。；！？、,:;!?]|赢|没|不|的|拿|将|说|被|只|还|已|在|有|和|与|获|击|留|走|退|补|消)',
          );
          text = text.replaceAllMapped(
            exactForm,
            (m) => '${m.group(1)}$chosen',
          );
        }
      }
    }

    if (style == CaptionStyle.community &&
        _allMissed.hasMatch(english.trim()) &&
        _missedChinese.hasMatch(text.trim())) {
      text = '一枪没中，这波人体描边了。';
    }
    return text;
  }
}
