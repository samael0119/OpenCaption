def trimmed:
  gsub("^\\s+|\\s+$"; "");

def aliases($values; $english):
  [
    $values[]?
    | select(type == "string")
    | trimmed
    | select(length > 0)
    | select(ascii_downcase != ($english | ascii_downcase))
    | select(test("[A-Za-z0-9]"))
    | select(
        (ascii_downcase
          | gsub("[^a-z0-9']+"; " ")
          | trimmed
          | gsub("\\s+"; " ")
          | length) > 1
      )
  ]
  | unique_by(ascii_downcase);

def term($id; $english; $chinese; $aliases; $category; $priority; $context; $preserve; $source):
  {
    id: $id,
    english: ($english | trimmed),
    aliases: aliases($aliases; $english),
    chinese: ($chinese | trimmed),
    alternatives: [],
    category: $category,
    priority: ($priority // 3),
    context: ($context // ""),
    avoid: [],
    preserve: $preserve,
    source_refs: [$source]
  };

($events[0]) as $events |
($teams[0]) as $teams |
($players[0]) as $players |
($maps[0]) as $maps |
{
  schema_version: 1,
  id: "cs2-zh-broadcast-live-entities",
  version: "0.2.0",
  display_name: "Counter-Strike 赛事、战队、选手与地图报点语料",
  language_pair: "en-US -> zh-CN",
  domain: "counter-strike-2",
  provenance: {
    provided_directory: $source_directory,
    snapshot: ($events.meta.snapshot // $maps.meta.snapshot),
    source_files: ["events.json", "teams.json", "players.json", "maps_callouts.json"],
    sources: ($events.sources + $teams.sources + $players.sources + $maps.sources),
    license_status: "not_declared_in_source_files"
  },
  translation_rules: [
    {
      rule: "preserve_entities",
      description: "选手 ID 和没有约定中文名的战队保持原始拼写。"
    },
    {
      rule: "map_sensitive_callouts",
      description: "同名报点可能因地图而异，结合 context 中的地图名称选择译法。"
    }
  ],
  terms:
    ([
      $events.series
      | to_entries[]
      | .key as $index
      | .value as $value
      | term(
          "live-event-series-\($index + 1)";
          $value.en;
          $value.zh;
          ($value.aliases // []);
          ($value.category // "event_series");
          $value.priority;
          ($value.notes // (if $value.organizer then "主办方：\($value.organizer)" else "" end));
          false;
          "events.json"
        )
    ] + [
      $events.competition_terms
      | to_entries[]
      | .key as $index
      | .value as $value
      | term(
          "live-competition-term-\($index + 1)";
          $value.en;
          $value.zh;
          ($value.aliases // []);
          ($value.category // "competition_term");
          $value.priority;
          "";
          false;
          "events.json"
        )
    ] + [
      $teams.teams
      | to_entries[]
      | .key as $index
      | .value as $value
      | term(
          "live-team-\($index + 1)";
          $value.en;
          $value.zh;
          ($value.aliases // []);
          "team";
          $value.priority;
          (if $value.hltv_rank_snapshot then "HLTV 排名快照：\($value.hltv_rank_snapshot)" else "" end);
          true;
          "teams.json"
        )
    ] + [
      $players.players
      | to_entries[]
      | .key as $index
      | .value as $value
      | term(
          "live-player-\($index + 1)";
          $value.handle;
          $value.display;
          ($value.asr_aliases // []);
          "player";
          $value.priority;
          (if $value.team then "战队：\($value.team)" else "" end);
          true;
          "players.json"
        )
    ] + [
      $maps.maps
      | to_entries[]
      | .key as $index
      | .value as $value
      | term(
          "live-map-\($index + 1)";
          $value.en;
          $value.zh;
          [$value.map_code];
          "map";
          5;
          "CS2 地图";
          false;
          "maps_callouts.json"
        )
    ] + [
      $maps.maps
      | to_entries[]
      | .key as $map_index
      | .value as $map
      | $map.callouts
      | to_entries[]
      | .key as $callout_index
      | .value as $value
      | term(
          "live-callout-\($map_index + 1)-\($callout_index + 1)";
          $value.en;
          $value.zh;
          ($value.aliases // []);
          "map_callout";
          $value.priority;
          ("地图：\($map.en)" + (if $value.notes then "；\($value.notes)" else "" end));
          false;
          "maps_callouts.json"
        )
    ])
}
