# Graph Report - mediavault  (2026-11-13)

## Corpus Check
- 66 files · ~44,201 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 2 file(s) not represented in the graph (top: (none) 2)

## Summary
- 1416 nodes · 3132 edges · 99 communities (32 shown, 67 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 199 edges (avg confidence: 0.87)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `91cf5a14`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- test_remote.py
- import_paths
- test_ai_meta.py
- test_config.py
- thumbnails.py
- RubberBandSelector
- test_plugin_import.py
- main_window.py
- DownloadsPage
- library.py
- .snapshot
- ThemeManager
- button
- copy_into_folder
- MediaCard
- test_plugins.py
- WheelPage
- WheelWidget
- write_marker
- steps
- test_collapsible.py
- test_wheel.py
- Worker
- .set_plugins
- Sidebar
- load_thumbnail
- MainWindow
- main_window.py
- media.py
- ConfigDialog
- ._setup_ui
- GroupPickDialog
- visible_entries
- CardGrid
- StickBanner
- ._locate
- StickDialog
- test_card_grid.py
- target_angle
- MediaItem
- ._build_cache
- create_config
- find_new_media
- _stored
- .escape
- volume_for_path
- absolute_path
- _build_splash_pixmap
- .set_page
- context7
- mediavault
- test_volumes.py
- test_models_boundary.py
- vaults
- _hint_label
- .file_path

## God Nodes (most connected - your core abstractions)
1. `MediaDatabase` - 91 edges
2. `MediaItem` - 65 edges
3. `MainWindow` - 53 edges
4. `import_paths()` - 37 edges
5. `CardGrid` - 33 edges
6. `VaultConfig` - 33 edges
7. `button()` - 28 edges
8. `WheelPage` - 26 edges
9. `LibraryRoot` - 26 edges
10. `save_configs()` - 24 edges

## Surprising Connections (you probably didn't know these)
- `test_random_picks_only_from_the_given_pool()` --uses--> `MediaDatabase`  [INFERRED]
  tests/test_media_database.py → mediavault/database.py
- `test_corrupt_json_is_backed_up()` --uses--> `MediaDatabase`  [INFERRED]
  tests/test_models.py → mediavault/database.py
- `page()` --uses--> `WheelPage`  [INFERRED]
  tests/test_wheel.py → mediavault/extras/wheel/page.py
- `grid()` --uses--> `CardGrid`  [INFERRED]
  tests/test_card_grid.py → mediavault/gui/card_grid.py
- `sidebar()` --uses--> `Sidebar`  [INFERRED]
  tests/test_sidebar.py → mediavault/gui/sidebar.py

## Import Cycles
- None detected.

## Communities (99 total, 67 thin omitted)

### Community 0 - "test_remote.py"
Cohesion: 0.05
Nodes (34): MediaDatabase, PreviewDialog, RemotePost, DownloadResult, download_and_import(), download_dir(), download_post(), fetch_preview() (+26 more)

### Community 2 - "import_paths"
Cohesion: 0.06
Nodes (33): build_entry(), find_duplicate(), import_paths(), _Index, _try_hash(), path_key(), _ai_png(), _db() (+25 more)

### Community 3 - "test_ai_meta.py"
Cohesion: 0.06
Nodes (39): ai_duplicate_key(), _as_float(), _as_int(), _decode_text(), extract_ai_metadata(), _find_prompt_text(), format_ai_meta(), _parse_comfyui() (+31 more)

### Community 4 - "test_config.py"
Cohesion: 0.10
Nodes (21): config_from_dict(), _default_config(), load_configs(), locate(), save_configs(), VaultConfig, _round_trip(), test_configs_file_is_private() (+13 more)

### Community 5 - "thumbnails.py"
Cohesion: 0.12
Nodes (8): cache_key(), cache_path(), _read_cache(), _render(), _write_cache(), get_os_thumbnail(), get_video_frame_image(), test_cache_key_is_scoped_per_volume_without_hash()

### Community 6 - "RubberBandSelector"
Cohesion: 0.06
Nodes (6): RubberBandSelector, app(), _Card, _grid(), test_drag_selects_touched_cards_on_top_of_base(), test_move_without_press_does_nothing()

### Community 7 - "test_plugin_import.py"
Cohesion: 0.10
Nodes (16): download_status_text(), DownloadJob, DownloadRow, JobState, apply_imported(), _job(), test_status_text_covers_every_state(), test_status_text_never_claims_a_file_past_the_total() (+8 more)

### Community 10 - "library.py"
Cohesion: 0.13
Nodes (15): find_unindexed(), index_files(), media_exts(), not_indexed(), scan(), MediaType, ImportResult, LibraryRoot (+7 more)

### Community 12 - "ThemeManager"
Cohesion: 0.09
Nodes (7): build_qpalette(), build_stylesheet(), repolish(), ThemeManager, main(), _scan_after_show(), _show_main()

### Community 13 - "button"
Cohesion: 0.09
Nodes (3): button(), field_label(), hint_label()

### Community 14 - "copy_into_folder"
Cohesion: 0.07
Nodes (21): _filter_patterns(), _native_pick(), open_file(), pick_file(), pick_files(), content_hash(), copy_into_folder(), unique_destination() (+13 more)

### Community 15 - "MediaCard"
Cohesion: 0.10
Nodes (3): MediaCard, rounded_pixmap(), score_tier()

### Community 16 - "test_plugins.py"
Cohesion: 0.06
Nodes (42): FetchResult, _bug(), _candidates(), configure_plugin(), discover_plugins(), ImportPlugin, _invalid(), is_saveable() (+34 more)

### Community 19 - "write_marker"
Cohesion: 0.15
Nodes (7): VolumeInfo, marker_path(), new_uuid(), read_marker(), write_marker(), test_marker_round_trip(), test_missing_or_broken_marker_reads_as_none()

### Community 20 - "steps"
Cohesion: 0.09
Nodes (22): QT_QPA_PLATFORM, jobs, test, name, on, pull_request, push, contents (+14 more)

### Community 21 - "test_collapsible.py"
Cohesion: 0.13
Nodes (8): CollapsibleSection, app(), _section(), settings(), test_clicking_the_header_toggles_and_persists(), test_collapsed_by_default(), test_restores_the_saved_state(), test_toggled_signal()

### Community 22 - "test_wheel.py"
Cohesion: 0.14
Nodes (11): parse_entries(), saved(), _answer(), page(), qtbot_free_app(), test_all_groups_overwrite_confirmed(), test_all_groups_overwrite_warns_when_entries_are_unsaved(), test_no_groups_shows_hint_and_keeps_entries() (+3 more)

### Community 24 - ".set_plugins"
Cohesion: 0.15
Nodes (9): app(), sidebar(), test_one_button_per_plugin(), test_online_section_hidden_without_plugins(), test_online_section_only_outside_ai_mode(), test_online_section_stays_hidden_without_plugins_in_normal_mode(), test_plugin_loading_text(), test_set_plugins_keeps_section_hidden_in_ai_mode() (+1 more)

### Community 28 - "load_thumbnail"
Cohesion: 0.15
Nodes (12): load_thumbnail(), load_thumbnails(), _scaled(), isolated_thumb_cache(), test_changed_content_gets_a_fresh_preview(), test_load_thumbnail_returns_none_for_missing_file(), test_load_thumbnail_scales_to_cache_bounds(), test_load_thumbnails_keeps_other_previews_when_one_fails() (+4 more)

### Community 30 - "main_window.py"
Cohesion: 0.10
Nodes (6): setup_logging(), AnalysisDialog, DetailDialog, EditDialog, FolderPreviewDialog, GroupRandomDialog

### Community 34 - "GroupPickDialog"
Cohesion: 0.11
Nodes (3): GroupPickDialog, checked_groups(), group_checklist()

### Community 35 - "visible_entries"
Cohesion: 0.34
Nodes (11): _matches(), visible_entries(), _entries(), test_group_filter(), test_input_order_is_not_mutated(), test_last_watched_puts_unwatched_entries_last(), test_score_ties_are_broken_by_title_not_input_order(), test_search_finds_ai_prompts() (+3 more)

### Community 45 - "target_angle"
Cohesion: 0.22
Nodes (3): target_angle(), test_spin_uses_text_typed_within_the_debounce_delay(), test_target_angle_puts_winner_under_pointer()

### Community 46 - "MediaItem"
Cohesion: 0.09
Nodes (15): MediaItem, test_concurrent_adds_keep_every_entry(), test_load_corrupt_file_reports_error_and_backup(), test_random_picks_only_from_the_given_pool(), test_unreadable_file_is_never_overwritten(), _smart_weights(), test_add_saves(), test_ai_meta_round_trip() (+7 more)

### Community 50 - "create_config"
Cohesion: 0.22
Nodes (3): create_config(), _slug(), test_create_config_makes_unique_paths()

### Community 51 - "find_new_media"
Cohesion: 0.36
Nodes (7): find_new_media(), test_find_new_media_can_limit_the_types(), test_find_new_media_missing_folder_returns_empty(), test_find_new_media_recurses_and_skips_known(), test_find_new_media_skips_known_relative_paths(), test_find_new_media_splits_images_and_videos(), _touch()

### Community 52 - "_stored"
Cohesion: 0.29
Nodes (3): int_setting(), _plugin_settings(), _stored()

### Community 57 - "volume_for_path"
Cohesion: 0.29
Nodes (3): relative_to_root(), volume_for_path(), test_volume_for_path_outside_any_root()

### Community 59 - "absolute_path"
Cohesion: 0.15
Nodes (9): absolute_path(), folder_path(), _safe_parts(), stored_path(), test_absolute_path_never_returns_the_root(), test_folder_path_treats_empty_as_the_root(), test_paths_cannot_escape_the_volume(), test_relative_and_absolute_paths_round_trip() (+1 more)

### Community 64 - "context7"
Cohesion: 0.50
Nodes (3): npx, context7, @upstash/context7-mcp

### Community 79 - "test_volumes.py"
Cohesion: 0.43
Nodes (4): _make_volume(), test_find_volume_matches_uuid_only(), test_vaults_lists_only_marked_volumes(), test_volume_for_path_picks_the_deepest_mount()

### Community 87 - "vaults"
Cohesion: 0.33
Nodes (3): find_volume(), mounted_roots(), vaults()

## Knowledge Gaps
- **3 isolated node(s):** `npx`, `@upstash/context7-mcp`, `mediavault`
  These have ≤1 connection - possible missing edges. (Counts symbols only; 617 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **67 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `MediaDatabase` connect `test_remote.py` to `import_paths`, `test_config.py`, `test_plugin_import.py`, `main_window.py`, `DownloadsPage`, `library.py`, `.snapshot`, `button`, `MediaItem`, `test_volumes.py`, `.__init__`, `Worker`, `MainWindow`, `main_window.py`?**
  _High betweenness centrality (0.123) - this node is a cross-community bridge._
- **Are the 21 inferred relationships involving `MediaDatabase` (e.g. with `AnalysisDialog` and `DetailDialog`) actually correct?**
  _`MediaDatabase` has 21 INFERRED edges - model-reasoned connections that need verification._
- **What connects `npx`, `@upstash/context7-mcp`, `mediavault` to the rest of the system?**
  _3 weakly-connected nodes found - possible missing edges._
- **Should `test_remote.py` be split into smaller, more focused modules?**
  _Cohesion score 0.050286058416139714 - nodes in this community are weakly interconnected._
- **Why does `MainWindow` connect `MainWindow` to `test_remote.py`, `._setup_ui`, `.__init__`, `.cancel_drag`, `CardGrid`, `test_config.py`, `._locate`, `test_plugin_import.py`, `._show_page`, `._finish_batch`, `DownloadsPage`, `main_window.py`, `ThemeManager`, `.refresh_data`, `._build_action_bar`, `._activate_config`, `main_window.py`?**
  _High betweenness centrality (0.082) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `MainWindow` (e.g. with `MediaDatabase` and `CardGrid`) actually correct?**
  _`MainWindow` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Should `import_paths` be split into smaller, more focused modules?**
  _Cohesion score 0.06246799795186892 - nodes in this community are weakly interconnected._