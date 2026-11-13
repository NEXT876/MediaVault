# Graph Report - MediaVault  (2026-11-12)

## Corpus Check
- 66 files · ~43,448 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 2 file(s) not represented in the graph (top: (none) 2)

## Summary
- 1412 nodes · 3146 edges · 86 communities (35 shown, 51 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 217 edges (avg confidence: 0.88)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `20342daf`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- test_remote.py
- plugin_import.py
- import_paths
- test_ai_meta.py
- test_config.py
- thumbnails.py
- RubberBandSelector
- test_plugin_import.py
- main_window.py
- DownloadsPage
- LibraryRoot
- MediaDatabase
- ThemeManager
- dialogs.py
- copy_into_folder
- MediaCard
- run_fetch
- WheelPage
- WheelWidget
- test_volumes.py
- steps
- test_collapsible.py
- test_wheel.py
- Worker
- .set_plugins
- Sidebar
- PluginImport
- .paintEvent
- VaultConfig
- MainWindow
- models/__init__.py
- test_plugins.py
- ConfigDialog
- GroupPickDialog
- visible_entries
- CardGrid
- StickBanner
- MediaType
- DetailDialog
- StickDialog
- test_card_grid.py
- target_angle
- MediaItem
- PluginError
- test_collapsible.py
- library.py
- Configuring
- .escape
- FolderSync
- find_duplicate
- .set_page
- context7
- mediavault

## God Nodes (most connected - your core abstractions)
1. `MediaDatabase` - 91 edges
2. `MainWindow` - 61 edges
3. `MediaItem` - 51 edges
4. `import_paths()` - 37 edges
5. `VaultConfig` - 36 edges
6. `CardGrid` - 35 edges
7. `LibraryRoot` - 30 edges
8. `button()` - 28 edges
9. `WheelPage` - 27 edges
10. `save_configs()` - 24 edges

## Surprising Connections (you probably didn't know these)
- `test_rejects_non_http_urls()` --uses--> `MediaDatabase`  [INFERRED]
  tests/test_remote.py → mediavault/database.py
- `test_rejects_unsafe_ids()` --uses--> `MediaDatabase`  [INFERRED]
  tests/test_remote.py → mediavault/database.py
- `test_configure_plugin_keeps_settings_on_error()` --uses--> `PluginError`  [INFERRED]
  tests/test_plugins.py → mediavault/plugins.py
- `test_run_fetch_rejects_posts_of_wrong_type()` --uses--> `PluginError`  [INFERRED]
  tests/test_plugins.py → mediavault/plugins.py
- `test_run_fetch_rejects_wrong_field_types()` --uses--> `PluginError`  [INFERRED]
  tests/test_plugins.py → mediavault/plugins.py

## Import Cycles
- None detected.

## Communities (86 total, 51 thin omitted)

### Community 0 - "test_remote.py"
Cohesion: 0.06
Nodes (32): RemotePost, DownloadResult, download_and_import(), download_dir(), download_post(), fetch_preview(), _is_http(), _request() (+24 more)

### Community 1 - "plugin_import.py"
Cohesion: 0.15
Nodes (5): _candidates(), configure_plugin(), _invalid(), is_saveable(), _load()

### Community 2 - "import_paths"
Cohesion: 0.16
Nodes (26): content_hash(), import_paths(), _db(), test_content_hash_differs_for_different_content(), test_content_hash_matches_identical_content(), test_entry_resolves_back_to_the_original_file(), test_find_duplicate_detects_stored_content(), test_find_duplicate_rejects_unknown_content() (+18 more)

### Community 3 - "test_ai_meta.py"
Cohesion: 0.07
Nodes (38): ai_duplicate_key(), _as_float(), _as_int(), _decode_text(), extract_ai_metadata(), _find_prompt_text(), format_ai_meta(), _parse_comfyui() (+30 more)

### Community 4 - "test_config.py"
Cohesion: 0.06
Nodes (33): config_from_dict(), create_config(), _default_config(), int_setting(), load_configs(), locate(), _plugin_settings(), save_configs() (+25 more)

### Community 5 - "thumbnails.py"
Cohesion: 0.06
Nodes (22): cache_key(), cache_path(), load_thumbnail(), load_thumbnails(), _read_cache(), _render(), _scaled(), _write_cache() (+14 more)

### Community 6 - "RubberBandSelector"
Cohesion: 0.06
Nodes (7): LoadingLabel, RubberBandSelector, app(), _Card, _grid(), test_drag_selects_touched_cards_on_top_of_base(), test_move_without_press_does_nothing()

### Community 7 - "test_plugin_import.py"
Cohesion: 0.10
Nodes (16): download_status_text(), DownloadJob, DownloadRow, JobState, apply_imported(), _job(), test_status_text_covers_every_state(), test_status_text_never_claims_a_file_past_the_total() (+8 more)

### Community 10 - "LibraryRoot"
Cohesion: 0.26
Nodes (9): find_unindexed(), scan(), LibraryRoot, test_find_unindexed_matches_paths_stored_relative_to_the_stick(), test_find_unindexed_skips_ignored_files(), test_not_indexed_reports_rejected_files(), test_scan_does_nothing_while_the_stick_is_unplugged(), test_scan_stores_stick_paths_relative() (+1 more)

### Community 11 - "MediaDatabase"
Cohesion: 0.10
Nodes (10): MediaDatabase, test_concurrent_adds_keep_every_entry(), test_load_corrupt_file_reports_error_and_backup(), test_random_picks_only_from_the_given_pool(), test_save_leaves_no_temp_file(), test_unreadable_file_is_never_overwritten(), test_ai_meta_round_trip(), test_corrupt_json_is_backed_up() (+2 more)

### Community 12 - "ThemeManager"
Cohesion: 0.08
Nodes (8): build_qpalette(), build_stylesheet(), ThemeManager, _build_splash_pixmap(), main(), _scan_after_show(), _show_main(), _splash_font()

### Community 13 - "dialogs.py"
Cohesion: 0.06
Nodes (8): AnalysisDialog, checked_groups(), EditDialog, FolderPreviewDialog, group_checklist(), GroupRandomDialog, button(), field_label()

### Community 14 - "copy_into_folder"
Cohesion: 0.10
Nodes (15): _filter_patterns(), _native_pick(), pick_file(), pick_files(), copy_into_folder(), unique_destination(), test_copies_a_file_into_the_folder(), test_file_already_inside_the_folder_is_kept() (+7 more)

### Community 15 - "MediaCard"
Cohesion: 0.09
Nodes (4): repolish(), MediaCard, rounded_pixmap(), score_tier()

### Community 16 - "run_fetch"
Cohesion: 0.19
Nodes (13): FetchResult, run_fetch(), Dummy, no_preview(), post(), test_run_fetch_drops_duplicate_ids(), test_run_fetch_passes_plugin_error(), test_run_fetch_rejects_posts_of_wrong_type() (+5 more)

### Community 17 - "WheelPage"
Cohesion: 0.10
Nodes (3): matching_config(), WheelPage, test_matching_config_needs_identical_entries_in_order()

### Community 19 - "test_volumes.py"
Cohesion: 0.07
Nodes (20): open_file(), absolute_path(), find_volume(), folder_path(), marker_path(), new_uuid(), read_marker(), _safe_parts() (+12 more)

### Community 20 - "steps"
Cohesion: 0.09
Nodes (22): QT_QPA_PLATFORM, jobs, test, name, on, pull_request, push, contents (+14 more)

### Community 22 - "test_wheel.py"
Cohesion: 0.16
Nodes (11): parse_entries(), saved(), _answer(), page(), qtbot_free_app(), test_all_groups_overwrite_confirmed(), test_all_groups_overwrite_warns_when_entries_are_unsaved(), test_no_groups_shows_hint_and_keeps_entries() (+3 more)

### Community 24 - ".set_plugins"
Cohesion: 0.15
Nodes (9): app(), sidebar(), test_one_button_per_plugin(), test_online_section_hidden_without_plugins(), test_online_section_only_outside_ai_mode(), test_online_section_stays_hidden_without_plugins_in_normal_mode(), test_plugin_loading_text(), test_set_plugins_keeps_section_hidden_in_ai_mode() (+1 more)

### Community 25 - "Sidebar"
Cohesion: 0.11
Nodes (3): _nav_button(), _section_label(), Sidebar

### Community 26 - "PluginImport"
Cohesion: 0.15
Nodes (3): PluginImport, PreviewDialog, ImportPlugin

### Community 28 - "VaultConfig"
Cohesion: 0.20
Nodes (7): VaultConfig, migrate_settings(), Migrating, test_migrate_called_only_without_settings(), test_migrate_error_leaves_extra(), test_migrate_rejects_unsaveable_settings(), test_plugin_without_migrate_is_left_alone()

### Community 30 - "models/__init__.py"
Cohesion: 0.08
Nodes (8): setup_logging(), CopyResult, VolumeInfo, is_inside(), mounted_roots(), _norm(), vaults(), volume_for_path()

### Community 31 - "test_plugins.py"
Cohesion: 0.32
Nodes (10): discover_plugins(), test_broken_plugins_are_skipped(), test_discovers_public_and_private(), test_duplicate_name_first_wins(), test_missing_root_returns_empty(), test_private_folder_itself_is_not_a_plugin(), test_readme_example_loads(), test_relative_import_and_hyphen_folder() (+2 more)

### Community 35 - "visible_entries"
Cohesion: 0.34
Nodes (11): _matches(), visible_entries(), _entries(), test_group_filter(), test_input_order_is_not_mutated(), test_last_watched_puts_unwatched_entries_last(), test_score_ties_are_broken_by_title_not_input_order(), test_search_finds_ai_prompts() (+3 more)

### Community 38 - "MediaType"
Cohesion: 0.17
Nodes (5): file_filter(), media_exts(), MediaType, test_ai_mode_only_indexes_png(), test_file_filter_lists_every_known_extension()

### Community 45 - "target_angle"
Cohesion: 0.22
Nodes (3): target_angle(), test_spin_uses_text_typed_within_the_debounce_delay(), test_target_angle_puts_winner_under_pointer()

### Community 46 - "MediaItem"
Cohesion: 0.11
Nodes (11): MediaItem, _smart_weights(), test_add_many_saves_once(), test_add_saves(), test_file_path_prefers_video_over_preview_image(), test_from_dict_ignores_unknown_keys(), test_legacy_dict_gets_empty_ai_meta(), test_recent_picks_are_excluded_unless_whole_pool() (+3 more)

### Community 47 - "PluginError"
Cohesion: 0.20
Nodes (4): _bug(), PluginError, test_configure_plugin_rejects_unsaveable_settings(), _Unsaveable

### Community 48 - "test_collapsible.py"
Cohesion: 0.31
Nodes (7): app(), _section(), settings(), test_clicking_the_header_toggles_and_persists(), test_collapsed_by_default(), test_restores_the_saved_state(), test_toggled_signal()

### Community 51 - "library.py"
Cohesion: 0.29
Nodes (3): index_files(), not_indexed(), ImportResult

### Community 52 - "Configuring"
Cohesion: 0.29
Nodes (3): Configuring, test_configure_plugin_keeps_settings_on_error(), test_configure_plugin_returns_changed_copy()

### Community 59 - "find_duplicate"
Cohesion: 0.09
Nodes (8): build_entry(), find_duplicate(), _Index, _try_hash(), path_key(), stored_path(), test_path_key_matches_absolute_and_relative(), test_stored_path_keeps_paths_outside_the_volume()

### Community 64 - "context7"
Cohesion: 0.50
Nodes (3): npx, context7, @upstash/context7-mcp

## Knowledge Gaps
- **3 isolated node(s):** `npx`, `@upstash/context7-mcp`, `mediavault`
  These have ≤1 connection - possible missing edges. (Counts symbols only; 615 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **51 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `MainWindow` connect `MainWindow` to `test_config.py`, `test_plugin_import.py`, `main_window.py`, `DownloadsPage`, `MediaDatabase`, `ThemeManager`, `dialogs.py`, `PluginImport`, `ConfigDialog`, `StickBanner`, `DetailDialog`, `._setup_ui`, `._finish_batch`, `StickDialog`, `.closeEvent`, `.escape`, `FolderSync`, `._sync_loading`, `._build_action_bar`, `._on_folder_synced`, `.set_theme`?**
  _High betweenness centrality (0.090) - this node is a cross-community bridge._
- **Are the 21 inferred relationships involving `MediaDatabase` (e.g. with `AnalysisDialog` and `DetailDialog`) actually correct?**
  _`MediaDatabase` has 21 INFERRED edges - model-reasoned connections that need verification._
- **What connects `npx`, `@upstash/context7-mcp`, `mediavault` to the rest of the system?**
  _3 weakly-connected nodes found - possible missing edges._
- **Should `test_remote.py` be split into smaller, more focused modules?**
  _Cohesion score 0.05879917184265011 - nodes in this community are weakly interconnected._
- **Why does `MediaDatabase` connect `MediaDatabase` to `test_remote.py`, `plugin_import.py`, `import_paths`, `test_config.py`, `test_plugin_import.py`, `main_window.py`, `DownloadsPage`, `LibraryRoot`, `dialogs.py`, `test_volumes.py`, `Worker`, `PluginImport`, `MainWindow`, `models/__init__.py`, `.__init__`, `DetailDialog`, `MediaItem`, `library.py`, `FolderSync`, `find_duplicate`, `.__init__`?**
  _High betweenness centrality (0.087) - this node is a cross-community bridge._
- **Are the 12 inferred relationships involving `MainWindow` (e.g. with `MediaDatabase` and `AnalysisDialog`) actually correct?**
  _`MainWindow` has 12 INFERRED edges - model-reasoned connections that need verification._
- **Should `plugin_import.py` be split into smaller, more focused modules?**
  _Cohesion score 0.14736842105263157 - nodes in this community are weakly interconnected._