import 'corpus.dart';

/// Pre-MT phonetic normalization for promptless mobile ONNX ASR (SenseVoice /
/// Parakeet-TDT). Only active when the user opts into a domain glossary (e.g.
/// CS2), converting high-frequency phonetic mishearings into canonical English
/// terms and player/team IDs BEFORE term matching and HY-MT1.5 translation.
class AsrPhoneticNormalizer {
  static final _strayAngleBracket = RegExp(r'[<>]+');
  static final _multiSpace = RegExp(r'\s+');

  /// High-confidence CS2 phonetic corrections that do not collide with normal
  /// commentary prose.
  static final List<(RegExp, String Function(Match))> _cs2Rules = [
    // Team / map / side / callout homophones
    (RegExp(r'\bcity\s+side\b', caseSensitive: false), (_) => 'CT side'),
    (RegExp(r'\b(?:u|you)\s+til\b', caseSensitive: false), (_) => 'util'),
    (RegExp(r'\btwo\s+manhole\b', caseSensitive: false), (_) => 'two-man hold'),
    (RegExp(r'\b2\s+manhole\b', caseSensitive: false), (_) => 'two-man hold'),
    (RegExp(r'\bmidlugs\b|\bmid\s+lugs\b', caseSensitive: false), (_) => 'mid lurks'),
    (RegExp(r'\bdouble\s+(?:orb|orp)s?\b', caseSensitive: false), (_) => 'double AWP'),
    (RegExp(r'\borps\b', caseSensitive: false), (_) => 'AWPs'),
    (RegExp(r'\bthis\s+apl\b', caseSensitive: false), (_) => 'this AWP'),
    (
      RegExp(
        r'\b(this|the|an|one|on|with|by)\s+(?:orb|orp)\b',
        caseSensitive: false,
      ),
      (m) => '${m.group(1)} AWP',
    ),
    (
      RegExp(
        r'\b(through|towards?|into|around|out\s+of|in|on|from|at|a|b)\s+maine\b',
        caseSensitive: false,
      ),
      (m) => '${m.group(1)} Main',
    ),
    (
      RegExp(
        r'\b(around|towards?|out\s+of)\s+may\b',
        caseSensitive: false,
      ),
      (m) => '${m.group(1)} Main',
    ),
    (RegExp(r'\bin\s+aine\b', caseSensitive: false), (_) => 'in A Main'),
    (RegExp(r'\bmiddle\s+button\b', caseSensitive: false), (_) => 'middle, but'),
    (
      RegExp(r'\b([1-5])B([1-5])\b'),
      (m) => '${m.group(1)}v${m.group(2)}',
    ),
    (RegExp(r'\bshira\s+hol\b', caseSensitive: false), (_) => 'sh1ro holding'),
    // Pro player / team phonetic aliases (Tier-1/Tier-2 active CS2 rosters).
    // Strictly non-English-word phonetic spellings so normal commentary prose
    // is never altered; optional possessive `'s` is preserved.
    (
      RegExp(
        r"\b(?:carrigan|karagan|kerrigan|carigan|karigan|carragan|karragan|caragan)('s)?\b",
        caseSensitive: false,
      ),
      (m) => "karrigan${m.group(1) ?? ''}",
    ),
    (
      RegExp(
        r"\b(?:shira|shiro|shero|sheero|shyro|shiru)('s)?\b",
        caseSensitive: false,
      ),
      (m) => "sh1ro${m.group(1) ?? ''}",
    ),
    (
      RegExp(
        r"\b(?:zontic|zontics|zontix|zonticks|zontex|zontiks|zontecks)('s)?\b",
        caseSensitive: false,
      ),
      (m) => "zont1x${m.group(1) ?? ''}",
    ),
    (
      RegExp(
        r"\b(?:teneer|tnir|tenere|teneir|t\s+near|tn1r)('s)?\b",
        caseSensitive: false,
      ),
      (m) => "tN1R${m.group(1) ?? ''}",
    ),
    (
      RegExp(
        r"\b(?:monese|monesy|monesey|monesee|monesie|monesi|monessy|monessie|monasy|monacy|monassy|monisy|monisi|monise|monesty|monastery|mo\s+nesy|mo\s+nessy|mo\s+nese)('s)?\b",
        caseSensitive: false,
      ),
      (m) => "m0NESY${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:magics|magix|magixx|majix|majixx)('s)?\b", caseSensitive: false),
      (m) => "magixx${m.group(1) ?? ''}",
    ),
    (
      RegExp(r'\b(with|on|for|from|to|onto)\s+magic\b', caseSensitive: false),
      (m) => '${m.group(1)} magixx',
    ),
    (
      RegExp(
        r"\b(?:tes\s+says|tesses|tesis|teses|tessis|tesus|tessus)('s)?\b",
        caseSensitive: false,
      ),
      (m) => "TeSeS${m.group(1) ?? ''}",
    ),
    (
      RegExp(
        r"\b(?:kyusuke|kiosuke|kyosuke|kyoske|kyouske|keosuke|kioske|kyosuki|kyusuki)('s)?\b",
        caseSensitive: false,
      ),
      (m) => "kyousuke${m.group(1) ?? ''}",
    ),
    (
      RegExp(
        r"\b(?:kixan|kicksan|kyxan|kixsan|kyksan|kicks\s+an)('s)?\b",
        caseSensitive: false,
      ),
      (m) => "kyxsan${m.group(1) ?? ''}",
    ),
    (
      RegExp(
        r"\b(?:zaiwoo|zywoo|zywu|zaiwu|zywo|ziwoo|zai\s+woo|zy\s+woo)('s)?\b",
        caseSensitive: false,
      ),
      (m) => "ZywOo${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:flamez|flamesz|flame\s+z)('s)?\b", caseSensitive: false),
      (m) => "flameZ${m.group(1) ?? ''}",
    ),
    (
      RegExp(
        r"\b(?:torsi|torzi|torsie|torzie|torzy|torsy|torzhi)('s)?\b",
        caseSensitive: false,
      ),
      (m) => "torzsi${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:spinx|spinks|sphinx|sphynx)('s)?\b", caseSensitive: false),
      (m) => "Spinx${m.group(1) ?? ''}",
    ),
    (
      RegExp(
        r"\b(?:jimpphat|jimphat|jimfat|jimpfat|jim\s+fat|jimp\s+hat|jim\s+hat|jimp\s+fat)('s)?\b",
        caseSensitive: false,
      ),
      (m) => "Jimpphat${m.group(1) ?? ''}",
    ),
    (
      RegExp(
        r"\b(?:xertion|zertion|zersion|xersion|zerchun|sertion)('s)?\b",
        caseSensitive: false,
      ),
      (m) => "xertioN${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:xelex|zelex|selix|zelix)('s)?\b", caseSensitive: false),
      (m) => "xelex${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:brollan|brolan|brolin|brolen)('s)?\b", caseSensitive: false),
      (m) => "Brollan${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:mezi|mezzy|mezzie|mezy|mezzi)('s)?\b", caseSensitive: false),
      (m) => "mezii${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:brokey|brokie|broki|brocky|brokee)('s)?\b", caseSensitive: false),
      (m) => "broky${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:ropz|rops|robz)('s)?\b", caseSensitive: false),
      (m) => "ropz${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:twistz|twists|twistzz)('s)?\b", caseSensitive: false),
      (m) => "Twistzz${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:neityu|naitu|neitu|natyu|naytu)('s)?\b", caseSensitive: false),
      (m) => "Neityu${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:jcobbb|jcobb|jaycob)('s)?\b", caseSensitive: false),
      (m) => "jcobbb${m.group(1) ?? ''}",
    ),
    (
      RegExp(
        r"\b(?:alexib|alexi\s+b|aleksi\s+b|alexy\s+b|alexee\s+b|alexie\s+b)('s)?\b",
        caseSensitive: false,
      ),
      (m) => "Aleksib${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:makazze|makaze|makazi|macaze|makazzi)('s)?\b", caseSensitive: false),
      (m) => "makazze${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:nertz|nerts|nerdz|nert\s+z)('s)?\b", caseSensitive: false),
      (m) => "NertZ${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:r1nkle|rinkle)('s)?\b", caseSensitive: false),
      (m) => "r1nkle${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:heavy\s*god|heavigod)('s)?\b", caseSensitive: false),
      (m) => "HeavyGod${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:matys|matis|mattis|matiss|matees)('s)?\b", caseSensitive: false),
      (m) => "MATYS${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:malbs|malbsmd|malbz|malbs\s+md|malps)('s)?\b", caseSensitive: false),
      (m) => "malbsMd${m.group(1) ?? ''}",
    ),
    (
      RegExp(
        r"\b(?:kscerato|k\s*serato|caserato|kaserato|cerato|keserato|k\s+cerato)('s)?\b",
        caseSensitive: false,
      ),
      (m) => "KSCERATO${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:yuurih|yuri|yurii|yurih|yury)('s)?\b", caseSensitive: false),
      (m) => "yuurih${m.group(1) ?? ''}",
    ),
    (
      RegExp(
        r"\b(?:molodoy|molodoi|maladoy|maladoi|molodai)('s)?\b",
        caseSensitive: false,
      ),
      (m) => "molodoy${m.group(1) ?? ''}",
    ),
    (
      RegExp(
        r"\b(?:xantares|zantares|santares|zantaris|xantaris|zantarez|xantarez)('s)?\b",
        caseSensitive: false,
      ),
      (m) => "XANTARES${m.group(1) ?? ''}",
    ),
    (
      RegExp(
        r"\b(?:woxic|woxik|woksic|woksik|voxic|voxik|woxick)('s)?\b",
        caseSensitive: false,
      ),
      (m) => "woxic${m.group(1) ?? ''}",
    ),
    (
      RegExp(
        r"\b(?:wicadia|wikadia|vicadia|vikadia|wickadia)('s)?\b",
        caseSensitive: false,
      ),
      (m) => "Wicadia${m.group(1) ?? ''}",
    ),
    (
      RegExp(
        r"\b(?:hooxi|hooksi|huxi|huxy|hooxy|hooksie|hooxie)('s)?\b",
        caseSensitive: false,
      ),
      (m) => "HooXi${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:phzy|fizzy|phizy|fezzy)('s)?\b", caseSensitive: false),
      (m) => "phzy${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:jabbi|jabi|jaby|jabby|yabbi|yabi)('s)?\b", caseSensitive: false),
      (m) => "jabbi${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:staehr|staher|stehr)('s)?\b", caseSensitive: false),
      (m) => "Staehr${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:senzu|sensu|senzo|senzoo)('s)?\b", caseSensitive: false),
      (m) => "Senzu${m.group(1) ?? ''}",
    ),
    (
      RegExp(
        r"\b(?:mzinho|emzinho|m\s*zinho|em\s+zinho|mzino)('s)?\b",
        caseSensitive: false,
      ),
      (m) => "mzinho${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\bnine\s+one\s+zero\b", caseSensitive: false),
      (_) => "910",
    ),
    (
      RegExp(
        r"\b(?:boombl4|boomich|boomitch|boomage|boombich|boombla|boomblya)('s)?\b",
        caseSensitive: false,
      ),
      (m) => "Boombl4${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:zorte|zorty|zortay)('s)?\b", caseSensitive: false),
      (m) => "zorte${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:fl1t|flit)('s)?\b", caseSensitive: false),
      (m) => "FL1T${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:jame|jayme)('s)?\b", caseSensitive: false),
      (m) => "Jame${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:xielo|zielo|sielo|cielo)('s)?\b", caseSensitive: false),
      (m) => "xiELO${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:zweih|zwei|zvai|zwai)('s)?\b", caseSensitive: false),
      (m) => "zweih${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:snax|snacks)('s)?\b", caseSensitive: false),
      (m) => "Snax${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:tauson|tawson|towson|touson)('s)?\b", caseSensitive: false),
      (m) => "Tauson${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:fl4mus|flamus|flamous|flamas|flamuss)('s)?\b", caseSensitive: false),
      (m) => "FL4MUS${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:misutaaa|misuta|mizuta|mesuta)('s)?\b", caseSensitive: false),
      (m) => "misutaaa${m.group(1) ?? ''}",
    ),
    (
      RegExp(
        r"\b(?:yekindar|yekinder|yakindar|yakinder|yekindur|yakindur)('s)?\b",
        caseSensitive: false,
      ),
      (m) => "YEKINDAR${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:elige|elije|elidge|e\s+lige|e\s+liege)('s)?\b", caseSensitive: false),
      (m) => "EliGE${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:tabsen|tabson|tabzen|tabsin)('s)?\b", caseSensitive: false),
      (m) => "tabseN${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:faven|fayven|favin)('s)?\b", caseSensitive: false),
      (m) => "faveN${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:blamef|blame\s+f|blam\s+f|blame\s+eff)('s)?\b", caseSensitive: false),
      (m) => "blameF${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:gr1ks|griks|gricks)('s)?\b", caseSensitive: false),
      (m) => "gr1ks${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:chr1zn|chrizn|krizn|chrisn)('s)?\b", caseSensitive: false),
      (m) => "Chr1zN${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:stavn|staven|stavin|stavan|stovon)('s)?\b", caseSensitive: false),
      (m) => "stavn${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:sjuush|sjush|shush|syush|sjoosh)('s)?\b", caseSensitive: false),
      (m) => "sjuush${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:krimbo|crimbo|krembo|krimbow)('s)?\b", caseSensitive: false),
      (m) => "Krimbo${m.group(1) ?? ''}",
    ),
    (
      RegExp(
        r"\b(?:xkacpersky|kacpersky|kaspersky|kasperski|kacperski)('s)?\b",
        caseSensitive: false,
      ),
      (m) => "xKacpersky${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:insani|insany|insanie)('s)?\b", caseSensitive: false),
      (m) => "insani${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:dumau|dumao|doomao|dumow)('s)?\b", caseSensitive: false),
      (m) => "dumau${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:latto|lato|latow)('s)?\b", caseSensitive: false),
      (m) => "latto${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:n1ssim|nissim|nisim|nissam)('s)?\b", caseSensitive: false),
      (m) => "n1ssim${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:xfl0ud|xfloud|exfloud|x\s+floud|ex\s+floud)('s)?\b", caseSensitive: false),
      (m) => "xfl0ud${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:westmelon|west\s+melon)('s)?\b", caseSensitive: false),
      (m) => "Westmelon${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:z4kr|zakr|zaker|zacker)('s)?\b", caseSensitive: false),
      (m) => "z4KR${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:c4llm3su3|call\s+me\s+sue|callmesue)('s)?\b", caseSensitive: false),
      (m) => "C4LLM3SU3${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:jamyoung|jam\s+young)('s)?\b", caseSensitive: false),
      (m) => "JamYoung${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:moseyuh|moseya|mosia|mosiah)('s)?\b", caseSensitive: false),
      (m) => "Moseyuh${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:magisk|majisk|magisc)('s)?\b", caseSensitive: false),
      (m) => "Magisk${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:degster|degstur)('s)?\b", caseSensitive: false),
      (m) => "degster${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:cadian|kadian|caydian|cadyan)('s)?\b", caseSensitive: false),
      (m) => "cadiaN${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:niko|nico|neeko|neko|nikko)('s)?\b", caseSensitive: false),
      (m) => "NiKo${m.group(1) ?? ''}",
    ),
    (
      RegExp(r"\b(?:donk|donck)('s)?\b", caseSensitive: false),
      (m) => "donk${m.group(1) ?? ''}",
    ),
    (RegExp(r'\bteam\s+spirit\b', caseSensitive: false), (_) => 'Spirit'),
    (RegExp(r'\bteam\s+falcons\b', caseSensitive: false), (_) => 'Falcons'),
    (RegExp(r'\bfalcon\b', caseSensitive: false), (_) => 'Falcons'),
  ];

  /// Ambiguous phonetic rules activated ONLY when the corresponding team/player
  /// is active in the current match context or user hints.
  static final _moneyAsMonesy = RegExp(
    r'\b(for|on|with|from|to|onto)\s+money\b',
    caseSensitive: false,
  );
  static final _magicAsMagixx = RegExp(r'\bmagic\b', caseSensitive: false);
  static final _wonderfulAsW0nderful = RegExp(r'\bwonderful\b', caseSensitive: false);
  static final _wrinkleAsR1nkle = RegExp(r'\bwrinkle\b', caseSensitive: false);
  static final _hunterAsHunter = RegExp(r"\bhunter('s)?\b", caseSensitive: false);
  static final _electronicAsElectronic = RegExp(r'\belectronic\b', caseSensitive: false);
  static final _deviceAsDev1ce = RegExp(
    r'\b(for|on|with|from|to|onto)\s+device\b',
    caseSensitive: false,
  );

  static String normalize(
    String text, {
    required CorpusProfile profile,
    Iterable<String> activeTeams = const [],
    String contextHint = '',
  }) {
    var out = text
        .replaceAll(_strayAngleBracket, '')
        .replaceAll(_multiSpace, ' ')
        .trim();
    if (out.isEmpty || profile != CorpusProfile.cs2) return out;

    for (final (pattern, replace) in _cs2Rules) {
      out = out.replaceAllMapped(pattern, replace);
    }

    final ctx = '${activeTeams.join(' ')} $contextHint'.toLowerCase();
    if (ctx.contains('falcons') || ctx.contains('g2') || ctx.contains('m0nesy')) {
      out = out.replaceAllMapped(
        _moneyAsMonesy,
        (m) => '${m.group(1)} m0NESY',
      );
    }
    if (ctx.contains('spirit') || ctx.contains('magixx')) {
      out = out.replaceAll(_magicAsMagixx, 'magixx');
    }
    if (ctx.contains('navi') || ctx.contains('natus vincere') || ctx.contains('w0nderful')) {
      out = out.replaceAll(_wonderfulAsW0nderful, 'w0nderful');
    }
    if (ctx.contains('g2') || ctx.contains('r1nkle')) {
      out = out.replaceAll(_wrinkleAsR1nkle, 'r1nkle');
    }
    if (ctx.contains('g2') || ctx.contains('hunter')) {
      out = out.replaceAllMapped(
        _hunterAsHunter,
        (m) => "huNter-${m.group(1) ?? ''}",
      );
    }
    if (ctx.contains('bc.game') || ctx.contains('electronic')) {
      out = out.replaceAll(_electronicAsElectronic, 'electroNic');
    }
    if (ctx.contains('astralis') || ctx.contains('100 thieves') || ctx.contains('dev1ce') || ctx.contains('device')) {
      out = out.replaceAllMapped(
        _deviceAsDev1ce,
        (m) => '${m.group(1)} dev1ce',
      );
    }

    return out.replaceAll(_multiSpace, ' ').trim();
  }
}
