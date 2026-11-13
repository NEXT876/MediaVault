# Graph Report - MediaVault  (2026-11-13)

## Corpus Check
- 67 files · ~44,539 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 2 file(s) not represented in the graph (top: (none) 2)

## Summary
- 1424 nodes · 3168 edges · 107 communities (38 shown, 69 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 213 edges (avg confidence: 0.87)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `6141c5d9`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- test_remote.py
- import_paths
- test_ai_meta.py
- test_config.py
- run_fetch
- RubberBandSelector
- test_plugin_import.py
- main_window.py
- DownloadsPage
- library.py
- ThemeManager
- dialogs.py
- _native_pick
- MediaCard
- plugins.py
- WheelPage
- WheelWidget
- read_marker
- steps
- test_collapsible.py
- test_wheel.py
- downloads.py
- .set_plugins
- Sidebar
- load_thumbnail
- GroupRandomDialog
- os
- models/__init__.py
- ConfigDialog
- ._setup_ui
- GroupPickDialog
- visible_entries
- CardGrid
- StickBanner
- ._locate
- DetailDialog
- MainWindow
- StickDialog
- test_card_grid.py
- target_angle
- MediaItem
- ._build_cache
- ._locate
- config.py
- test_plugins.py
- EditDialog
- .escape
- volume_for_path
- folder_path
- absolute_path
- .set_page
- context7
- mediavault
- test_volumes.py
- PreviewDialog
- VaultConfig
- PluginImport
- test_collapsible.py
- _nav_button
- path_key
- PluginError
- .from_dict
- Configuring

## God Nodes (most connected - your core abstractions)
1. `MediaDatabase` - 94 edges
2. `MediaItem` - 68 edges
3. `MainWindow` - 53 edges
4. `import_paths()` - 37 edges
5. `CardGrid` - 33 edges
6. `VaultConfig` - 33 edges
7. `button()` - 28 edges
8. `LibraryRoot` - 26 edges
9. `WheelPage` - 26 edges
10. `save_configs()` - 24 edges

## Surprising Connections (you probably didn't know these)
- `test_create_config_makes_unique_paths()` --calls--> `create_config()`  [EXTRACTED]
  tests/test_config.py → mediavault/config.py
- `test_rejects_non_http_urls()` --uses--> `MediaDatabase`  [INFERRED]
  tests/test_remote.py → mediavault/database.py
- `test_rejects_unsafe_ids()` --uses--> `MediaDatabase`  [INFERRED]
  tests/test_remote.py → mediavault/database.py
- `_ai_entry()` --calls--> `MediaItem`  [INFERRED]
  tests/test_ai_meta.py → mediavault/models/media.py
- `test_summarize_prompts_counts_tags_models_and_scores()` --calls--> `MediaItem`  [INFERRED]
  tests/test_ai_meta.py → mediavault/models/media.py

## Import Cycles
- None detected.

## Communities (107 total, 69 thin omitted)

### Community 0 - "test_remote.py"
Cohesion: 0.08
Nodes (30): RemotePost, download_and_import(), download_dir(), download_post(), fetch_preview(), _is_http(), _request(), _target_path() (+22 more)

### Community 2 - "import_paths"
Cohesion: 0.07
Nodes (42): build_entry(), content_hash(), find_duplicate(), import_paths(), _try_hash(), copy_into_folder(), unique_destination(), is_inside() (+34 more)

### Community 3 - "test_ai_meta.py"
Cohesion: 0.06
Nodes (40): ai_duplicate_key(), _as_float(), _as_int(), _decode_text(), extract_ai_metadata(), _find_prompt_text(), format_ai_meta(), _parse_comfyui() (+32 more)

### Community 4 - "test_config.py"
Cohesion: 0.09
Nodes (25): config_from_dict(), _default_config(), int_setting(), load_configs(), _plugin_settings(), find_new_media(), _round_trip(), test_configs_file_is_private() (+17 more)

### Community 5 - "run_fetch"
Cohesion: 0.19
Nodes (13): FetchResult, run_fetch(), Dummy, no_preview(), post(), test_run_fetch_drops_duplicate_ids(), test_run_fetch_passes_plugin_error(), test_run_fetch_rejects_posts_of_wrong_type() (+5 more)

### Community 6 - "RubberBandSelector"
Cohesion: 0.06
Nodes (6): RubberBandSelector, app(), _Card, _grid(), test_drag_selects_touched_cards_on_top_of_base(), test_move_without_press_does_nothing()

### Community 7 - "test_plugin_import.py"
Cohesion: 0.10
Nodes (16): download_status_text(), DownloadJob, DownloadRow, JobState, apply_imported(), _job(), test_status_text_covers_every_state(), test_status_text_never_claims_a_file_past_the_total() (+8 more)

### Community 10 - "library.py"
Cohesion: 0.10
Nodes (14): FolderSync, find_unindexed(), index_files(), media_exts(), not_indexed(), scan(), LibraryRoot, test_ai_mode_only_indexes_png() (+6 more)

### Community 12 - "ThemeManager"
Cohesion: 0.08
Nodes (8): build_qpalette(), build_stylesheet(), ThemeManager, _build_splash_pixmap(), main(), _scan_after_show(), _show_main(), _splash_font()

### Community 13 - "dialogs.py"
Cohesion: 0.09
Nodes (5): FolderPreviewDialog, _hint_label(), button(), field_label(), hint_label()

### Community 14 - "_native_pick"
Cohesion: 0.22
Nodes (4): _filter_patterns(), _native_pick(), pick_file(), pick_files()

### Community 15 - "MediaCard"
Cohesion: 0.09
Nodes (4): repolish(), MediaCard, rounded_pixmap(), score_tier()

### Community 16 - "plugins.py"
Cohesion: 0.14
Nodes (7): _bug(), configure_plugin(), ImportPlugin, _invalid(), is_saveable(), _load(), migrate_settings()

### Community 19 - "read_marker"
Cohesion: 0.20
Nodes (6): marker_path(), new_uuid(), read_marker(), write_marker(), test_marker_round_trip(), test_missing_or_broken_marker_reads_as_none()

### Community 20 - "steps"
Cohesion: 0.11
Nodes (18): QT_QPA_PLATFORM, jobs, test, name, on, pull_request, contents, if (+10 more)

### Community 22 - "test_wheel.py"
Cohesion: 0.16
Nodes (10): parse_entries(), saved(), _answer(), page(), qtbot_free_app(), test_all_groups_overwrite_confirmed(), test_all_groups_overwrite_warns_when_entries_are_unsaved(), test_no_groups_shows_hint_and_keeps_entries() (+2 more)

### Community 24 - ".set_plugins"
Cohesion: 0.15
Nodes (9): app(), sidebar(), test_one_button_per_plugin(), test_online_section_hidden_without_plugins(), test_online_section_only_outside_ai_mode(), test_online_section_stays_hidden_without_plugins_in_normal_mode(), test_plugin_loading_text(), test_set_plugins_keeps_section_hidden_in_ai_mode() (+1 more)

### Community 28 - "load_thumbnail"
Cohesion: 0.06
Nodes (21): cache_key(), cache_path(), load_thumbnail(), load_thumbnails(), _read_cache(), _render(), _scaled(), _write_cache() (+13 more)

### Community 31 - "models/__init__.py"
Cohesion: 0.15
Nodes (4): CopyResult, DownloadResult, ImportResult, VolumeInfo

### Community 34 - "GroupPickDialog"
Cohesion: 0.13
Nodes (3): GroupPickDialog, checked_groups(), group_checklist()

### Community 35 - "visible_entries"
Cohesion: 0.34
Nodes (11): _matches(), visible_entries(), _entries(), test_group_filter(), test_input_order_is_not_mutated(), test_last_watched_puts_unwatched_entries_last(), test_score_ties_are_broken_by_title_not_input_order(), test_search_finds_ai_prompts() (+3 more)

### Community 38 - "._locate"
Cohesion: 0.11
Nodes (3): file_filter(), MediaType, test_file_filter_lists_every_known_extension()

### Community 39 - "DetailDialog"
Cohesion: 0.10
Nodes (3): DetailDialog, open_file(), test_file_path_prefers_video_over_preview_image()

### Community 45 - "target_angle"
Cohesion: 0.22
Nodes (3): target_angle(), test_spin_uses_text_typed_within_the_debounce_delay(), test_target_angle_puts_winner_under_pointer()

### Community 46 - "MediaItem"
Cohesion: 0.11
Nodes (20): MediaDatabase, MediaItem, test_concurrent_adds_keep_every_entry(), test_entry_without_title_is_treated_as_corrupt(), test_failed_backup_never_overwrites_corrupt_file(), test_load_corrupt_file_reports_error_and_backup(), test_numbers_stored_as_text_are_converted(), test_random_picks_only_from_the_given_pool() (+12 more)

### Community 48 - "._locate"
Cohesion: 0.16
Nodes (3): locate(), test_locate_keeps_a_local_config_on_its_folder(), test_locate_reports_an_unplugged_volume()

### Community 50 - "config.py"
Cohesion: 0.14
Nodes (4): create_config(), save_configs(), _slug(), _stored()

### Community 51 - "test_plugins.py"
Cohesion: 0.24
Nodes (11): _candidates(), discover_plugins(), test_broken_plugins_are_skipped(), test_discovers_public_and_private(), test_duplicate_name_first_wins(), test_missing_root_returns_empty(), test_private_folder_itself_is_not_a_plugin(), test_readme_example_loads() (+3 more)

### Community 57 - "volume_for_path"
Cohesion: 0.29
Nodes (4): mounted_roots(), _norm(), volume_for_path(), test_volume_for_path_outside_any_root()

### Community 59 - "folder_path"
Cohesion: 0.33
Nodes (4): folder_path(), _safe_parts(), test_folder_path_treats_empty_as_the_root(), test_paths_cannot_escape_the_volume()

### Community 64 - "context7"
Cohesion: 0.50
Nodes (3): npx, context7, @upstash/context7-mcp

### Community 79 - "test_volumes.py"
Cohesion: 0.23
Nodes (7): find_volume(), vaults(), _make_volume(), test_absolute_path_never_returns_the_root(), test_find_volume_matches_uuid_only(), test_vaults_lists_only_marked_volumes(), test_volume_for_path_picks_the_deepest_mount()

### Community 86 - "VaultConfig"
Cohesion: 0.18
Nodes (6): VaultConfig, test_known_keys_win_over_extra(), Migrating, test_migrate_called_only_without_settings(), test_migrate_error_leaves_extra(), test_plugin_without_migrate_is_left_alone()

### Community 88 - "test_collapsible.py"
Cohesion: 0.31
Nodes (7): app(), _section(), settings(), test_clicking_the_header_toggles_and_persists(), test_collapsed_by_default(), test_restores_the_saved_state(), test_toggled_signal()

### Community 91 - "path_key"
Cohesion: 0.22
Nodes (6): path_key(), relative_to_root(), stored_path(), test_path_key_matches_absolute_and_relative(), test_relative_and_absolute_paths_round_trip(), test_stored_path_keeps_paths_outside_the_volume()

### Community 92 - "PluginError"
Cohesion: 0.25
Nodes (4): PluginError, test_configure_plugin_rejects_unsaveable_settings(), test_migrate_rejects_unsaveable_settings(), _Unsaveable

### Community 99 - ".from_dict"
Cohesion: 0.25
Nodes (3): test_from_dict_ignores_unknown_keys(), test_legacy_dict_gets_empty_ai_meta(), test_to_dict_returns_detached_copy()

### Community 100 - "Configuring"
Cohesion: 0.29
Nodes (3): Configuring, test_configure_plugin_keeps_settings_on_error(), test_configure_plugin_returns_changed_copy()

## Knowledge Gaps
- **3 isolated node(s):** `npx`, `@upstash/context7-mcp`, `mediavault`
  These have ≤1 connection - possible missing edges. (Counts symbols only; 620 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **69 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `MediaDatabase` connect `MediaItem` to `test_remote.py`, `import_paths`, `test_plugin_import.py`, `main_window.py`, `DownloadsPage`, `library.py`, `.snapshot`, `dialogs.py`, `downloads.py`, `._activate_config`, `GroupRandomDialog`, `os`, `DetailDialog`, `MainWindow`, `config.py`, `EditDialog`, `absolute_path`, `test_volumes.py`, `PluginImport`, `.__init__`?**
  _High betweenness centrality (0.130) - this node is a cross-community bridge._
- **Are the 21 inferred relationships involving `MediaDatabase` (e.g. with `AnalysisDialog` and `DetailDialog`) actually correct?**
  _`MediaDatabase` has 21 INFERRED edges - model-reasoned connections that need verification._
- **What connects `npx`, `@upstash/context7-mcp`, `mediavault` to the rest of the system?**
  _3 weakly-connected nodes found - possible missing edges._
- **Should `test_remote.py` be split into smaller, more focused modules?**
  _Cohesion score 0.08489795918367347 - nodes in this community are weakly interconnected._
- **Why does `MainWindow` connect `MainWindow` to `test_plugin_import.py`, `main_window.py`, `DownloadsPage`, `ThemeManager`, `._activate_config`, `GroupRandomDialog`, `._setup_ui`, `CardGrid`, `StickBanner`, `._locate`, `._show_page`, `.set_selection`, `MediaItem`, `._locate`, `.cancel_drag`, `.clear_selection`, `._setup_ui`, `PluginImport`, `._apply_config_ui`?**
  _High betweenness centrality (0.085) - this node is a cross-community bridge._
- **Are the 8 inferred relationships involving `MediaItem` (e.g. with `_ai_entry()` and `test_summarize_prompts_counts_tags_models_and_scores()`) actually correct?**
  _`MediaItem` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Should `import_paths` be split into smaller, more focused modules?**
  _Cohesion score 0.07297726070861978 - nodes in this community are weakly interconnected._