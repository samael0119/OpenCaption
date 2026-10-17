import 'corpus.dart';

class _MapEvidence {
  const _MapEvidence(
    this.concept,
    this.maps,
    this.window,
    this.at,
    this.explicit,
  );
  final String concept;
  final Set<String> maps;
  final int window, at;
  final bool explicit;
}

class _TeamEvidence {
  const _TeamEvidence(this.team, this.window, this.at);
  final String team;
  final int window, at;
}

class _PlayerEvidence {
  const _PlayerEvidence(this.player, this.window, this.at);
  final String player;
  final int window, at;
}

class _MembershipEvidence {
  const _MembershipEvidence(this.player, this.team, this.window, this.at);
  final String player, team;
  final int window, at;
}

/// Causal, bounded scene evidence. Roster snapshots are priors, never proof of
/// the current match. Injected vocabulary and duplicate output cannot vote.
class SceneAssistant {
  int _epoch = -1;
  int _clock = 0;
  int _lastOutput = 0;
  String? map;
  List<String> teams = const [];
  // Snapshot candidates never enter the model's confirmed-team hint.
  List<String> teamCandidates = const [];
  final _maps = <_MapEvidence>[];
  final _teams = <_TeamEvidence>[];
  final _players = <_PlayerEvidence>[];
  final _memberships = <_MembershipEvidence>[];
  final _deniedMemberships = <_MembershipEvidence>[];
  final _snapshotTeams = <String, Set<String>>{};
  final _windows = <int>{};
  final _texts = <String>[];
  final _deniedMaps = <String, int>{};

  void reset(int epoch) {
    _epoch = epoch;
    _clock = 0;
    _lastOutput = 0;
    map = null;
    teams = const [];
    teamCandidates = const [];
    _maps.clear();
    _teams.clear();
    _players.clear();
    _memberships.clear();
    _deniedMemberships.clear();
    _snapshotTeams.clear();
    _windows.clear();
    _texts.clear();
    _deniedMaps.clear();
  }

