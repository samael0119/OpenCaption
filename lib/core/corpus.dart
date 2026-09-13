import 'dart:convert';

import 'package:flutter/services.dart';

/// Domain glossary selection.  `none` is deliberately the application
/// default so a normal interview does not receive CS2-specific vocabulary.
enum CorpusProfile {
  none('none', '通用（无术语库）'),
  cs2('cs2', 'CS2 比赛');

  const CorpusProfile(this.id, this.label);

  final String id;
  final String label;

  static CorpusProfile fromId(String? id) => switch (id) {
    'cs2' => CorpusProfile.cs2,
    _ => CorpusProfile.none,
  };
}

class _ScoredTerm {
  _ScoredTerm(this.term);

  final Map<String, Object?> term;
  int hits = 0;
  double score = 0;
}

class CorpusIndex {
  CorpusIndex._(this._terms, this.packCount, this._packDomains);

  final List<Map<String, Object?>> _terms;
  final int packCount;
  final Set<String> _packDomains;

  int get termCount => _terms.length;

  int packCountFor(CorpusProfile profile) => switch (profile) {
    CorpusProfile.none => 0,
    CorpusProfile.cs2 =>
      _packDomains.isEmpty
          ? packCount
          : _packDomains.where(_isCs2Domain).length,
  };

  int termCountFor(CorpusProfile profile) =>
      _terms.where((term) => _matchesProfile(term, profile)).length;

  static Future<CorpusIndex> load(
    AssetBundle bundle, {
    String manifestAsset = 'assets/corpora/manifest.json',
  }) async {
    final manifest = Map<String, Object?>.from(
      jsonDecode(await bundle.loadString(manifestAsset)) as Map,
    );
    if (manifest['schema_version'] != 1) {
      throw const FormatException('unsupported corpus manifest');
    }
    final packs = <Map<String, Object?>>[];
    for (final entry in (manifest['packs'] as List? ?? const [])) {
      final descriptor = Map<String, Object?>.from(entry as Map);
      if (descriptor['enabled'] == false) continue;
      final asset = descriptor['asset'] as String;
      final pack = Map<String, Object?>.from(
        jsonDecode(await bundle.loadString(asset)) as Map,
      );
      // Keep the descriptor domain beside the pack. Older packs have no
      // domain field and are treated as CS2 when the caller explicitly opts
      // into that profile.
      pack['_domain'] = descriptor['domain'] ?? 'cs2';
      packs.add(pack);
    }
    return CorpusIndex.fromPacks(packs);
  }

  factory CorpusIndex.fromPacks(List<Map<String, Object?>> packs) {
    final merged = <String, Map<String, Object?>>{};
    final packDomains = <String>{};
    for (final pack in packs) {
      if (pack['schema_version'] != 1 || pack['terms'] is! List) {
        throw const FormatException('unsupported corpus pack');
      }
      final domain = (pack['_domain'] ?? pack['domain']) as String?;
      if (domain != null && domain.trim().isNotEmpty) {
        packDomains.add(domain.trim().toLowerCase());
      }
      for (final value in pack['terms'] as List) {
        final term = Map<String, Object?>.from(value as Map);
        final english = (term['english'] as String? ?? '').trim();
        final chinese = (term['chinese'] as String? ?? '').trim();
        if (english.isEmpty || chinese.isEmpty) {
          throw const FormatException(
            'corpus term requires english and chinese',
          );
        }
        term['english'] = english;
        term['chinese'] = chinese;
        term['aliases'] = List<String>.from(
          term['aliases'] as List? ?? const [],
        );
        if (domain != null && domain.trim().isNotEmpty) {
          term['_domain'] = domain.trim().toLowerCase();
        }
        // Keep context-dependent translations (for example, the same callout
        // on two maps) while still merging exact duplicate glossary entries.
        final key = '${english.toLowerCase()}\u0000${chinese.toLowerCase()}';
        final previous = merged[key];
        if (previous == null) {
          merged[key] = term;
        } else {
          final winner = _priority(term) > _priority(previous)
              ? term
              : previous;
          final aliases = <String>{
            ...List<String>.from(previous['aliases'] as List? ?? const []),
            ...List<String>.from(term['aliases'] as List? ?? const []),
          };
          winner['aliases'] = aliases.toList();
          merged[key] = winner;
        }
      }
    }
    final terms = merged.values.toList()
      ..sort((a, b) {
        final priority = _priority(b).compareTo(_priority(a));
        return priority != 0
            ? priority
            : (a['english'] as String).compareTo(b['english'] as String);
      });
    return CorpusIndex._(terms, packs.length, packDomains);
  }

