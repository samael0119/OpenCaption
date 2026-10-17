import 'dart:convert';
import 'dart:collection';

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

/// A dated relationship is separate from the stable entity/alias spelling.
/// A source snapshot is an observation date, not an effective roster interval.
class CorpusRelation {
  const CorpusRelation({
    required this.subject,
    required this.target,
    required this.kind,
    this.observedAt,
    this.validFrom,
    this.validUntil,
    this.sources = const [],
  });
  final String subject, target, kind;
  final DateTime? observedAt, validFrom, validUntil;
  final List<String> sources;
  bool appliesAt(DateTime? date) =>
      date != null &&
      validFrom != null &&
      validUntil != null &&
      !date.isBefore(validFrom!) &&
      date.isBefore(validUntil!);
}

class _ScoredTerm {
  _ScoredTerm(this.term);

  final Map<String, Object?> term;
  int hits = 0;
  double score = 0;
}

/// A retrieval suggestion is vocabulary, never evidence of a spoken event or
/// the current roster. Its provenance stays available to diagnostic callers.
class CorpusHintCandidate {
  CorpusHintCandidate({
    required Map<String, Object?> term,
    required this.anchor,
    required this.reason,
    required Iterable<String> sourceRefs,
    this.matchDate,
  }) : term = Map.unmodifiable(term),
       sourceRefs = List.unmodifiable(sourceRefs);
  final Map<String, Object?> term;
  final String anchor, reason;
  final List<String> sourceRefs;
  final DateTime? matchDate;
}

class CorpusIndex {
  CorpusIndex._(this._terms, this.packCount, this._packDomains);

  final List<Map<String, Object?>> _terms;
  final int packCount;
  final List<String> _packDomains;

  late final Map<String, String> _mapConcepts = _buildMapConcepts();
  late final Set<String> _preservedIdentifiers = Set.unmodifiable(
    _terms
        .where(
          (t) =>
              _matchesProfile(t, CorpusProfile.cs2) &&
              t['preserve'] == true &&
              const {'player', 'team', 'map'}.contains(t['category']),
        )
        .expand(
          (t) => [
            t['english'] as String,
            ...List<String>.from(t['aliases'] as List? ?? const []).take(4),
          ],
        )
        .take(1024)
        .where(
          (name) => RegExp(r'^[A-Za-z0-9][A-Za-z0-9_-]{1,31}$').hasMatch(name),
        )
        .take(256)
        .toSet(),
  );

  Set<String> preservedIdentifiers({
    CorpusProfile profile = CorpusProfile.cs2,
  }) => profile == CorpusProfile.cs2 ? _preservedIdentifiers : const {};

  Map<String, String> _buildMapConcepts() {
    final parents = <String, String>{};
    String find(String name) {
      var root = name;
      while (parents[root] != root) {
        root = parents[root]!;
      }
      while (name != root) {
        final next = parents[name]!;
        parents[name] = root;
        name = next;
      }
      return root;
    }

    for (final term in _terms.where(
      (t) =>
          t['category'] == 'map_callout' &&
          _matchesProfile(t, CorpusProfile.cs2),
    )) {
      final names = [
        term['english'] as String,
        ...List<String>.from(term['aliases'] as List? ?? const []),
      ].map(_normalize).where((name) => name.isNotEmpty).toSet().toList();
      for (final name in names) {
        parents.putIfAbsent(name, () => name);
      }
      for (final name in names.skip(1)) {
        final a = find(names.first), b = find(name);
        if (a != b) {
          if (a.compareTo(b) < 0) {
            parents[b] = a;
          } else {
            parents[a] = b;
          }
        }
      }
    }
    return {for (final name in parents.keys) name: find(name)};
  }

  /// Shared curated aliases carry one ambiguous concept, not extra votes.
  String sceneConceptFor(Map<String, Object?> term) {
    final english = _normalize(term['english'] as String);
    return term['category'] == 'map_callout'
        ? _mapConcepts[english] ?? english
        : english;
  }

  int get termCount => _terms.length;