  void observe(
    CorpusIndex corpus,
    String english, {
    required int epoch,
    required int window,
    required int endMs,
    Set<String> injectedConcepts = const {},
  }) {
    if (epoch != _epoch || endMs < _lastOutput || _windows.contains(window)) {
      return;
    }
    _lastOutput = endMs;
    if (endMs > _clock) _clock = endMs;
    _expire(_clock);
    if (_clock - endMs > 45000) return;
    _windows.add(window);
    if (_windows.length > 64) _windows.remove(_windows.first);
    final clean = CorpusIndex.sanitizeContext(english).toLowerCase();
    if (clean.isEmpty || _texts.contains(clean)) return;
    _texts.add(clean);
    if (_texts.length > 12) _texts.removeAt(0);
    final matches = corpus.match(clean, limit: corpus.termCount);
    // Retractions are source evidence even though their negated team mention
    // cannot vote positively. A stale roster snapshot cannot undo them.
    final rawPlayers = matches.where((t) => t['category'] == 'player');
    final rawTeams = matches.where((t) => t['category'] == 'team');
    final retractedInWindow = <String>{};
    for (final player in rawPlayers) {
      for (final team in rawTeams) {
        // A denial may release hinted constraints but cannot establish an
        // alternative affiliation, just like explicit map denial.
        if (!_explicitMembershipDenial(clean, player, team)) {
          continue;
        }
        final p = player['english'] as String;
        final t = team['english'] as String;
        retractedInWindow.add('$p|$t');
        _memberships.removeWhere((e) => e.player == p && e.team == t);
        _deniedMemberships.removeWhere((e) => e.player == p && e.team == t);
        _deniedMemberships.add(_MembershipEvidence(p, t, window, endMs));
      }
    }
    if (_deniedMemberships.length > 32) {
      _deniedMemberships.removeRange(0, _deniedMemberships.length - 32);
    }
    final concepts = <String, Set<String>>{};
    final explicit = <String>{};
    final teamsInWindow = <String, Map<String, Object?>>{};
    final playersInWindow = <String, Map<String, Object?>>{};
    for (final term in matches) {
      if (term['category'] == 'map' && !corpus.isSceneMap(term)) continue;
      final concept = corpus.sceneConceptFor(term);
      if (term['category'] == 'map' && _explicitMapDenial(clean, term)) {
        final denied = term['english'] as String;
        _deniedMaps[denied] = endMs;
        if (map == denied || map == null) {
          map = null;
          _maps.clear();
        }
        continue; // Negation can release a hint, never establish another map.
      }
      if (injectedConcepts.contains(concept) ||
          !_positiveMention(clean, term) ||
          !corpus.allowsPositiveSceneEvidence(clean, term)) {
        continue;
      }
      final owner = CorpusIndex.mapFor(term);
      if (owner != null) {
        concepts.putIfAbsent(concept, () => {}).add(owner);
      } else if (term['category'] == 'map') {
        concepts.putIfAbsent(concept, () => {}).add(term['english'] as String);
        explicit.add(concept);
      } else if (term['category'] == 'team') {
        teamsInWindow[term['english'] as String] = term;
      } else if (term['category'] == 'player') {
        final player = term['english'] as String;
        playersInWindow[player] = term;
        _snapshotTeams[player] = corpus
            .relationsFor(player)
            .where((r) => r.subject == player && r.kind == 'roster_snapshot')
            .map((r) => corpus.canonicalTeam(r.target))
            .whereType<String>()
            .toSet();
      }
    }
    final affiliationTeams = <String>{};
    for (final player in playersInWindow.keys) {
      _players.add(_PlayerEvidence(player, window, endMs));
      for (final team in teamsInWindow.keys) {
        if (_explicitMembership(
          clean,
          playersInWindow[player]!,
          teamsInWindow[team]!,
        )) {
          affiliationTeams.add(team);
          if (retractedInWindow.contains('$player|$team')) continue;
          _deniedMemberships.removeWhere(
            (e) => e.player == player && e.team == team,
          );
          _memberships.add(_MembershipEvidence(player, team, window, endMs));
        }
      }
    }
    if (_players.length > 32) _players.removeRange(0, _players.length - 32);
    if (_memberships.length > 32) {
      _memberships.removeRange(0, _memberships.length - 32);
    }
    final retainedPlayers = {
      ..._players.map((e) => e.player),
      ..._memberships.map((e) => e.player),
    };
    _snapshotTeams.removeWhere(
      (player, _) => !retainedPlayers.contains(player),
    );
    for (final entry in concepts.entries) {
      final evidence = _MapEvidence(
        entry.key,
        entry.value,
        window,
        endMs,
        explicit.contains(entry.key),
      );
      if (evidence.explicit) {
        if (map != null && !entry.value.contains(map)) map = null;
        _maps.removeWhere((old) => old.maps.intersection(entry.value).isEmpty);
      }
      _maps.removeWhere((old) => old.concept == entry.key);
      _maps.add(evidence);
    }
    if (_maps.length > 32) _maps.removeRange(0, _maps.length - 32);
    _resolveMap();
    for (final team in teamsInWindow.keys) {
      // An affiliation must use the independent-player path, not count the
      // same statement again as an unrelated direct team vote.
      if (affiliationTeams.contains(team)) continue;
      _teams.add(_TeamEvidence(team, window, endMs));
    }
    if (_teams.length > 32) _teams.removeRange(0, _teams.length - 32);
    _resolveTeams();
  }

  bool advanceClock(int at) {
    if (at < _clock) return false;
    final old = '$map|${teams.join('|')}|${teamCandidates.join('|')}';
    _clock = at;
    _expire(at);
    return old != '$map|${teams.join('|')}|${teamCandidates.join('|')}';
  }

  void _expire(int at) {
    _deniedMaps.removeWhere((_, deniedAt) => at - deniedAt > 45000);
    _maps.removeWhere((e) => at - e.at > 45000);
    _teams.removeWhere((e) => at - e.at > 90000);
    _players.removeWhere((e) => at - e.at > 90000);
    // Learned speech relations last at most 10 audio minutes, within one
    // epoch. A conflicting current affiliation makes the player ambiguous.
    _memberships.removeWhere((e) => at - e.at > 600000);
    _deniedMemberships.removeWhere((e) => at - e.at > 600000);
    final retainedPlayers = {
      ..._players.map((e) => e.player),
      ..._memberships.map((e) => e.player),
    };
    _snapshotTeams.removeWhere(
      (player, _) => !retainedPlayers.contains(player),
    );
    _resolveMap();
    _resolveTeams();
  }

  void _resolveMap() {
    if (_maps.isEmpty) {
      map = null;
      return;
    }
    var common = _maps.first.maps.toSet();
    for (final evidence in _maps.skip(1)) {
      common = common.intersection(evidence.maps);
    }
    if (common.isEmpty) {
      // Two distinct contrary cues release a prior map within two windows.
      final prior = map;
      final conflict = _maps
          .where((e) => prior != null && !e.maps.contains(prior))
          .toList();
      if (prior != null && conflict.map((e) => e.window).toSet().length >= 2) {
        map = null;
        _maps.removeWhere((e) => e.maps.contains(prior));
        _resolveMap();
      }
      return;
    }
    if (_maps.map((e) => e.concept).toSet().length >= 2 &&
        _maps.map((e) => e.window).toSet().length >= 2 &&
        common.length == 1) {
      map = _deniedMaps.containsKey(common.single) ? null : common.single;
    } else {
      map = null;
    }
  }