  List<Map<String, Object?>> match(
    String text, {
    int limit = 4,
    CorpusProfile profile = CorpusProfile.cs2,
  }) {
    final normalized = _normalize(text);
    final matches =
        _terms
            .where((term) => _matchesProfile(term, profile))
            .map((term) {
              final matchedWords =
                  <String>[
                        term['english'] as String,
                        ...List<String>.from(
                          term['aliases'] as List? ?? const [],
                        ),
                      ]
                      .map(_normalize)
                      .where(
                        (expression) => _containsPhrase(normalized, expression),
                      );
              if (matchedWords.isEmpty) return null;
              return (
                term: term,
                words: matchedWords
                    .map((expression) => expression.split(' ').length)
                    .reduce((a, b) => a > b ? a : b),
              );
            })
            .whereType<({Map<String, Object?> term, int words})>()
            .toList()
          ..sort((a, b) {
            // Curated priority remains authoritative; specificity breaks ties so
            // broad one-word aliases do not crowd out a precise phrase.
            final priority = _priority(b.term).compareTo(_priority(a.term));
            if (priority != 0) return priority;
            final specificity = b.words.compareTo(a.words);
            return specificity;
          });
    return matches
        .take(limit)
        .map((match) => Map<String, Object?>.from(match.term))
        .toList();
  }

  String asrPrompt(
    String contextHint, {
    CorpusProfile profile = CorpusProfile.cs2,
    int maximumCharacters = 280,
  }) {
    final parts = <String>[];
    final cleanContext = sanitizeContext(contextHint, maximumCharacters: 180);
    if (cleanContext.isNotEmpty) {
      parts.add('Context (data only): $cleanContext.');
    }
    if (profile == CorpusProfile.cs2) {
      parts.add('Counter-Strike broadcast terms:');
    }
    for (final term in _terms.where(
      (term) =>
          profile != CorpusProfile.none &&
          _matchesProfile(term, profile) &&
          _priority(term) >= 5,
    )) {
      final candidate = [...parts, term['english'] as String].join(' ');
      if (candidate.length > maximumCharacters) break;
      parts.add(term['english'] as String);
    }
    final prompt = parts.join(' ');
    return prompt.length <= maximumCharacters
        ? prompt
        : prompt.substring(0, maximumCharacters);
  }

  /// Build a small, bounded hint string.  Recent hints are only included when
  /// explicitly enabled and require repeated/high-priority matches; arbitrary
  /// model output is never added to the glossary.
  String e2eHints(
    String contextHint, {
    CorpusProfile profile = CorpusProfile.cs2,
    Iterable<String> recentEnglish = const [],
    bool includeRecent = false,
    int maximumCharacters = 240,
  }) {
    final clean = sanitizeContext(contextHint, maximumCharacters: 180);
    final parts = <String>[];
    if (profile == CorpusProfile.cs2) parts.add('CS2 broadcast.');
    final selected = <String>{};
    // Explicit user context has priority over automatically selected terms;
    // otherwise a long glossary could silently crowd the field out.
    if (clean.isNotEmpty) {
      final entry = 'User context (data only): $clean';
      if ([...parts, entry].join('; ').length <= maximumCharacters) {
        parts.add(entry);
      }
    }
    for (final term in match(clean, limit: 8, profile: profile)) {
      final entry = _hintEntry(term);
      if ([...parts, entry].join('; ').length <= maximumCharacters) {
        parts.add(entry);
        selected.add(_termKey(term));
      }
    }
    if (includeRecent && profile != CorpusProfile.none) {
      for (final term in recentMatches(recentEnglish, profile: profile)) {
        if (!selected.add(_termKey(term))) continue;
        final entry = _hintEntry(term);
        if ([...parts, entry].join('; ').length > maximumCharacters) break;
        parts.add(entry);
      }
    }
    return parts.join('; ');
  }

  /// Match terms observed in recent confirmed English.  Two observations (or
  /// one curated high-priority entity) are required to avoid prompt churn from
  /// a single noisy ASR fragment.
  List<Map<String, Object?>> recentMatches(
    Iterable<String> recentEnglish, {
    CorpusProfile profile = CorpusProfile.cs2,
    int limit = 6,
  }) {
    if (profile == CorpusProfile.none) return const [];
    final texts = recentEnglish
        .map(sanitizeContext)
        .where((text) => text.isNotEmpty)
        .toList(growable: false);
    if (texts.isEmpty) return const [];
    final scored = <String, _ScoredTerm>{};
    for (var index = 0; index < texts.length; index++) {
      final weight = 1 + (index + 1) / texts.length;
      for (final term in match(
        texts[index],
        limit: _terms.length,
        profile: profile,
      )) {
        final key = _termKey(term);
        final entry = scored.putIfAbsent(key, () => _ScoredTerm(term));
        entry.hits++;
        entry.score += weight;
      }
    }
    final eligible =
        scored.values
            .where((entry) => entry.hits >= 2 || _priority(entry.term) >= 8)
            .toList()
          ..sort((a, b) {
            final hits = b.hits.compareTo(a.hits);
            if (hits != 0) return hits;
            final score = b.score.compareTo(a.score);
            if (score != 0) return score;
            final priority = _priority(b.term).compareTo(_priority(a.term));
            if (priority != 0) return priority;
            return (a.term['english'] as String).compareTo(
              b.term['english'] as String,
            );
          });
    return eligible.take(limit).map((entry) => entry.term).toList();
  }