  /// Old packs used category=map for both named maps and vocabulary such as
  /// bombsite/spawn. Only named entities may vote for, deny or select a map.
  bool isSceneMap(Map<String, Object?> term) {
    if (term['category'] != 'map' ||
        !_matchesProfile(term, CorpusProfile.cs2)) {
      return false;
    }
    final declared = term['scene_entity'];
    if (declared != null) return declared == true;
    final english = _normalize(term['english'] as String);
    return term['preserve'] == true ||
        term['context'] == 'CS2 地图' ||
        _terms.any((t) => _normalize(mapFor(t) ?? '') == english);
  }

  /// Finite, curated choices for a user correction, not roster inference.
  List<String> sceneChoices(String category) {
    if (!const {'map', 'team'}.contains(category)) return const [];
    final choices =
        _terms
            .where(
              (t) =>
                  t['category'] == category &&
                  (category != 'map' || isSceneMap(t)) &&
                  _matchesProfile(t, CorpusProfile.cs2),
            )
            .map((t) => t['english'] as String)
            .toSet()
            .toList()
          ..sort();
    return List.unmodifiable(choices);
  }

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
    final packDomains = <String>[];
    for (final pack in packs) {
      if (pack['schema_version'] != 1 || pack['terms'] is! List) {
        throw const FormatException('unsupported corpus pack');
      }
      final domain = (pack['_domain'] ?? pack['domain']) as String?;
      packDomains.add(
        domain == null || domain.trim().isEmpty
            ? 'cs2'
            : domain.trim().toLowerCase(),
      );
      for (final value in pack['terms'] as List) {
        final term = Map<String, Object?>.from(value as Map);
        final english = (term['english'] as String? ?? '').trim();
        final chinese = (term['chinese'] as String? ?? '').trim();
        if (english.isEmpty || chinese.isEmpty) {
          throw const FormatException(
            'corpus term requires english and chinese',
          );
        }
        _validateTermPolicies(term);
        _validateRelatedTerms(term);
        term['_pack_id'] = pack['id'];
        term['_snapshot'] = (pack['provenance'] as Map?)?['snapshot'];
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
        final key = _termKey(term);
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
          winner['source_refs'] = <String>{
            ...List<String>.from(previous['source_refs'] as List? ?? const []),
            ...List<String>.from(term['source_refs'] as List? ?? const []),
          }.toList();
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
    String? map,
    bool strongAliasesOnly = false,
  }) {
    final normalized = _normalize(text);
    final matches =
        _terms
            .where(
              (term) =>
                  _matchesProfile(term, profile) && _matchesMap(term, map),
            )
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
                        (expression) =>
                            _containsPhrase(normalized, expression) &&
                            (!strongAliasesOnly ||
                                expression.length >= 3 ||
                                (term['category'] == 'player' &&
                                    expression.length >= 2 &&
                                    expression ==
                                        _normalize(term['english'] as String))),
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
    int maximumTokens = 96,
    String? map,
    List<String> teams = const [],
    bool mapIsManual = false,
    bool teamsAreManual = false,
    // Explicit diagnostic candidate input. Normal session hints do not enable
    // unvalidated proactive vocabulary or semantic history by default.
    List<CorpusHintCandidate> related = const [],
    DateTime? matchDate,
  }) {
    final clean = sanitizeContext(contextHint, maximumCharacters: 180);
    final parts = <String>[];
    if (profile == CorpusProfile.cs2) parts.add('CS2 broadcast.');
    final selected = <String>{};
    bool fits(String entry) {
      final candidate = [...parts, entry].join('; ');
      return candidate.length <= maximumCharacters &&
          estimateHintTokens(candidate) <= maximumTokens;
    }

    final mapEntry =
        'Map: $map (${mapIsManual ? 'user corrected' : 'inferred'})';
    final teamEntry =
        'Teams: ${teams.join(' vs ')} (${teamsAreManual ? 'user corrected' : 'observed'})';
    var mapAdded = false, teamsAdded = false;
    void addMap() {
      if (profile != CorpusProfile.none && map != null && fits(mapEntry)) {
        parts.add(mapEntry);
        mapAdded = true;
      }
    }

    void addTeams() {
      if (profile != CorpusProfile.none &&
          teams.length == 2 &&
          fits(teamEntry)) {
        parts.add(teamEntry);
        teamsAdded = true;
      }
    }

    // Structured user corrections outrank optional prose. Ordinary user
    // context retains its previous priority over automatically inferred data.
    if (mapIsManual) addMap();
    if (teamsAreManual) addTeams();
    if (clean.isNotEmpty) {
      var contextData = clean;
      if (mapAdded || teamsAdded) {
        while (contextData.isNotEmpty &&
            !fits('User context (data only): $contextData')) {
          contextData = contextData
              .substring(0, contextData.length - 1)
              .trimRight();
        }
      }
      final entry = 'User context (data only): $contextData';
      if (contextData.isNotEmpty && fits(entry)) parts.add(entry);
    }
    if (!mapAdded) addMap();
    if (!teamsAdded) addTeams();
    for (final term in match(clean, limit: 8, profile: profile, map: map)) {
      if (!_passesSourcePolicy(clean, term, 'hint_sources', 'hint_exclude')) {
        continue;
      }
      final entry = _hintEntry(term);
      if (fits(entry)) {
        parts.add(entry);
        selected.add(_termKey(term));
      }
    }
    if (includeRecent && profile != CorpusProfile.none) {
      for (final term in recentMatches(
        recentEnglish,
        profile: profile,
        map: map,
      )) {
        if (!selected.add(_termKey(term))) continue;
        final entry = _hintEntry(term);
        if (!fits(entry)) continue;
        parts.add(entry);
      }
    }
    if (includeRecent && profile != CorpusProfile.none) {
      for (final candidate in related.take(2)) {
        final term = candidate.term;
        if (!_matchesProfile(term, profile) ||
            !_matchesMap(term, map) ||
            (mapFor(term) != null && map == null) ||
            !_terms.any((t) => _termKey(t) == _termKey(term)) ||
            (candidate.reason == 'effective_roster' &&
                (matchDate == null ||
                    teams.length != 2 ||
                    candidate.matchDate != matchDate ||
                    teams
                            .map(canonicalTeam)
                            .whereType<String>()
                            .toSet()
                            .length !=
                        2 ||
                    !teams.map(canonicalTeam).contains(candidate.anchor))) ||
            !selected.add(_termKey(term))) {
          continue;
        }
        final entry =
            'Candidate vocabulary (not evidence): ${_hintEntry(term)}';
        if (fits(entry)) parts.add(entry);
      }
    }
    return parts.join('; ');
  }

  /// One-hop, explicitly sourced candidates, for shadow evaluation first.
  /// Unknown map/date or ambiguous meanings/rosters cause abstention. No
  /// candidate is allowed to become its own seed on the next observation.
  List<CorpusHintCandidate> relatedCandidates(
    Iterable<String> recentEnglish, {
    CorpusProfile profile = CorpusProfile.cs2,
    String? map,
    List<String> teams = const [],
    DateTime? matchDate,
    Set<String> injectedConcepts = const {},
    int limit = 2,
  }) {
    if (profile == CorpusProfile.none || limit <= 0) return const [];
    final texts = Queue<String>();
    for (final source in recentEnglish) {
      texts.add(sanitizeContext(source));
      if (texts.length > 6) texts.removeFirst();
    }
    final recent = texts.where((s) => s.isNotEmpty).toList();
    final observed = <String>{};
    for (final text in recent) {
      observed.addAll(
        match(
          text,
          limit: termCount,
          profile: profile,
          map: map,
          strongAliasesOnly: true,
        ).map(sceneConceptFor),
      );
    }
    final canonicalMap = map == null
        ? null
        : _terms
              .where(
                (t) =>
                    _matchesProfile(t, profile) &&
                    isSceneMap(t) &&
                    _normalize(t['english'] as String) == _normalize(map),
              )
              .firstOrNull;
    final selected = <String>{};
    final candidates = <CorpusHintCandidate>[];
    void add(
      Map<String, Object?> term,
      String anchor,
      String reason,
      Iterable<String> refs,
    ) {
      final concept = sceneConceptFor(term);
      if (observed.contains(concept) ||
          injectedConcepts.contains(concept) ||
          !selected.add(concept)) {
        return;
      }
      candidates.add(
        CorpusHintCandidate(
          term: term,
          anchor: anchor,
          reason: reason,
          sourceRefs: refs,
          matchDate: reason == 'effective_roster' ? matchDate : null,
        ),
      );
    }

    for (final text in recent.reversed) {
      if (RegExp(
        r"\b(?:not|no|never|without|previous|previously|former|formerly|historical|yesterday|last map|last year|used to|if|would|could|might|perhaps|imagine|20\d\d)\b|n't\b",
      ).hasMatch(text.toLowerCase())) {
        continue;
      }
      for (final anchor in match(
        text,
        limit: termCount,
        profile: profile,
        map: map,
        strongAliasesOnly: true,
      )) {
        if (injectedConcepts.contains(sceneConceptFor(anchor)) ||
            !_passesSourcePolicy(
              text,
              anchor,
              'hint_sources',
              'hint_exclude',
            ) ||
            !allowsPositiveSceneEvidence(text, anchor)) {
          continue;
        }
        if (canonicalMap != null &&
            mapFor(anchor) == canonicalMap['english'] &&
            _passesSourcePolicy(
              text,
              anchor,
              'related_sources',
              'related_exclude',
            )) {
          for (final raw in anchor['related_terms'] as List? ?? const []) {
            final relation = Map<String, Object?>.from(raw as Map);
            if (relation['map'] != canonicalMap['english']) continue;
            final targets = _terms
                .where(
                  (t) =>
                      _matchesProfile(t, profile) &&
                      mapFor(t) == canonicalMap['english'] &&
                      _normalize(t['english'] as String) ==
                          _normalize(relation['target'] as String),
                )
                .toList();
            if (targets.isEmpty ||
                targets.any((t) => t['hint_sources'] != null) ||
                targets.map((t) => t['chinese']).toSet().length != 1) {
              continue;
            }
            add(
              targets.first,
              anchor['english'] as String,
              'map_route',
              List<String>.from(relation['source_refs'] as List),
            );
          }
        }
      }
    }
    // A known date and two canonical current teams are necessary for roster
    // expansion; a dated snapshot alone still does not have an effective range.
    final canonicalTeams = teams.map(canonicalTeam).whereType<String>().toSet();
    if (matchDate != null && teams.length == 2 && canonicalTeams.length == 2) {
      for (final term in _terms.where(
        (t) => _matchesProfile(t, profile) && t['category'] == 'player',
      )) {
        final active = relationsFor(term['english'] as String)
            .where(
              (r) =>
                  r.subject == term['english'] &&
                  r.kind == 'roster' &&
                  r.appliesAt(matchDate),
            )
            .toList();
        final owners = active.map((r) => canonicalTeam(r.target)).toSet();
        if (owners.length != 1 ||
            owners.single == null ||
            !canonicalTeams.contains(owners.single) ||
            term['hint_sources'] != null) {
          continue;
        }
        if (active.any(
          (r) =>
              r.sources.isEmpty ||
              r.sources.any((v) {
                final uri = Uri.tryParse(v);
                return uri == null || uri.scheme != 'https' || uri.host.isEmpty;
              }),
        )) {
          continue;
        }
        add(
          term,
          owners.single!,
          'effective_roster',
          active.expand((r) => r.sources).toSet(),
        );
      }
    }
    return List.unmodifiable(candidates.take(limit.clamp(0, 4)));
  }

  /// Match terms observed in recent confirmed English.  Two observations (or
  /// one curated high-priority entity) are required to avoid prompt churn from
  /// a single noisy ASR fragment.
  List<Map<String, Object?>> recentMatches(
    Iterable<String> recentEnglish, {
    CorpusProfile profile = CorpusProfile.cs2,
    int limit = 6,
    String? map,
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
        map: map,
        strongAliasesOnly: true,
      )) {
        if (!_passesSourcePolicy(
          texts[index],
          term,
          'hint_sources',
          'hint_exclude',
        )) {
          continue;
        }
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
    final translations = <String, Set<String>>{};
    for (final entry in eligible) {
      translations
          .putIfAbsent(sceneConceptFor(entry.term), () => {})
          .add(entry.term['chinese'] as String);
    }
    return eligible
        .where((e) => translations[sceneConceptFor(e.term)]!.length == 1)
        .take(limit)
        .map((entry) => entry.term)
        .toList();
  }

  /// Conservative budget proxy until the runtime exposes exact tokenizer usage.
  /// ASCII <=3 characters/token; non-ASCII charged 2. Never called exact usage.
  static int estimateHintTokens(String value) {
    final wide = value.runes.where((r) => r > 127).length;
    return ((value.runes.length - wide) / 3).ceil() + wide * 2;
  }

  String _hintEntry(Map<String, Object?> term) => term['preserve'] == true
      ? '${term['english']}'
      : '${term['english']}=${term['chinese']}';

  // Equal text is not equal meaning. Keep map/team membership, domain and
  // correction predicates intact rather than choosing a higher-priority row.
  static String _termKey(Map<String, Object?> term) => jsonEncode([
    (term['english'] as String).toLowerCase(),
    (term['chinese'] as String).toLowerCase(),
    term['_domain'],
    term['category'],
    term['scene_entity'],
    term['context'],
    term['preserve'],
    term['correction_sources'],
    term['correction_exclude'],
    term['correction_target_exclude'],
    term['hint_sources'],
    term['hint_exclude'],
    term['scene_sources'],
    term['scene_exclude'],
    term['related_terms'],
    term['related_sources'],
    term['related_exclude'],
    term['wrong_targets'],
    term['relations'],
    term['_snapshot'],
  ]);

  /// Curated team aliases share a stable identity, independently of rosters.
  String? canonicalTeam(String name) {
    final normalized = _normalize(name);
    final teams = match(name, limit: termCount)
        .where(
          (term) =>
              term['category'] == 'team' &&
              [
                term['english'] as String,
                ...List<String>.from(term['aliases'] as List? ?? const []),
              ].any((alias) => _normalize(alias) == normalized),
        )
        .map((term) => term['english'] as String)
        .toSet();
    return teams.length == 1 ? teams.single : null;
  }

  List<CorpusRelation> relationsFor(String english) {
    final relations = <CorpusRelation>[];
    for (final term in match(english, limit: _terms.length)) {
      final owner = mapFor(term);
      final context = term['context'] as String? ?? '';
      final roster = term['category'] == 'player'
          ? RegExp(r'^战队[：:]\s*(.+)$').firstMatch(context.trim())?.group(1)
          : null;
      final target = owner ?? roster;
      if (target != null) {
        relations.add(
          CorpusRelation(
            subject: term['english'] as String,
            target: target.trim(),
            kind: owner == null ? 'roster_snapshot' : 'map_callout',
            observedAt: DateTime.tryParse(term['_snapshot'] as String? ?? ''),
            sources: List.unmodifiable(
              List<String>.from(term['source_refs'] as List? ?? const []),
            ),
          ),
        );
      }
      for (final raw in term['relations'] as List? ?? const []) {
        final row = Map<String, Object?>.from(raw as Map);
        final from = DateTime.tryParse(row['valid_from'] as String? ?? '');
        final until = DateTime.tryParse(row['valid_until'] as String? ?? '');
        if (from != null && until != null && !until.isAfter(from)) {
          throw const FormatException('invalid relation effective interval');
        }
        relations.add(
          CorpusRelation(
            subject: term['english'] as String,
            target: row['target'] as String,
            kind: row['kind'] as String,
            observedAt: DateTime.tryParse(row['observed_at'] as String? ?? ''),
            validFrom: from,
            validUntil: until,
            sources: List.unmodifiable(
              List<String>.from(row['source_refs'] as List? ?? const []),
            ),
          ),
        );
      }
    }
    return List.unmodifiable(relations);
  }

  static String? mapFor(Map<String, Object?> term) {
    if (term['category'] != 'map_callout') return null;
    final context = term['context'] as String? ?? '';
    final match = RegExp(r'^地图[：:]\s*([^；;\n]+)').firstMatch(context.trim());
    return match?.group(1)?.trim();
  }

  static bool _matchesMap(Map<String, Object?> term, String? map) {
    final owner = mapFor(term);
    return map == null || owner == null || _normalize(owner) == _normalize(map);
  }

  /// Only explicitly curated wrong translations are eligible for replacement.
  String correctChinese(
    String english,
    String chinese, {
    CorpusProfile profile = CorpusProfile.cs2,
    String? map,
  }) {
    if (profile == CorpusProfile.none) return chinese;
    final replacements = <String, Set<String>>{};
    for (final term in match(
      english,
      limit: _terms.length,
      profile: profile,
      map: map,
    )) {
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
      // A source cue does not make every occurrence in a multi-clause Chinese
      // reply a game term. Abstain when a curated ordinary meaning is present.
      final targetExcluded = List<String>.from(
        term['correction_target_exclude'] as List? ?? const [],
      );
      final compactChinese = chinese.replaceAll(RegExp(r'\s+'), '');
      if (targetExcluded.any(
        (phrase) =>
            compactChinese.contains(phrase.replaceAll(RegExp(r'\s+'), '')),
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

  /// Positive scene evidence has its own semantic scope; glossary suggestions
  /// and explicit denials must not be treated as the same task.
  bool allowsPositiveSceneEvidence(String source, Map<String, Object?> term) =>
      _passesSourcePolicy(source, term, 'scene_sources', 'scene_exclude');

  static bool _passesSourcePolicy(
    String text,
    Map<String, Object?> term,
    String sourcesKey,
    String excludeKey,
  ) {
    final normalized = _normalize(text);
    final sources = term[sourcesKey] as List?;
    if (sources != null &&
        !sources.any(
          (s) => _containsPhrase(normalized, _normalize(s as String)),
        )) {
      return false;
    }
    return !(term[excludeKey] as List? ?? const []).any(
      (s) => _containsPhrase(normalized, _normalize(s as String)),
    );
  }

  static void _validateTermPolicies(Map<String, Object?> term) {
    if (term['scene_entity'] != null && term['scene_entity'] is! bool) {
      throw const FormatException('invalid scene entity declaration');
    }
    for (final key in const [
      'wrong_targets',
      'correction_sources',
      'correction_exclude',
      'correction_target_exclude',
      'hint_sources',
      'hint_exclude',
      'scene_sources',
      'scene_exclude',
      'related_sources',
      'related_exclude',
    ]) {
      final value = term[key];
      if (value == null) continue;
      if (value is! List ||
          value.length > 32 ||
          value.any(
            (v) => v is! String || v.trim().isEmpty || v.length > 160,
          )) {
        throw FormatException('invalid corpus policy: $key');
      }
      if (const {
            'correction_sources',
            'correction_exclude',
            'hint_sources',
            'hint_exclude',
            'scene_sources',
            'scene_exclude',
            'related_sources',
            'related_exclude',
          }.contains(key) &&
          value.any((v) => _normalize(v as String).isEmpty)) {
        throw FormatException('unsupported corpus source policy: $key');
      }
    }
    final wrong = term['wrong_targets'] as List? ?? const [];
    if (wrong.isNotEmpty &&
        (term['correction_sources'] as List? ?? const []).isEmpty) {
      throw const FormatException(
        'automatic correction requires explicit source cues',
      );
    }
    for (final key in ['hint_sources', 'scene_sources', 'related_sources']) {
      if (term[key] != null && (term[key] as List).isEmpty) {
        throw FormatException('$key cues cannot be empty');
      }
    }
  }

  static void _validateRelatedTerms(Map<String, Object?> term) {
    final rows = term['related_terms'];
    if (rows == null) return;
    if (rows is! List ||
        rows.length > 8 ||
        mapFor(term) == null ||
        (term['related_sources'] as List? ?? const []).isEmpty) {
      throw const FormatException('invalid related vocabulary');
    }
    for (final raw in rows) {
      if (raw is! Map ||
          raw['kind'] != 'map_route' ||
          raw['map'] != mapFor(term) ||
          raw['target'] is! String ||
          (raw['target'] as String).length > 64 ||
          _normalize(raw['target'] as String).isEmpty ||
          raw['reviewed_at'] is! String ||
          DateTime.tryParse(raw['reviewed_at'] as String) == null ||
          raw['map_version'] is! String ||
          (raw['map_version'] as String).isEmpty) {
        throw const FormatException('invalid related vocabulary relation');
      }
      final refs = raw['source_refs'];
      if (refs is! List ||
          refs.isEmpty ||
          refs.length > 4 ||
          refs.any((v) {
            if (v is! String || v.length > 512) return true;
            final uri = Uri.tryParse(v);
            return uri == null || uri.scheme != 'https' || uri.host.isEmpty;
          })) {
        throw const FormatException('related vocabulary requires sources');
      }
    }
  }

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