  void _resolveTeams() {
    final votes = <String, Set<int>>{};
    for (final e in _teams) {
      votes.putIfAbsent(e.team, () => {}).add(e.window);
    }
    final memberships = <String, Set<String>>{};
    for (final e in _memberships) {
      memberships.putIfAbsent(e.player, () => {}).add(e.team);
    }
    final observedPlayers = <String, Set<String>>{};
    final observedWindows = <String, Set<int>>{};
    final candidatePlayers = <String, Set<String>>{};
    final candidateWindows = <String, Set<int>>{};
    for (final e in _players) {
      final targets = memberships[e.player];
      if (targets != null && targets.length == 1) {
        final team = targets.single;
        observedPlayers.putIfAbsent(team, () => {}).add(e.player);
        observedWindows.putIfAbsent(team, () => {}).add(e.window);
      }
      // Conflicting observed affiliations also invalidate a stale snapshot.
      if (targets != null && targets.length > 1) continue;
      for (final team in targets ?? _snapshotTeams[e.player] ?? <String>{}) {
        if (_deniedMemberships.any(
          (denial) => denial.player == e.player && denial.team == team,
        )) {
          continue;
        }
        candidatePlayers.putIfAbsent(team, () => {}).add(e.player);
        candidateWindows.putIfAbsent(team, () => {}).add(e.window);
      }
    }
    final observed = observedPlayers.keys.where(
      (team) =>
          observedPlayers[team]!.length >= 2 &&
          observedWindows[team]!.length >= 2,
    );
    final qualified = <String>{
      ...observed,
      ...votes.entries.where((e) => e.value.length >= 2).map((e) => e.key),
    }.toList()..sort();
    teams = qualified.length == 2 ? List.unmodifiable(qualified) : const [];
    final candidates =
        candidatePlayers.keys
            .where(
              (team) =>
                  candidatePlayers[team]!.length >= 2 &&
                  candidateWindows[team]!.length >= 2,
            )
            .toList()
          ..sort();
    teamCandidates = List.unmodifiable(candidates.take(4));
  }

  static bool _explicitMembership(
    String text,
    Map<String, Object?> player,
    Map<String, Object?> team,
  ) {
    String names(Map<String, Object?> term) =>
        [
              term['english'] as String,
              ...List<String>.from(term['aliases'] as List? ?? const []),
            ]
            .map(
              (name) => name
                  .toLowerCase()
                  .replaceAll(RegExp(r'[^a-z0-9]+'), ' ')
                  .trim(),
            )
            .where((name) => name.length >= 2)
            .map(RegExp.escape)
            .toSet()
            .join('|');
    final p = names(player);
    final t = names(team);
    final relation = RegExp(
      r'\b'
      '(?:$p)'
      r'\s+(?:of|from|playing for|plays for|is playing for)\s+'
      '(?:$t)'
      r'\b',
    );
    for (final clause in text.split(
      RegExp(r'\b(?:but|however|now|next)\b|[.!?;]'),
    )) {
      final normalized = clause.replaceAll(RegExp(r'[^a-z0-9]+'), ' ').trim();
      if (!relation.hasMatch(normalized)) continue;
      if (RegExp(
        r'\b(?:not|no|never|without|isn t|wasn t|aren t|used to|previous|previously|former|formerly|historical|yesterday|last year|if|would|could|might|perhaps|imagine|20\d\d)\b',
      ).hasMatch(normalized)) {
        continue;
      }
      return true;
    }
    return false;
  }