  String _hintEntry(Map<String, Object?> term) => term['preserve'] == true
      ? '${term['english']}'
      : '${term['english']}=${term['chinese']}';

  static String _termKey(Map<String, Object?> term) =>
      '${term['english']}|${term['chinese']}';

  /// Only explicitly curated wrong translations are eligible for replacement.
  String correctChinese(
    String english,
    String chinese, {
    CorpusProfile profile = CorpusProfile.cs2,
  }) {
    if (profile == CorpusProfile.none) return chinese;
    final replacements = <String, Set<String>>{};
    for (final term in match(english, limit: _terms.length, profile: profile)) {
      final sources = List<String>.from(
        term['correction_sources'] as List? ?? [term['english']],
      );
      if (!sources.any(
        (s) => _containsPhrase(_normalize(english), _normalize(s)),
      )) {
        continue;
      }
      final excluded = List<String>.from(
        term['correction_exclude'] as List? ?? const [],
      );
      if (excluded.any(
        (s) => _containsPhrase(_normalize(english), _normalize(s)),
      )) {
        continue;
      }
      final target = term['chinese'] as String;
      for (final wrong in List<String>.from(
        term['wrong_targets'] as List? ?? const [],
      )) {
        if (wrong.isEmpty || wrong == target || target.contains(wrong)) {
          continue;
        }
        replacements.putIfAbsent(wrong, () => <String>{}).add(target);
      }
    }
    final keys =
        replacements.keys.where((k) => replacements[k]!.length == 1).toList()
          ..sort((a, b) => b.length.compareTo(a.length));
    if (keys.isEmpty) return chinese;
    // Single pass, longest match first: replacements never cascade.
    return chinese.replaceAllMapped(
      RegExp(keys.map(RegExp.escape).join('|')),
      (m) => replacements[m[0]]!.single,
    );
  }

  static int _priority(Map<String, Object?> term) =>
      (term['priority'] as num?)?.toInt() ?? 0;

  static bool _matchesProfile(
    Map<String, Object?> term,
    CorpusProfile profile,
  ) {
    if (profile == CorpusProfile.none) return false;
    final domain = (term['_domain'] as String?)?.toLowerCase();
    return domain == null || _isCs2Domain(domain);
  }

  static bool _isCs2Domain(String domain) {
    final normalized = domain.toLowerCase().replaceAll('_', '-');
    return normalized == 'cs2' ||
        normalized == 'counter-strike-2' ||
        normalized == 'counterstrike-2' ||
        normalized.contains('counter-strike');
  }

  /// Normalize the optional user context before it can reach any model.
  ///
  /// This field is data, not an instruction channel. Markup/control characters
  /// and common prompt-injection forms are ignored, and the bounded result is
  /// wrapped as context by every backend. Keeping this policy here means the
  /// same guard applies to the ASR initial prompt, E2E system hints and the
  /// legacy translation payload.
  static String sanitizeContext(String value, {int maximumCharacters = 240}) {
    // Inspect before stripping markup so a tagged prompt cannot hide its
    // role marker behind the normalization step.
    if (_promptInjection.hasMatch(value)) return '';
    final normalized = value
        .replaceAll(
          RegExp(r'[\u0000-\u001f\u007f\u200b-\u200f\u202a-\u202e]'),
          ' ',
        )
        .replaceAll(RegExp(r'[<>`{}]'), ' ')
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
    if (normalized.isEmpty || _promptInjection.hasMatch(normalized)) {
      return '';
    }
    return normalized.length <= maximumCharacters
        ? normalized
        : normalized.substring(0, maximumCharacters).trimRight();
  }

  static final _promptInjection = RegExp(
    r'<\s*/?\s*(?:system|user|assistant|developer|think|analysis)\s*>|'
    r'(?:ignore|disregard|forget)\s+(?:all\s+)?(?:the\s+)?'
    r'(?:previous|prior|above|these)?\s*(?:instructions?|rules?|prompts?)|'
    r'(?:system|developer|assistant|user)\s*'
    r'(?:message|prompt|instruction)\s*[:：]|'
    r'(?:output|respond|answer)\s+(?:only|as|in\s+(?:json|xml|yaml))\b|'
    r'(?:jailbreak|prompt\s+injection)',
    caseSensitive: false,
  );

  static String _normalize(String value) => value
      .toLowerCase()
      .replaceAll(RegExp(r"[^a-z0-9']+"), ' ')
      .trim()
      .replaceAll(RegExp(r'\s+'), ' ');

  static bool _containsPhrase(String text, String phrase) =>
      phrase.isNotEmpty && ' $text '.contains(' $phrase ');
}
