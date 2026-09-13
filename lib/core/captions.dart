enum SessionPhase {
  idle,
  preparing,
  listening,
  waiting,
  pausing,
  paused,
  ended,
}

enum CaptionStatus { queued, translating, ready, failed, gap }

enum TranslationMode { mlKit, qwen, external }

class Caption {
  Caption({
    required this.id,
    required this.epoch,
    required this.sequence,
    required this.startMs,
    required this.endMs,
    required this.english,
    required DateTime createdAt,
    this.status = CaptionStatus.queued,
    this.chinese = '',
    this.errorCode,
  }) : createdAt = createdAt,
       lastAttemptAt = createdAt;
  final String id;
  final int epoch, sequence, startMs, endMs;
  final String english;
  final DateTime createdAt;
  DateTime lastAttemptAt;
  int attempts = 0;
  CaptionStatus status;
  String chinese;
  String? errorCode;
}

/// Stable English is immutable. Only punctuation-complete common prefixes may
/// be committed before an utterance ends. This is a heuristic, not confidence.
class StableText {
  String _previous = '';
  String _committed = '';
  int _window = -1;
  bool conflict = false;
  String temporary = '';

  void reset() {
    _previous = _committed = temporary = '';
    _window = -1;
    conflict = false;
  }

  String accept(
    int window,
    String text, {
    required bool finalResult,
    required bool allowEarly,
  }) {
    if (_window != window) {
      _window = window;
      _previous = _committed = '';
      conflict = false;
    }
    text = text.trim().replaceAll(RegExp(r'\s+'), ' ');
    if (_committed.isNotEmpty && !text.startsWith(_committed)) {
      conflict = true;
      temporary = '识别修订与已确认内容冲突，保留原字幕';
      _previous = text;
      return '';
    }
    var boundary = _committed.length;
    if (finalResult) {
      boundary = text.length;
    } else if (allowEarly) {
      var common = 0;
      while (common < text.length &&
          common < _previous.length &&
          text[common] == _previous[common]) {
        common++;
      }
      // Require whitespace after punctuation so IDs such as "s1mple" and
      // decimal scores cannot be split by a partial prefix.
      for (final match in RegExp(r'[.!?;](?:\s|$)').allMatches(text)) {
        final punctuationEnd = match.start + 1;
        final previousBoundary =
            punctuationEnd == _previous.length ||
            (punctuationEnd < _previous.length &&
                _previous[punctuationEnd] == ' ');
        if (previousBoundary &&
            punctuationEnd <= common &&
            punctuationEnd > boundary) {
          boundary = punctuationEnd;
        }
      }
    }
    final added = text.substring(_committed.length, boundary).trim();
    _committed = text.substring(0, boundary).trimRight();
    temporary = text.substring(_committed.length).trim();
    _previous = text;
    return added;
  }
}

class CaptionLedger {
  CaptionLedger({this.maxItems = 1000}) : assert(maxItems > 0);

  /// Keep the subtitle history bounded during long-running sessions.
  ///
  /// Queued/translating items are retained preferentially so trimming the
  /// visible history does not discard work that is still in flight. If an
  /// unusually large backlog exceeds the limit, the oldest item is removed.
  final int maxItems;
  final List<Caption> items = [];
  final Set<String> _ids = {};
  int _nextSequence = 0;

  int get latestSequence => items.isEmpty ? -1 : items.last.sequence;

  Caption? append({
    required String id,
    required int epoch,
    required int startMs,
    required int endMs,
    required String english,
    required DateTime now,
  }) {
    if (!_ids.add(id)) return null;
    final item = Caption(
      id: id,
      epoch: epoch,
      sequence: _nextSequence++,
      startMs: startMs,
      endMs: endMs,
      english: english,
      createdAt: now,
    );
    items.add(item);
    _trimHistory();
    return item;
  }

  void _trimHistory() {
    while (items.length > maxItems) {
      var index = items.indexWhere(
        (item) =>
            item.status != CaptionStatus.queued &&
            item.status != CaptionStatus.translating,
      );
      if (index < 0) index = 0;
      final removed = items.removeAt(index);
      _ids.remove(removed.id);
    }
  }

  bool complete(
    String id,
    int epoch, {
    String? text,
    String? error,
    bool allowEmpty = false,
  }) {
    final matches = items.where((s) => s.id == id && s.epoch == epoch);
    if (matches.isEmpty) return false;
    final item = matches.first;
    if (item.status != CaptionStatus.translating) return false;
    if (error != null || text == null || (!allowEmpty && text.trim().isEmpty)) {
      item.status = CaptionStatus.failed;
      item.errorCode = error ?? 'empty_translation';
    } else {
      item.status = CaptionStatus.ready;
      item.chinese = text.trim();
    }
    return true;
  }

  bool start(String id, int epoch, DateTime now) {
    final matches = items.where((s) => s.id == id && s.epoch == epoch);
    if (matches.isEmpty) return false;
    final item = matches.first;
    if (item.status != CaptionStatus.queued) return false;
    item.status = CaptionStatus.translating;
    item.errorCode = null;
    item.lastAttemptAt = now;
    item.attempts++;
    return true;
  }

  bool requeue(String id, int epoch) {
    final matches = items.where((s) => s.id == id && s.epoch == epoch);
    if (matches.isEmpty) return false;
    final item = matches.first;
    if (item.status != CaptionStatus.translating) return false;
    item.status = CaptionStatus.queued;
    item.errorCode = null;
    return true;
  }

  bool retry(String id, int epoch, DateTime now) {
    final matches = items.where((s) => s.id == id && s.epoch == epoch);
    if (matches.isEmpty) return false;
    final item = matches.first;
    if (item.status != CaptionStatus.failed) return false;
    item.status = CaptionStatus.queued;
    item.errorCode = null;
    item.lastAttemptAt = now;
    return true;
  }

  // Cards already keep their sequence, so a ready later translation can be
  // shown without waiting for a slow earlier request.
  bool canShowTranslation(Caption caption) => true;

  void expire(DateTime now, {Duration timeout = const Duration(seconds: 10)}) {
    for (final s in items) {
      if (s.status == CaptionStatus.translating &&
          now.difference(s.lastAttemptAt) >= timeout) {
        complete(s.id, s.epoch, error: 'translation_timeout');
      }
    }
  }

  void cancelEpoch(int epoch) {
    for (final s in items.where((s) => s.epoch == epoch)) {
      if (s.status == CaptionStatus.queued) {
        s.status = CaptionStatus.failed;
        s.errorCode = 'cancelled';
      } else {
        complete(s.id, epoch, error: 'cancelled');
      }
    }
  }

  void gap(int epoch, String message, DateTime now) {
    final s = append(
      id: 'gap-$_nextSequence',
      epoch: epoch,
      startMs: 0,
      endMs: 0,
      english: '',
      now: now,
    )!;
    s.status = CaptionStatus.gap;
    s.chinese = message;
  }

  void clear() {
    items.clear();
    _ids.clear();
    _nextSequence = 0;
  }
}