  static bool _explicitMembershipDenial(
    String text,
    Map<String, Object?> player,
    Map<String, Object?> team,
  ) {
    String names(Map<String, Object?> term) =>
        [
              term['english'] as String,
              ...List<String>.from(term['aliases'] as List? ?? const []),
            ]
            .map(
              (name) => name
                  .toLowerCase()
                  .replaceAll(RegExp(r'[^a-z0-9]+'), ' ')
                  .trim(),
            )
            .where((name) => name.length >= 2)
            .map(RegExp.escape)
            .toSet()
            .join('|');
    final relation = RegExp(
      r'\b(?:'
      '${names(player)}'
      r')\s+(?:is\s+|does\s+)?(?:no longer|not|never|isn t|doesn t)\s+'
      r'(?:plays? for|playing for|from|of|with)\s+(?:'
      '${names(team)}'
      r')\b(?!\s+(?:(?:clan|esports|gaming|team)\s+)?(?:academy|junior|juniors|youth)\b)',
    );
    for (final clause in text.split(
      RegExp(r'\b(?:but|however|now|next)\b|[.!?;]'),
    )) {
      final normalized = clause.replaceAll(RegExp(r'[^a-z0-9]+'), ' ').trim();
      if (RegExp(
        r'\b(?:if|imagine|suppose|supposing|assuming|hypothetically|would|could|might|perhaps|previous|previously|former|formerly|historical|yesterday|last year|used to|20\d\d)\b',
      ).hasMatch(normalized)) {
        continue;
      }
      if (relation.hasMatch(normalized)) return true;
    }
    return false;
  }

  static bool _explicitMapDenial(String text, Map<String, Object?> term) {
    final names = [
      term['english'] as String,
      ...List<String>.from(term['aliases'] as List? ?? const []),
    ];
    for (final clause in text.split(
      RegExp(r'\b(?:but|however|now|next)\b|[.!?;]'),
    )) {
      final normalized = clause.replaceAll(RegExp(r'[^a-z0-9]+'), ' ').trim();
      // Non-factual denials must not revoke a current map or poison later
      // independent cues. A factual clause after "but/now" is checked alone.
      if (RegExp(
        r'\b(?:if|imagine|suppose|supposing|assuming|hypothetically|would|could|might|perhaps|previous|previously|former|formerly|historical|yesterday|last year|used to|20\d\d)\b',
      ).hasMatch(normalized)) {
        continue;
      }
      for (final name in names) {
        final phrase = name
            .toLowerCase()
            .replaceAll(RegExp(r'[^a-z0-9]+'), ' ')
            .trim();
        if (RegExp(
          r'\b(?:not(?: on| playing)?|isn t|aren t|no longer(?: on| playing)?)\s+' +
              RegExp.escape(phrase) +
              r'\b',
        ).hasMatch(normalized)) {
          return true;
        }
      }
    }
    return false;
  }

  static bool _positiveMention(String text, Map<String, Object?> term) {
    final names = [
      term['english'] as String,
      ...List<String>.from(term['aliases'] as List? ?? const []),
    ];
    for (final name in names) {
      final phrase = name
          .toLowerCase()
          .replaceAll(RegExp(r'[^a-z0-9]+'), ' ')
          .trim();
      final curatedShortIdentity =
          phrase.length >= 2 &&
          (term['category'] == 'team' ||
              (term['category'] == 'player' && name == term['english']));
      if (phrase.isEmpty || (phrase.length < 3 && !curatedShortIdentity)) {
        continue; // short aliases cannot vote
      }
      for (final clause in text.split(
        RegExp(r'\b(?:but|instead|however|rather|now|next)\b|[.!?;]'),
      )) {
        final normalized = clause.replaceAll(RegExp(r'[^a-z0-9]+'), ' ').trim();
        // A hypothetical scene/roster must not become direct entity evidence
        // even when membership learning would independently reject it.
        // Ordinary tactical predictions ("FaZe could win") remain eligible.
        if (RegExp(
          r'\b(?:if|imagine|suppose|supposing|assuming|hypothetically)\b',
        ).hasMatch(normalized)) {
          continue;
        }
        final index = ' $normalized '.indexOf(' $phrase ');
        if (index < 0) continue;
        final after = normalized.substring(
          (index + phrase.length).clamp(0, normalized.length),
        );
        // Unknown youth-roster names must not vote for a senior team through
        // a shorter curated alias. Known full youth-team terms still work.
        if (term['category'] == 'team' &&
            RegExp(
              r'^\s+(?:(?:clan|esports|gaming|team)\s+)?(?:academy|junior|juniors|youth)\b',
            ).hasMatch(after)) {
          continue;
        }
        final before = normalized.substring(
          0,
          index.clamp(0, normalized.length),
        );
        if (RegExp(
          r'\b(?:not|no|never|without|isn t|wasn t|aren t|don t|can t)\b',
        ).hasMatch(before)) {
          continue;
        }
        if (RegExp(
          r'\b(?:previous|previously|former|formerly|historical|yesterday|last year|used to|20\d\d)\b',
        ).hasMatch(normalized)) {
          continue;
        }
        return true;
      }
    }
    return false;
  }
}
